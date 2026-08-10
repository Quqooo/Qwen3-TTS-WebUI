"""
WebUI 后端主入口

FastAPI 应用实例化、中间件注册和路由挂载均在此文件完成。
"""
import asyncio
import json
import logging
import os
import sys
import time
from contextlib import asynccontextmanager

logging.basicConfig(
    level=logging.INFO,
    format="[WebUI] %(asctime)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.staticfiles import StaticFiles

from .cache import get_cache_manager, idle_cleanup_loop
from .config import load_settings
from .errors import APIError, api_error_handler, validation_error_handler
from .routers import (
    settings as settings_router,
    audio as audio_router,
    synthesis as synthesis_router,
    models as models_router,
    voices as voices_router,
    batch as batch_router,
    worker as worker_router,
    tracker as tracker_router,
    ws as ws_router,
)

_logger = logging.getLogger("qwen-webui")

MAX_LOG_VALUE_LEN = 100
MAX_LOG_BODY_BYTES = 1024 * 1024
_is_prod = (Path(__file__).resolve().parent / "static").is_dir()


def _resolve_static_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "backend" / "static"
    return Path(__file__).resolve().parent / "static"


def _truncate_json(obj):
    """递归截断 JSON 中超过 MAX_LOG_VALUE_LEN 的字符串值"""
    if isinstance(obj, str):
        return obj[:MAX_LOG_VALUE_LEN] + "..." if len(obj) > MAX_LOG_VALUE_LEN else obj
    if isinstance(obj, dict):
        return {k: _truncate_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_truncate_json(v) for v in obj]
    return obj


def _format_body_log(body: bytes, total_size: int, content_type: str) -> str:
    if not total_size:
        return ""
    if "json" in content_type:
        if total_size > len(body):
            return f"<{total_size} bytes; log capture limit exceeded>"
        try:
            parsed = json.loads(body.decode("utf-8"))
            return json.dumps(_truncate_json(parsed), ensure_ascii=False)
        except Exception:
            pass
    return f"<{total_size} bytes binary>"


class RequestLogMiddleware:
    """Log ASGI messages without consuming or rebuilding streaming responses."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/"):
            await self.app(scope, receive, send)
            return

        if _is_prod:
            await self.app(scope, receive, send)
            return

        start = time.monotonic()
        request_body = bytearray()
        request_size = 0
        response_body = bytearray()
        response_size = 0
        status_code = 500
        response_content_type = ""

        async def receive_wrapper():
            nonlocal request_size
            message = await receive()
            if message["type"] == "http.request":
                chunk = message.get("body", b"")
                request_size += len(chunk)
                remaining = MAX_LOG_BODY_BYTES - len(request_body)
                if remaining > 0:
                    request_body.extend(chunk[:remaining])
            return message

        async def send_wrapper(message):
            nonlocal status_code, response_size, response_content_type
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = {
                    key.decode("latin-1").lower(): value.decode("latin-1")
                    for key, value in message.get("headers", [])
                }
                response_content_type = headers.get("content-type", "")
            elif message["type"] == "http.response.body":
                chunk = message.get("body", b"")
                response_size += len(chunk)
                remaining = MAX_LOG_BODY_BYTES - len(response_body)
                if remaining > 0 and "json" in response_content_type:
                    response_body.extend(chunk[:remaining])
            await send(message)

        try:
            await self.app(scope, receive_wrapper, send_wrapper)
        finally:
            elapsed = time.monotonic() - start
            method = scope.get("method", "")
            path = scope.get("path", "")
            request_log = ""
            if request_size:
                request_content_type = ""
                for key, value in scope.get("headers", []):
                    if key.lower() == b"content-type":
                        request_content_type = value.decode("latin-1")
                        break
                formatted = _format_body_log(bytes(request_body), request_size, request_content_type)
                request_log = f"\n  └─ body: {formatted}"

            response_log = ""
            if response_size:
                formatted = _format_body_log(
                    bytes(response_body), response_size, response_content_type,
                )
                response_log = f"\n  └─ response: {formatted}"

            _logger.info(
                "%s %s → %d %.0fms%s%s",
                method, path, status_code, elapsed * 1000, request_log, response_log,
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    load_settings()
    idle_cleanup_task = asyncio.create_task(
        idle_cleanup_loop(),
        name="model-worker-idle-cleanup",
    )
    try:
        yield
    finally:
        idle_cleanup_task.cancel()
        try:
            await idle_cleanup_task
        except asyncio.CancelledError:
            pass

        cache_manager = get_cache_manager()
        try:
            await asyncio.wait_for(
                cache_manager.worker_stop(stop_all=True),
                timeout=10.0,
            )
        except asyncio.TimeoutError:
            _logger.warning("Timed out while stopping Worker processes; forcing shutdown")
        except Exception:
            _logger.exception("Failed to stop all Worker processes during shutdown")
        finally:
            try:
                await cache_manager.worker_force_stop(stop_all=True)
            except Exception:
                _logger.exception("Failed to force-stop remaining Worker processes during shutdown")


# 创建 FastAPI 应用实例
app = FastAPI(
    title="Qwen3-TTS WebUI",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_exception_handler(APIError, api_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)

# 跨域资源共享中间件：允许前端开发服务器跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],             # 生产环境应限定具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLogMiddleware)


# 挂载各功能模块路由
app.include_router(settings_router.router)
app.include_router(audio_router.router)
app.include_router(synthesis_router.router)
app.include_router(models_router.router)
app.include_router(voices_router.router)
app.include_router(batch_router.router)
app.include_router(worker_router.router)
app.include_router(tracker_router.router)
app.include_router(ws_router.router)

# 生产模式：托管前端静态文件（含 SPA 路由回退）
# 仅在非 reload 模式（非开发模式）下启用，reload 模式由前端 dev server 独立提供
_frontend_dist = _resolve_static_dir()
_is_dev = "--reload" in sys.argv
if not _is_dev and _frontend_dist.is_dir():
    _static_app = StaticFiles(directory=str(_frontend_dist))
    app.mount("/", _static_app, name="static")

    class _SPAMiddleware:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] != "http":
                await self.app(scope, receive, send)
                return

            path = scope.get("path", "")
            if path == "/api" or path.startswith("/api/"):
                await self.app(scope, receive, send)
                return

            index = _frontend_dist / "index.html"
            should_fallback = False

            async def _send(message):
                nonlocal should_fallback
                if (
                    message["type"] == "http.response.start"
                    and message["status"] == 404
                    and index.is_file()
                ):
                    # Swallow the complete original 404 response. Sending the SPA
                    # response here would let the downstream app send its 404 body
                    # afterwards, violating ASGI's one-response-per-request rule.
                    should_fallback = True
                    return
                if should_fallback:
                    return
                await send(message)

            await self.app(scope, receive, _send)
            if should_fallback:
                response = FileResponse(str(index))
                await response(scope, receive, send)

    app.add_middleware(_SPAMiddleware)


def main():
    """CLI 入口：启动 FastAPI 服务器。"""
    import argparse
    import uvicorn

    frozen = getattr(sys, "frozen", False)
    if frozen:
        parser = argparse.ArgumentParser(description="Qwen3-TTS WebUI")
        parser.add_argument("--port", type=int, default=8000)
        parser.add_argument("--no-browser", action="store_true")
        parser.add_argument("--host", default="127.0.0.1")
        args = parser.parse_args()

        def _open_browser() -> None:
            import time
            import webbrowser
            time.sleep(1.5)
            webbrowser.open(f"http://{args.host}:{args.port}")

        if not args.no_browser:
            import threading
            threading.Thread(target=_open_browser, daemon=True).start()
        uvicorn.run(app, host=args.host, port=args.port)
    else:
        uvicorn.run("backend.main:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()

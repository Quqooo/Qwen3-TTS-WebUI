"""WebSocket 路由 — 模型缓存状态、Worker 状态、推理任务状态实时推送"""
import asyncio
import json
import logging
from typing import Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from ..cache import get_cache_manager
from ..config import settings
from ..model_meta import get_model_meta
from ..tracker import get_tracker
from ..branches import discover_branches

_logger = logging.getLogger("qwen-webui.ws")

router = APIRouter(tags=["websocket"])

_connections: Set[WebSocket] = set()
_tracker_broadcast_lock = asyncio.Lock()


def _tracker_status_listener(per_model, inference_total):
    return broadcast_tracker_status(per_model=per_model, inference_total=inference_total)


def _encode(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False)


get_tracker().set_status_listener(_tracker_status_listener)


async def _build_cache_message():
    try:
        cache = get_cache_manager()
        info = await cache.cached_models()
        loaded = [
            {**item, "meta": get_model_meta(item["id"])}
            for item in info["loaded"]
        ]
        return _encode({
            "type": "cache",
            "data": {
                "loaded": loaded,
                "max_concurrent": settings.max_concurrent_models,
                "usage_order": info["usage_order"],
            },
        })
    except RuntimeError:
        return _encode({
            "type": "cache",
            "data": {"loaded": [], "max_concurrent": settings.max_concurrent_models, "usage_order": []},
        })


async def _build_worker_message():
    try:
        cm = get_cache_manager()
        status = await cm.worker_status()
        return _encode({
            "type": "worker",
            "data": status,
        })
    except RuntimeError:
        return _encode({
            "type": "worker",
            "data": {"alive": False, "error": None},
        })


def _build_backend_message():
    """当前选中的后端分支及其可用选项。"""
    return _encode({
        "type": "backend",
        "data": {
            "backend_branch": settings.backend_branch,
            "backend_branch_options": list(discover_branches().keys()),
        },
    })


async def _safe_send(ws: WebSocket, message: str) -> bool:
    """向单个连接发送消息；失败（通常连接已断）返回 False，由调用方清理。

    注意：send_text 失败时 starlette 会把该连接的 application_state 置为
    DISCONNECTED，此副作用无法撤销——后续该连接的 receive_text 会抛
    RuntimeError，由 ws_cache 的状态检查与异常捕获兜底。
    """
    try:
        await ws.send_text(message)
        return True
    except Exception:
        return False


async def _broadcast(message: str):
    if not _connections:
        return
    dead: Set[WebSocket] = set()
    # 快照遍历，避免 ws_cache 的 finally 并发 discard 导致 set 遍历期修改
    for ws in list(_connections):
        if not await _safe_send(ws, message):
            dead.add(ws)
    if dead:
        _connections.difference_update(dead)


async def broadcast_cache_status():
    """向所有已连接客户端推送缓存状态。"""
    if not _connections:
        return
    await _broadcast(await _build_cache_message())


async def broadcast_worker_status():
    """向所有已连接客户端推送 Worker 状态。"""
    if not _connections:
        return
    await _broadcast(await _build_worker_message())


async def broadcast_backend_status():
    """向所有已连接客户端推送当前后端信息。"""
    if not _connections:
        return
    await _broadcast(_build_backend_message())


def _build_tracker_message(
    per_model=None,
    inference_total=None,
):
    tracker = get_tracker()
    if per_model is None:
        per_model = tracker.status()
    if inference_total is None:
        inference_total = tracker.inference_count
    return _encode({
        "type": "tracker",
        "data": {
            "inference_counts": {
                mid: sum(gpu_counts.values()) for mid, gpu_counts in per_model.items()
            },
            "inference_gpus": per_model,
            "inference_total": inference_total,
        },
    })


async def broadcast_tracker_status(*, per_model=None, inference_total=None):
    """向所有已连接客户端推送推理任务状态快照。"""
    if not _connections:
        return
    async with _tracker_broadcast_lock:
        await _broadcast(_build_tracker_message(per_model, inference_total))


@router.websocket("/api/ws/cache")
async def ws_cache(websocket: WebSocket):
    await websocket.accept()
    _connections.add(websocket)

    try:
        await _broadcast(await _build_cache_message())
        await _broadcast(await _build_worker_message())
        await _broadcast(_build_backend_message())
        await _broadcast(_build_tracker_message())

        while True:
            # 状态检查：_broadcast 向本连接 send 失败会把 application_state
            # 置为 DISCONNECTED，此时不应再调用 receive_text（会抛 RuntimeError）
            if websocket.application_state != WebSocketState.CONNECTED:
                break
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                break  # 空闲超时，主动断开
            except (WebSocketDisconnect, RuntimeError):
                break  # 客户端断开 / 状态已被外部置为断开
            if msg == "ping":
                try:
                    await websocket.send_text("pong")
                except Exception:
                    break  # 回 pong 失败，连接已不可用
    except (WebSocketDisconnect, RuntimeError):
        pass  # 兜底：连接失效相关的异常一律按断开处理，避免冒泡成 ASGI 未处理异常
    finally:
        _connections.discard(websocket)
        # 确保连接关闭；可能已被置为 DISCONNECTED，忽略二次异常
        try:
            if websocket.application_state == WebSocketState.CONNECTED:
                await websocket.close()
        except Exception:
            pass

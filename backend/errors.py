"""
标准化错误处理模块

提供统一的 API 错误异常类和 FastAPI 异常处理器。
- detail: 面向用户的错误消息（必须）
- debug:  面向开发者的调试信息（可选）
"""
import json
from typing import Any, List, NoReturn, Optional, Sequence

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def _format_field_name(loc: tuple) -> str:
    parts = [str(p) for p in loc if p not in ("body", "query", "path")]
    return ".".join(parts) if parts else "request"


def _validation_detail(errors: Sequence[Any]) -> str:
    if not errors:
        return "Invalid request"
    msgs: List[str] = []
    for e in errors[:3]:
        loc = _format_field_name(e.get("loc", ()))
        msg = e.get("msg", "invalid value")
        msgs.append(f"{loc}: {msg}")
    joined = "; ".join(msgs)
    if len(errors) > 3:
        joined += f" (+{len(errors) - 3} more)"
    return joined


class APIError(Exception):
    """标准化 API 错误异常"""

    def __init__(
        self,
        status_code: int,
        detail: str,
        debug: Optional[str] = None,
    ):
        self.status_code = status_code
        self.detail = detail
        self.debug = debug or ""


def raise_error(
    status_code: int,
    detail: str,
    debug: Optional[str] = None,
) -> NoReturn:
    """抛出标准化 API 错误"""
    raise APIError(status_code, detail, debug)


async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    """FastAPI 异常处理器：将 APIError 转换为 JSON 响应"""
    body: dict = {"detail": exc.detail}
    if exc.debug:
        body["debug"] = exc.debug
    return JSONResponse(status_code=exc.status_code, content=body)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """将 Pydantic 验证错误转换为标准格式"""
    errors = exc.errors()
    body: dict = {
        "detail": _validation_detail(errors),
        "debug": json.dumps(errors, ensure_ascii=False),
    }
    return JSONResponse(status_code=422, content=body)

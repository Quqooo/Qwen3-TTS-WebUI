"""WebSocket 路由 — 模型缓存状态、Worker 状态、推理任务状态实时推送"""
import asyncio
import json
import logging
from typing import Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..cache import get_cache_manager
from ..config import settings
from ..model_meta import get_model_meta
from ..tracker import get_tracker

_logger = logging.getLogger("qwen-webui.ws")

router = APIRouter(tags=["websocket"])

_connections: Set[WebSocket] = set()


def _encode(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False)


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


async def _broadcast(message: str):
    dead: Set[WebSocket] = set()
    for ws in _connections:
        try:
            await ws.send_text(message)
        except Exception:
            dead.add(ws)
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


async def _build_tracker_message():
    tracker = get_tracker()
    return _encode({
        "type": "tracker",
        "data": {
            "inference_counts": dict(tracker._inference_counts),
            "inference_total": tracker.inference_count,
        },
    })


async def broadcast_tracker_status():
    """向所有已连接客户端推送推理任务状态。"""
    if not _connections:
        return
    await _broadcast(await _build_tracker_message())


@router.websocket("/api/ws/cache")
async def ws_cache(websocket: WebSocket):
    await websocket.accept()
    _connections.add(websocket)

    try:
        await _broadcast(await _build_cache_message())
        await _broadcast(await _build_worker_message())

        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                if msg == "ping":
                    await websocket.send_text("pong")
            except (asyncio.TimeoutError, WebSocketDisconnect):
                break
    except WebSocketDisconnect:
        pass
    finally:
        _connections.discard(websocket)

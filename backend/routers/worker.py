"""
Worker 进程生命周期管理 API 路由

提供启动、停止和查询 Worker 子进程的 REST 接口。
Worker 统一通过 cache.branch 访问，不直接与 WorkerProcess 交互。

多 GPU：start/stop/force-stop 支持在路径末尾指定 GPU 槽位
（如 /api/worker/stop/1），stop 与 force-stop 额外支持 /all。
不指定时按配置的 GPU 优先级顺序启动/停止。
"""
import asyncio
from typing import Optional, Tuple

from fastapi import APIRouter, Depends

from ..branches.base import NotSupportedError
from ..cache import get_cache_manager
from ..config import require_qwen, settings
from ..errors import raise_error
from .ws import broadcast_worker_status

router = APIRouter(prefix="/api", tags=["worker"], dependencies=[Depends(require_qwen)])


def _resolve_target(target: Optional[str], allow_all: bool) -> Tuple[Optional[str], bool]:
    """解析路径中的目标 GPU 槽位，返回 (gpu_id, is_all)"""
    if target is None:
        return None, False
    if target.lower() == "all":
        if not allow_all:
            raise_error(status_code=400, detail="'all' is not supported for this operation")
        return None, True
    if not target.isdigit():
        raise_error(
            status_code=400,
            detail=f"Invalid GPU slot: {target}",
            debug=f"configured GPUs: {settings.gpu_list()}",
        )
    return target, False


@router.get("/worker/status")
async def worker_status():
    """查询 Worker 运行状态（含各 GPU 的 workers 数组）"""
    try:
        cm = get_cache_manager()
        status = await cm.worker_status()
    except NotSupportedError as e:
        raise_error(status_code=400, detail="Operation not supported", debug=str(e))
    except RuntimeError as e:
        raise_error(status_code=503, detail="Worker unavailable", debug=str(e))
    return status


async def _start(target: Optional[str]):
    gpu_id, is_all = _resolve_target(target, allow_all=True)
    try:
        cm = get_cache_manager()
        if is_all:
            for g in settings.gpu_list():
                await cm.worker_start(g)
        else:
            await cm.worker_start(gpu_id)
        asyncio.create_task(broadcast_worker_status())
        return {"status": "started"}
    except NotSupportedError as e:
        raise_error(status_code=400, detail="Operation not supported", debug=str(e))
    except RuntimeError as e:
        raise_error(status_code=503, detail="Worker unavailable", debug=str(e))


@router.post("/worker/start")
async def worker_start():
    """按优先级启动第一个未运行的 Worker"""
    return await _start(None)


@router.post("/worker/start/{target}")
async def worker_start_gpu(target: str):
    """启动指定 GPU 槽位的 Worker（/all 启动全部）"""
    return await _start(target)


async def _stop(target: Optional[str], *, force: bool):
    allow_all = True
    gpu_id, is_all = _resolve_target(target, allow_all)
    try:
        cm = get_cache_manager()
        if force:
            await cm.worker_force_stop(gpu_id, is_all)
            return {"status": "force-stopped"}
        await cm.worker_stop(gpu_id, is_all)
        asyncio.create_task(broadcast_worker_status())
        return {"status": "stopped"}
    except NotSupportedError as e:
        raise_error(status_code=400, detail="Operation not supported", debug=str(e))
    except RuntimeError as e:
        raise_error(status_code=503, detail="Worker unavailable", debug=str(e))


@router.post("/worker/stop")
async def worker_stop():
    """按优先级停止第一个运行中的 Worker（等待推理到达安全边界）"""
    return await _stop(None, force=False)


@router.post("/worker/stop/{target}")
async def worker_stop_gpu(target: str):
    """停止指定 GPU 槽位的 Worker，/all 停止全部"""
    return await _stop(target, force=False)


@router.post("/worker/force-stop")
async def worker_force_stop():
    """按优先级强制停止第一个运行中的 Worker"""
    return await _stop(None, force=True)


@router.post("/worker/force-stop/{target}")
async def worker_force_stop_gpu(target: str):
    """强制停止指定 GPU 槽位的 Worker，/all 强制停止全部"""
    return await _stop(target, force=True)

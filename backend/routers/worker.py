"""
Worker 进程生命周期管理 API 路由

提供启动、停止和查询 Worker 子进程的 REST 接口。
Worker 统一通过 cache.branch 访问，不直接与 WorkerProcess 交互。
"""
import asyncio
from fastapi import APIRouter, Depends

from ..branches.base import NotSupportedError
from ..cache import get_cache_manager
from ..config import require_qwen
from ..errors import raise_error
from .ws import broadcast_worker_status

router = APIRouter(prefix="/api", tags=["worker"], dependencies=[Depends(require_qwen)])


@router.get("/worker/status")
async def worker_status():
    """查询 Worker 运行状态"""
    try:
        cm = get_cache_manager()
        status = await cm.worker_status()
    except NotSupportedError as e:
        raise_error(status_code=400, detail="Operation not supported", debug=str(e))
    except RuntimeError as e:
        raise_error(status_code=503, detail="Worker unavailable", debug=str(e))
    return status


@router.post("/worker/start")
async def worker_start():
    """启动 Worker 子进程（若已运行则为空操作）"""
    try:
        cm = get_cache_manager()
        await cm.worker_start()
        asyncio.create_task(broadcast_worker_status())
        return {"status": "started"}
    except NotSupportedError as e:
        raise_error(status_code=400, detail="Operation not supported", debug=str(e))
    except RuntimeError as e:
        raise_error(status_code=503, detail="Worker unavailable", debug=str(e))


@router.post("/worker/stop")
async def worker_stop():
    """等待推理到达安全边界后停止 Worker 子进程。"""
    try:
        cm = get_cache_manager()
        await cm.worker_stop()
        asyncio.create_task(broadcast_worker_status())
        return {"status": "stopped"}
    except NotSupportedError as e:
        raise_error(status_code=400, detail="Operation not supported", debug=str(e))
    except RuntimeError as e:
        raise_error(status_code=503, detail="Worker unavailable", debug=str(e))


@router.post("/worker/force-stop")
async def worker_force_stop():
    """立即强制终止 Worker 子进程，不等待推理安全边界。"""
    try:
        cm = get_cache_manager()
        await cm.worker_force_stop()
        return {"status": "force-stopped"}
    except NotSupportedError as e:
        raise_error(status_code=400, detail="Operation not supported", debug=str(e))
    except RuntimeError as e:
        raise_error(status_code=503, detail="Worker unavailable", debug=str(e))

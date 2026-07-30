"""推理任务状态查询 API 路由"""
from fastapi import APIRouter

from ..tracker import get_tracker

router = APIRouter(prefix="/api", tags=["tracker"])


@router.get("/tracker/status")
async def tracker_status():
    """返回各模型当前的推理任务数"""
    tracker = get_tracker()
    return {
        "inference_counts": dict(tracker._inference_counts),
        "inference_total": tracker.inference_count,
    }

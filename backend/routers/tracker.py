"""推理任务状态查询 API 路由"""
from fastapi import APIRouter

from ..tracker import get_tracker

router = APIRouter(prefix="/api", tags=["tracker"])


@router.get("/tracker/status")
async def tracker_status():
    """返回各模型当前的推理任务数（含所在 GPU 明细）"""
    tracker = get_tracker()
    per_model = tracker.status()
    return {
        "inference_counts": {
            mid: sum(gpu_counts.values()) for mid, gpu_counts in per_model.items()
        },
        "inference_gpus": per_model,
        "inference_total": tracker.inference_count,
    }

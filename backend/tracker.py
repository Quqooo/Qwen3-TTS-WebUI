"""
推理任务引用计数器

按 模型 × GPU 两个维度跟踪正在进行的推理任务数量，
供缓存淘汰逻辑与多卡负载均衡使用。
"""
import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Dict, Optional

_logger = logging.getLogger("qwen-webui.tracker")


class ModelWorkTracker:
    def __init__(self):
        # model_id -> gpu_id -> 进行中任务数
        self._inference_counts: Dict[str, Dict[str, int]] = {}
        self._inference_total = 0
        self._lock = asyncio.Lock()
        self._status_listener: Optional[
            Callable[[Dict[str, Dict[str, int]], int], Awaitable[None]]
        ] = None

    def set_status_listener(
        self,
        listener: Optional[Callable[[Dict[str, Dict[str, int]], int], Awaitable[None]]],
    ) -> None:
        self._status_listener = listener

    def _schedule_status_broadcast(self) -> None:
        """按本次变更的快照异步推送，避免快速变更被合并。"""
        if self._status_listener is None:
            return
        per_model = self.status()
        inference_total = self._inference_total
        asyncio.create_task(self._status_listener(per_model, inference_total))

    async def acquire_inference(self, model_id: str, gpu: str = "0") -> None:
        async with self._lock:
            per_gpu = self._inference_counts.setdefault(model_id, {})
            per_gpu[gpu] = per_gpu.get(gpu, 0) + 1
            self._inference_total += 1
            self._schedule_status_broadcast()

    async def release_inference(self, model_id: str, gpu: str = "0") -> None:
        async with self._lock:
            per_gpu = self._inference_counts.get(model_id)
            if per_gpu:
                cnt = per_gpu.get(gpu, 0)
                if cnt > 1:
                    per_gpu[gpu] = cnt - 1
                else:
                    per_gpu.pop(gpu, None)
                if not per_gpu:
                    self._inference_counts.pop(model_id, None)
            self._inference_total = max(0, self._inference_total - 1)
            self._schedule_status_broadcast()

    def is_busy(self, model_id: str, gpu: Optional[str] = None) -> bool:
        per_gpu = self._inference_counts.get(model_id)
        if not per_gpu:
            return False
        if gpu is not None:
            return per_gpu.get(gpu, 0) > 0
        return any(cnt > 0 for cnt in per_gpu.values())

    def model_count(self, model_id: str, gpu: Optional[str] = None) -> int:
        """指定模型（可选限定 GPU）进行中的任务数"""
        per_gpu = self._inference_counts.get(model_id)
        if not per_gpu:
            return 0
        if gpu is not None:
            return per_gpu.get(gpu, 0)
        return sum(per_gpu.values())

    def gpu_count(self, gpu: str) -> int:
        """指定 GPU 上所有模型进行中的任务总数"""
        return sum(per_gpu.get(gpu, 0) for per_gpu in self._inference_counts.values())

    async def wait_idle(self, model_id: str, gpu: Optional[str] = None) -> None:
        while self.is_busy(model_id, gpu):
            await asyncio.sleep(0.5)

    async def wait_any_idle(self) -> None:
        await asyncio.sleep(0.5)

    @property
    def inference_count(self) -> int:
        return self._inference_total

    def status(self) -> Dict[str, Dict[str, int]]:
        """返回 {model_id: {gpu_id: count}} 快照"""
        return {mid: dict(per_gpu) for mid, per_gpu in self._inference_counts.items()}


# 全局单例
_tracker: ModelWorkTracker = ModelWorkTracker()


def get_tracker() -> ModelWorkTracker:
    return _tracker

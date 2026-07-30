"""
推理任务引用计数器

跟踪所有模型正在进行的推理任务数量，供缓存淘汰逻辑使用
并发控制由 synthesis.py 的 asyncio.Semaphore 负责。
"""
import asyncio
import logging
from typing import Dict

_logger = logging.getLogger("qwen-webui.tracker")


class ModelWorkTracker:
    def __init__(self):
        self._inference_counts: Dict[str, int] = {}
        self._inference_total = 0
        self._lock = asyncio.Lock()

    async def acquire_inference(self, model_id: str) -> None:
        async with self._lock:
            self._inference_counts[model_id] = self._inference_counts.get(model_id, 0) + 1
            self._inference_total += 1

    async def release_inference(self, model_id: str) -> None:
        async with self._lock:
            cnt = self._inference_counts.get(model_id, 0)
            if cnt > 1:
                self._inference_counts[model_id] = cnt - 1
            else:
                self._inference_counts.pop(model_id, None)
            self._inference_total = max(0, self._inference_total - 1)

    def is_busy(self, model_id: str) -> bool:
        return self._inference_counts.get(model_id, 0) > 0

    async def wait_idle(self, model_id: str) -> None:
        while self.is_busy(model_id):
            await asyncio.sleep(0.5)

    async def wait_any_idle(self) -> None:
        await asyncio.sleep(0.5)

    @property
    def inference_count(self) -> int:
        return self._inference_total


# 全局单例
_tracker: ModelWorkTracker = ModelWorkTracker()


def get_tracker() -> ModelWorkTracker:
    return _tracker

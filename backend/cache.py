"""
统一模型缓存管理模块

集中管理模型的加载、卸载和缓存策略。所有涉及模型生命周期
的操作必须通过此模块进行，确保遵守 max_concurrent_models
限制和 LRU 淘汰策略。

加载/卸载请求通过异步锁串行化处理。

所有公开接口统一使用模型 ID（目录名），ID → 绝对路径的转换
仅在最终传递给 Worker 子进程时完成。
"""
import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional

from .branches import get_branch
from .branches.base import TTSBranch
from .config import resolve_model_path, settings
from .model_meta import cache_model_meta, invalidate_model_meta
from .tracker import get_tracker

_logger = logging.getLogger("qwen-webui.cache")


class ModelCacheManager:
    """统一模型缓存管理器

    职责：
    - 控制模型加载/卸载，遵守 max_concurrent_models 限制
    - LRU 淘汰：缓存满时淘汰最久未使用的模型
    - 空闲超时卸载
    - 与 Worker 子进程中的实际缓存保持同步
    """

    def __init__(self):
        self._cache: Dict[str, float] = {}  # model_id -> last_used (monotonic)
        self._lock = asyncio.Lock()
        self._branch: Optional[TTSBranch] = None
        self._op_lock = asyncio.Lock()  # 串行化加载/卸载操作
        self._empty_since: Optional[float] = None  # Worker 无模型缓存的起始时间

    # ── 内部方法 ─────────────────────────────────────────────

    def _get_branch(self) -> TTSBranch:
        if self._branch is None:
            self._branch = get_branch()
        return self._branch

    @staticmethod
    def _detect_kind(model_id: str) -> str:
        lower = model_id.lower().replace("-", "").replace("_", "")
        if "tokenizer" in lower:
            return "unknown"
        if "customvoice" in lower:
            return "custom_voice"
        if "voicedesign" in lower:
            return "voice_design"
        return "base"

    async def _sync_from_worker(self):
        try:
            branch = self._get_branch()
            loaded = await branch.cached_models()
            loaded_ids = {os.path.basename(p): info for p, info in loaded.items()}
            async with self._lock:
                for mid in list(self._cache):
                    if mid not in loaded_ids:
                        del self._cache[mid]
                for mid, info in loaded_ids.items():
                    if mid not in self._cache:
                        ts = info.get("last_used", 0.0) or time.monotonic()
                        self._cache[mid] = ts
                if self._cache:
                    self._empty_since = None
        except Exception:
            pass

    async def _enforce_max_concurrent(self, reserve_for: Optional[str] = None):
        """尝试淘汰模型，确保缓存不超过上限。"""
        branch = self._get_branch()
        tracker = get_tracker()
        logged = False
        while True:
            async with self._lock:
                if len(self._cache) < settings.max_concurrent_models:
                    return
                if not self._cache:
                    return
                if reserve_for in self._cache and len(self._cache) == 1:
                    return
                sorted_ids = sorted(
                    self._cache.keys(),
                    key=lambda p: 0.0 if p == reserve_for else self._cache.get(p, 0.0),
                )
                lru_id = None
                for mid in sorted_ids:
                    if mid == reserve_for:
                        continue
                    if not tracker.is_busy(mid):
                        lru_id = mid
                        break
                if lru_id is not None:
                    del self._cache[lru_id]
            if lru_id is None:
                if not logged:
                    busy = [mid for mid in sorted_ids if mid != reserve_for]
                    _logger.info("All models busy, waiting: %s", busy)
                    logged = True
                await tracker.wait_any_idle()
                continue
            _logger.info("Evicting LRU model: %s", lru_id)
            try:
                await branch.unload_model(resolve_model_path(lru_id))
            except Exception:
                _logger.warning("Failed to unload %s during eviction", lru_id)
            return

    # ── 公开接口（全部 async） ──────────────────────────────

    async def load_model(
        self, model_id: str, model_kind: str,
        load_kwargs: Optional[Dict[str, Any]] = None,
    ) -> None:
        async with self._op_lock:
            async with self._lock:
                already = model_id in self._cache
            if not already:
                await self._enforce_max_concurrent(reserve_for=model_id)
            branch = self._get_branch()
            model_path = resolve_model_path(model_id)
            await branch.load_model(model_path, model_kind, load_kwargs or {})
            if not already:
                try:
                    meta = await branch.get_supported_options(model_path)
                    cache_model_meta(model_id, meta)
                except Exception:
                    _logger.warning("Failed to fetch model meta for %s", model_id)
            async with self._lock:
                self._cache[model_id] = time.monotonic()
                self._empty_since = None
                if not already:
                    _logger.info(
                        "Model loaded: %s (cache: %d/%d)",
                        model_id, len(self._cache), settings.max_concurrent_models,
                    )
                else:
                    _logger.debug("Model already cached: %s", model_id)

    async def unload_model(self, model_id: str) -> None:
        async with self._op_lock:
            await get_tracker().wait_idle(model_id)
            async with self._lock:
                self._cache.pop(model_id, None)
            try:
                branch = self._get_branch()
                await branch.unload_model(resolve_model_path(model_id))
            except Exception:
                pass
            async with self._lock:
                if not self._cache:
                    self._empty_since = time.monotonic()
            invalidate_model_meta(model_id)

    async def touch_model(self, model_id: str) -> None:
        async with self._lock:
            if model_id in self._cache:
                self._cache[model_id] = time.monotonic()

    async def unload_idle(self, max_idle_seconds: float) -> List[str]:
        async with self._op_lock:
            now = time.monotonic()
            async with self._lock:
                candidates = [
                    mid for mid, last_used in self._cache.items()
                    if now - last_used > max_idle_seconds
                ]
            tracker = get_tracker()
            branch = self._get_branch()
            unloaded: List[str] = []
            for mid in candidates:
                await tracker.wait_idle(mid)
                # 推理结束时 touch_model() 可能已刷新 last_used；等待期间必须
                # 重新检查，避免把刚结束推理的模型立刻卸载。
                async with self._lock:
                    last_used = self._cache.get(mid)
                    if last_used is None or time.monotonic() - last_used <= max_idle_seconds:
                        continue
                try:
                    await branch.unload_model(resolve_model_path(mid))
                except Exception:
                    continue
                async with self._lock:
                    self._cache.pop(mid, None)
                unloaded.append(mid)
                invalidate_model_meta(mid)
                _logger.info("Idle unload: %s", mid)
            if unloaded:
                async with self._lock:
                    if not self._cache:
                        self._empty_since = time.monotonic()
            return unloaded

    async def cached_models(self) -> Dict[str, Any]:
        await self._sync_from_worker()
        async with self._lock:
            sorted_ids = sorted(
                self._cache.keys(),
                key=lambda p: self._cache.get(p, 0.0),
                reverse=True,
            )
            loaded_list = [
                {"id": mid, "kind": self._detect_kind(mid), "last_used": self._cache.get(mid, 0.0)}
                for mid in sorted_ids
            ]
            return {
                "loaded": loaded_list,
                "max_concurrent": settings.max_concurrent_models,
                "usage_order": sorted_ids,
            }

    async def clear(self) -> None:
        async with self._op_lock:
            async with self._lock:
                model_ids = list(self._cache)
            tracker = get_tracker()
            branch = self._get_branch()
            for mid in model_ids:
                await tracker.wait_idle(mid)
                try:
                    await branch.unload_model(resolve_model_path(mid))
                except Exception:
                    pass
            async with self._lock:
                self._cache.clear()
                self._empty_since = time.monotonic()

    async def worker_start(self) -> None:
        await self._get_branch().worker_start()
        async with self._lock:
            if not self._cache:
                self._empty_since = time.monotonic()
        from .routers.ws import broadcast_worker_status
        asyncio.create_task(broadcast_worker_status())

    async def worker_stop(self) -> None:
        async with self._op_lock:
            async with self._lock:
                model_ids = list(self._cache.keys())
            if model_ids:
                branch = self._get_branch()
                tracker = get_tracker()
                for mid in model_ids:
                    await tracker.wait_idle(mid)
                    try:
                        await branch.unload_model(resolve_model_path(mid))
                    except Exception:
                        pass
                    invalidate_model_meta(mid)
            async with self._lock:
                self._cache.clear()
                self._empty_since = None
            await self._get_branch().worker_stop()
        from .routers.ws import broadcast_worker_status
        asyncio.create_task(broadcast_worker_status())

    async def _worker_force_stop_locked(self) -> None:
        """在持有 _op_lock 时强停 Worker 并清除缓存状态。"""
        async with self._lock:
            model_ids = list(self._cache.keys())
            self._cache.clear()
            self._empty_since = None
        for mid in model_ids:
            invalidate_model_meta(mid)
        await self._get_branch().worker_force_stop()

    async def worker_force_stop(self) -> None:
        """立即终止 Worker，并清除服务端缓存状态。"""
        # 不等待 _op_lock：强停必须能够打断正在加载/推理的 Worker。
        branch = self._get_branch()
        await branch.worker_force_stop()
        async with self._op_lock:
            # 若已有加载请求排在操作锁队列中，它可能在首次强停后重启
            # Worker；进入锁后再强停一次，确保返回时一定已停止。
            await branch.worker_force_stop()
            async with self._lock:
                model_ids = list(self._cache.keys())
                self._cache.clear()
                self._empty_since = None
            for mid in model_ids:
                invalidate_model_meta(mid)
        from .routers.ws import broadcast_cache_status, broadcast_worker_status
        asyncio.create_task(broadcast_cache_status())
        asyncio.create_task(broadcast_worker_status())

    async def cleanup_idle(self, max_idle_seconds: float) -> Dict[str, Any]:
        """卸载闲置模型，并在缓存持续为空达到阈值后强停 Worker。"""
        unloaded = await self.unload_idle(max_idle_seconds)
        worker_force_stopped = False

        # 与模型加载/卸载共用操作锁，防止空缓存检查后有新模型加载，
        # 却仍将刚加载完成的 Worker 误杀。
        async with self._op_lock:
            status = await self._get_branch().worker_status()
            now = time.monotonic()
            async with self._lock:
                if not status.get("alive"):
                    self._empty_since = None
                    empty_for = 0.0
                elif self._cache:
                    self._empty_since = None
                    empty_for = 0.0
                else:
                    if self._empty_since is None:
                        self._empty_since = now
                    empty_for = now - self._empty_since

            if status.get("alive") and empty_for >= max_idle_seconds:
                _logger.info(
                    "Worker cache stayed empty for %.1fs; force stopping Worker",
                    empty_for,
                )
                await self._worker_force_stop_locked()
                worker_force_stopped = True

        return {
            "unloaded": unloaded,
            "worker_force_stopped": worker_force_stopped,
        }

    async def worker_status(self) -> Dict[str, Any]:
        return await self._get_branch().worker_status()

    @property
    def branch(self) -> TTSBranch:
        return self._get_branch()


_cache_manager: Optional[ModelCacheManager] = None


def get_cache_manager() -> ModelCacheManager:
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = ModelCacheManager()
    return _cache_manager


async def idle_cleanup_loop(check_interval_seconds: float = 30.0) -> None:
    """定期卸载闲置模型，并在缓存持续为空后强制停止 Worker。"""
    while True:
        await asyncio.sleep(check_interval_seconds)
        try:
            result = await get_cache_manager().cleanup_idle(
                float(settings.idle_unload_seconds)
            )
            if result["unloaded"]:
                from .routers.ws import broadcast_cache_status
                await broadcast_cache_status()
            if result["worker_force_stopped"]:
                from .routers.ws import broadcast_cache_status, broadcast_worker_status
                await broadcast_cache_status()
                await broadcast_worker_status()
                _logger.info("Idle cleanup force-stopped the Worker")
        except asyncio.CancelledError:
            raise
        except Exception:
            _logger.exception("Idle cleanup cycle failed")

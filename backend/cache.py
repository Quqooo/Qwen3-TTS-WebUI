"""
统一模型缓存管理模块（多 GPU 版）

集中管理模型的加载、卸载和缓存策略。所有涉及模型生命周期
的操作必须通过此模块进行。

多卡模型：
- 每 GPU 一个 Worker 子进程（由分支的 WorkerPool 管理）
- 缓存按 模型 × GPU 记录实例，max_concurrent_models 为每 GPU
  可加载的不同模型数上限（同一 GPU 不允许重复实例）
- 加载模型按配置的 GPU 优先级选择空 GPU → 未满 GPU →
  失败降级 → LRU 淘汰（按 Worker 分桶）
- 推理请求通过 acquire_model() 分配实例：优先空闲实例/空闲 GPU，
  无空闲实例时自动并行加载新实例，最终均分任务队列
- 模型空闲超时按实例记录；Worker 空闲超时各自独立
"""
import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from .branches import get_branch
from .branches.base import TTSBranch
from .branches.worker_pool import WorkerPool
from .config import resolve_model_path, settings
from .model_meta import cache_model_meta, detect_kind_from_config, invalidate_model_meta
from .tracker import get_tracker

_logger = logging.getLogger("qwen-webui.cache")


class ModelLease:
    """一次推理分配到的模型实例租约（模型 × GPU）。

    租约持有期间，实例的推理计数（WorkerPool 与 Tracker）保持 +1；
    释放后可选择先等待推理到达安全边界（流式中断场景）。
    """

    def __init__(self, manager: "ModelCacheManager", model_id: str, model_path: str, gpu: str):
        self._manager = manager
        self.model_id = model_id
        self.model_path = model_path
        self.gpu = gpu
        self._released = False

    @property
    def worker(self):
        return self._manager.pool.worker_for_gpu(self.gpu)

    async def wait_stoppable(self) -> None:
        try:
            await self._manager.branch.wait_model_stoppable(self.model_path, gpu_id=self.gpu)
        except Exception:
            _logger.debug("wait_stoppable failed for %s on GPU %s", self.model_id, self.gpu, exc_info=True)

    async def release(self, *, wait_stoppable: bool = False) -> None:
        if self._released:
            return
        self._released = True
        if wait_stoppable:
            await self.wait_stoppable()
        self._manager.pool.mark_release(self.model_path, self.gpu)
        await get_tracker().release_inference(self.model_id, self.gpu)


class ModelCacheManager:
    """统一模型缓存管理器（多 GPU）

    职责：
    - 控制模型加载/卸载，遵守每 GPU max_concurrent_models 限制
    - GPU 优先级放置与失败降级、按 Worker 分桶的 LRU 淘汰
    - 推理请求实例分配（acquire_model → ModelLease）
    - 模型实例空闲超时卸载、Worker 空闲超时停止
    """

    def __init__(self):
        # model_id -> {gpu_id: last_used (monotonic)}
        self._cache: Dict[str, Dict[str, float]] = {}
        self._kinds: Dict[str, str] = {}  # model_id -> kind
        self._lock = asyncio.Lock()
        self._branch: Optional[TTSBranch] = None
        self._op_lock = asyncio.Lock()  # 串行化加载/卸载/分配操作

    # ── 内部方法 ─────────────────────────────────────────────

    def _get_branch(self) -> TTSBranch:
        if self._branch is None:
            self._branch = get_branch()
        return self._branch

    @property
    def pool(self) -> WorkerPool:
        branch = self._get_branch()
        pool = getattr(branch, "pool", None)
        if pool is None:
            raise RuntimeError(f"Branch {branch.name} does not support GPU worker pool")
        return pool

    @staticmethod
    def _detect_kind(model_id: str) -> str:
        # 优先读取 config.json 的 tts_model_type 键；无法确定时按目录名猜测
        kind = detect_kind_from_config(model_id)
        if kind:
            return kind
        lower = model_id.lower().replace("-", "").replace("_", "")
        if "tokenizer" in lower:
            return "unknown"
        if "customvoice" in lower:
            return "custom_voice"
        if "voicedesign" in lower:
            return "voice_design"
        return "base"

    def _kind_of(self, model_id: str) -> str:
        return self._kinds.get(model_id) or self._detect_kind(model_id)

    def _last_used(self, model_id: str, gpu: str) -> float:
        return self._cache.get(model_id, {}).get(gpu, 0.0)

    def _gpu_kind_compatible(self, model_paths, kind: str) -> bool:
        """GPU 上已有模型是否全部与该模型同 kind（混 kind 同卡允许但优先级最低）"""
        for path in model_paths:
            if self._kind_of(os.path.basename(path)) != kind:
                return False
        return True

    def _gpu_candidates_locked(self, model_path: str, kind: str) -> List[str]:
        """可加载该模型的候选 GPU（按优先级）。

        跳过已加载相同模型的 GPU。候选分三档，依次尝试：
        1. 空 GPU（无模型）
        2. 未满且已有模型均为同 kind 的 GPU
        3. 未满但混 kind 的 GPU（允许混载，但优先级最低）
        2/3 档均需 max_concurrent_models > 1。
        """
        pool = self.pool
        assigned = set(pool.model_gpus(model_path))
        empty: List[str] = []
        same_kind: List[str] = []
        mixed_kind: List[str] = []
        for gpu in settings.gpu_list():
            if gpu in assigned:
                continue
            models = pool.gpu_models(gpu)
            if not models:
                empty.append(gpu)
            elif len(models) < settings.max_concurrent_models:
                if self._gpu_kind_compatible(models, kind):
                    same_kind.append(gpu)
                else:
                    mixed_kind.append(gpu)
        return empty + same_kind + mixed_kind

    async def _register_instance(self, model_id: str, kind: str, gpu: str, *, is_new_model: bool) -> None:
        async with self._lock:
            self._cache.setdefault(model_id, {})[gpu] = time.monotonic()
            self._kinds[model_id] = kind
        if is_new_model:
            try:
                model_path = resolve_model_path(model_id)
                meta = await self._get_branch().get_supported_options(model_path)
                cache_model_meta(model_id, meta)
            except Exception:
                _logger.warning("Failed to fetch model meta for %s", model_id)

    async def _load_on_gpu(self, model_id: str, kind: str, model_path: str,
                           gpu: str, load_kwargs: Optional[Dict[str, Any]]) -> None:
        is_new = model_id not in self._cache
        await self._get_branch().load_model(model_path, kind, load_kwargs or {}, gpu_id=gpu)
        await self._register_instance(model_id, kind, gpu, is_new_model=is_new)
        _logger.info(
            "Model loaded: %s on GPU %s (instances: %d)",
            model_id, gpu, len(self._cache.get(model_id, {})),
        )

    async def _evict_lru_on_gpu(self, gpu: str, reserve_for: Optional[str] = None) -> bool:
        """淘汰指定 GPU 上最久未使用的空闲模型实例，返回是否成功淘汰。

        仅淘汰完全空闲（Tracker 与 WorkerPool 计数均为 0）的实例，
        绝不强制卸载正在推理的模型。
        """
        pool = self.pool
        tracker = get_tracker()
        models = sorted(
            pool.gpu_models(gpu),
            key=lambda p: self._last_used(os.path.basename(p), gpu),
        )
        for path in models:
            model_id = os.path.basename(path)
            if model_id == reserve_for:
                continue
            if tracker.is_busy(model_id, gpu):
                continue
            if pool.instance_inflight(path, gpu) > 0:
                continue
            _logger.info("Evicting LRU model on GPU %s: %s", gpu, model_id)
            await self._unload_instance(model_id, path, gpu)
            return True
        return False

    async def _unload_instance(self, model_id: str, model_path: str, gpu: str) -> None:
        tracker = get_tracker()
        await tracker.wait_idle(model_id, gpu)
        pool = self.pool
        while pool.instance_inflight(model_path, gpu) > 0:
            await asyncio.sleep(0.2)
        try:
            await self._get_branch().unload_model(model_path, gpu_id=gpu)
        except Exception:
            _logger.warning("Failed to unload %s on GPU %s", model_id, gpu)
        async with self._lock:
            instances = self._cache.get(model_id)
            if instances is not None:
                instances.pop(gpu, None)
                if not instances:
                    self._cache.pop(model_id, None)
                    self._kinds.pop(model_id, None)
                    invalidate_model_meta(model_id)

    async def _load_locked(self, model_id: str, kind: str,
                           load_kwargs: Optional[Dict[str, Any]], *,
                           evict: bool) -> Optional[str]:
        """在最佳 GPU 加载模型实例（须持有 _op_lock）。

        依次尝试：空 GPU → 未满 GPU（候选按优先级）→（evict=True 时）
        按优先级逐 GPU 淘汰空闲 LRU 模型后重试。
        淘汰只针对空闲模型，绝不强制卸载推理中的模型；
        无可淘汰且仍有推理任务时，忙等待旧模型推理完成后再试，
        而不是直接返回失败。返回目标 gpu_id 或 None。
        """
        pool = self.pool
        model_path = resolve_model_path(model_id)
        candidates = self._gpu_candidates_locked(model_path, kind)
        errors: List[str] = []
        for gpu in candidates:
            try:
                await self._load_on_gpu(model_id, kind, model_path, gpu, load_kwargs)
                return gpu
            except Exception as exc:
                errors.append(f"GPU {gpu}: {exc}")
                _logger.warning("Load %s on GPU %s failed: %s", model_id, gpu, exc)
        if not evict:
            if errors:
                _logger.debug("Parallel instance load of %s skipped: %s", model_id, "; ".join(errors))
            return None
        # LRU 淘汰路径（忙等待）
        tracker = get_tracker()
        assigned = set(pool.model_gpus(model_path))
        waiting_logged = False
        while True:
            for gpu in settings.gpu_list():
                if gpu in assigned:
                    continue
                try:
                    evicted = await self._evict_lru_on_gpu(gpu, reserve_for=model_id)
                except Exception:
                    evicted = False
                if not evicted:
                    continue
                try:
                    await self._load_on_gpu(model_id, kind, model_path, gpu, load_kwargs)
                    return gpu
                except Exception as exc:
                    errors.append(f"GPU {gpu} (after eviction): {exc}")
                    _logger.warning("Load %s on GPU %s after eviction failed: %s", model_id, gpu, exc)
            if tracker.inference_count <= 0 and not pool.any_inflight():
                break
            if not waiting_logged:
                _logger.info(
                    "All GPUs full and models busy; waiting for inference to finish before loading %s",
                    model_id,
                )
                waiting_logged = True
            await tracker.wait_any_idle()
        if errors:
            _logger.error("Failed to load %s on all GPUs: %s", model_id, "; ".join(errors))
        else:
            _logger.error("Failed to load %s: no GPU capacity and no evictable idle model", model_id)
        return None

    async def _wait_instance_idle(self, model_id: str, model_path: str, gpu: str) -> None:
        await get_tracker().wait_idle(model_id, gpu)
        pool = self.pool
        while pool.instance_inflight(model_path, gpu) > 0:
            await asyncio.sleep(0.2)

    async def _sync_from_pool(self) -> None:
        """与 WorkerPool 的实例分布对齐本地缓存记录。"""
        try:
            pool = self.pool
            await pool.resync()
            async with self._lock:
                for model_id in list(self._cache):
                    model_path = resolve_model_path(model_id)
                    actual = set(pool.model_gpus(model_path))
                    instances = self._cache[model_id]
                    for gpu in list(instances):
                        if gpu not in actual:
                            del instances[gpu]
                    for gpu in actual:
                        if gpu not in instances:
                            instances[gpu] = time.monotonic()
                    if not instances:
                        del self._cache[model_id]
                        self._kinds.pop(model_id, None)
                        invalidate_model_meta(model_id)
        except Exception:
            pass

    # ── 公开接口（全部 async） ──────────────────────────────

    async def load_model(
        self, model_id: str, model_kind: str,
        load_kwargs: Optional[Dict[str, Any]] = None,
    ) -> None:
        """确保模型至少有一个实例加载（不存在时按 GPU 优先级加载）。"""
        async with self._op_lock:
            model_path = resolve_model_path(model_id)
            if self.pool.model_gpus(model_path):
                await self.touch_model(model_id)
                return
            gpu = await self._load_locked(model_id, model_kind, load_kwargs, evict=True)
            if gpu is None:
                raise RuntimeError(f"Failed to load model on any GPU: {model_id}")

    async def acquire_model(
        self, model_id: str, model_kind: str,
        load_kwargs: Optional[Dict[str, Any]] = None,
    ) -> ModelLease:
        """为一次推理请求分配模型实例（多卡自动并行）。

        分配策略：
        1. 存在空闲实例 → 优先空闲 GPU（整卡无任务）上的空闲实例
        2. 全部实例忙碌 → 尝试在空闲/未满 GPU 并行加载新实例
        3. 无法再加载 → 均分任务队列（选择任务数最少的实例）
        """
        async with self._op_lock:
            pool = self.pool
            model_path = resolve_model_path(model_id)
            if not pool.model_gpus(model_path):
                gpu = await self._load_locked(model_id, model_kind, load_kwargs, evict=True)
                if gpu is None:
                    raise RuntimeError(f"Failed to load model on any GPU: {model_id}")
            elif not pool.has_idle_instance(model_path):
                # 并行加载新实例失败时静默降级为排队均分
                try:
                    await self._load_locked(model_id, model_kind, load_kwargs, evict=False)
                except Exception:
                    _logger.debug("Parallel instance load failed for %s", model_id, exc_info=True)
            gpu = pool.pick_instance(model_path)
            if gpu is None:
                raise RuntimeError(f"Model not loaded: {model_id}")
            pool.mark_acquire(model_path, gpu)
            await get_tracker().acquire_inference(model_id, gpu)
            return ModelLease(self, model_id, model_path, gpu)

    async def unload_model(self, model_id: str, gpu: Optional[str] = None) -> None:
        """卸载模型；gpu 指定时仅卸载该实例，否则卸载全部实例。"""
        async with self._op_lock:
            model_path = resolve_model_path(model_id)
            async with self._lock:
                gpus = list(self._cache.get(model_id, {}).keys())
            if gpu is not None:
                gpus = [g for g in gpus if g == gpu]
                # 缓存中无记录但 Worker 可能仍持有（同步偏差），照常下发卸载
                if not gpus:
                    gpus = [gpu]
            for g in gpus:
                await self._wait_instance_idle(model_id, model_path, g)
                await self._unload_instance(model_id, model_path, g)

    async def touch_model(self, model_id: str, gpu: Optional[str] = None) -> None:
        """刷新模型实例的使用时间（Base 模型的音色保存/解析同样视为使用）。"""
        async with self._lock:
            instances = self._cache.get(model_id)
            if not instances:
                return
            now = time.monotonic()
            if gpu is not None and gpu in instances:
                instances[gpu] = now
            elif gpu is None:
                for g in instances:
                    instances[g] = now

    async def unload_idle(self, max_idle_seconds: float) -> List[Dict[str, str]]:
        """卸载空闲超时的模型实例，返回 [{"id": ..., "gpu": ...}]。"""
        async with self._op_lock:
            now = time.monotonic()
            async with self._lock:
                candidates = [
                    (mid, g) for mid, instances in self._cache.items()
                    for g, last_used in instances.items()
                    if now - last_used > max_idle_seconds
                ]
            tracker = get_tracker()
            pool = self.pool
            unloaded: List[Dict[str, str]] = []
            for mid, gpu in candidates:
                model_path = resolve_model_path(mid)
                await tracker.wait_idle(mid, gpu)
                while pool.instance_inflight(model_path, gpu) > 0:
                    await asyncio.sleep(0.2)
                # 等待期间推理结束可能已刷新 last_used，必须重新检查
                async with self._lock:
                    last_used = self._cache.get(mid, {}).get(gpu)
                    if last_used is None or time.monotonic() - last_used <= max_idle_seconds:
                        continue
                await self._unload_instance(mid, model_path, gpu)
                if mid not in self._cache or gpu not in self._cache.get(mid, {}):
                    unloaded.append({"id": mid, "gpu": gpu})
                    _logger.info("Idle unload: %s (GPU %s)", mid, gpu)
            return unloaded

    async def cached_models(self) -> Dict[str, Any]:
        await self._sync_from_pool()
        async with self._lock:
            entries = [
                {"id": mid, "gpu": gpu, "kind": self._kind_of(mid), "last_used": last_used}
                for mid, instances in self._cache.items()
                for gpu, last_used in instances.items()
            ]
        entries.sort(key=lambda e: e["last_used"], reverse=True)
        return {
            "loaded": entries,
            "max_concurrent": settings.max_concurrent_models,
            "usage_order": [{"id": e["id"], "gpu": e["gpu"]} for e in entries],
        }

    async def pick_loaded_instance(self, kind: str) -> Optional[Tuple[str, str]]:
        """在已加载的指定 kind 模型中选择实例，返回 (model_id, gpu)。

        优先空闲 GPU 上的空闲实例，其次空闲实例，最后任务数最少的实例。
        """
        pool = self.pool
        candidates: List[Tuple[str, str, str]] = []  # (model_id, model_path, gpu)
        async with self._lock:
            snapshot = {mid: list(instances) for mid, instances in self._cache.items()}
        for mid, gpus in snapshot.items():
            if self._kind_of(mid) != kind:
                continue
            try:
                model_path = resolve_model_path(mid)
            except ValueError:
                continue
            for gpu in pool.model_gpus(model_path):
                candidates.append((mid, model_path, gpu))
        if not candidates:
            return None
        idle = [c for c in candidates if pool.instance_inflight(c[1], c[2]) == 0]
        if idle:
            gpu_idle = [c for c in idle if pool.gpu_inflight(c[2]) == 0]
            best = gpu_idle or idle
            best.sort(key=lambda c: pool._priority_index(c[2]))
            return best[0][0], best[0][2]
        best = min(candidates, key=lambda c: (pool.instance_inflight(c[1], c[2]), pool._priority_index(c[2])))
        return best[0], best[2]

    async def enforce_max_concurrent(self) -> List[Dict[str, str]]:
        """max_concurrent_models 调低后，淘汰超出上限的实例（LRU 优先）。"""
        pool = self.pool
        tracker = get_tracker()
        evicted: List[Dict[str, str]] = []

        async def _unload_when_idle(mid: str, path: str, gpu: str) -> None:
            async with self._op_lock:
                await self._wait_instance_idle(mid, path, gpu)
                # 等待期间上限可能已被调高：该 GPU 实例数不再超限则放弃卸载。
                # 检查与卸载共用 _op_lock，多个后台任务串行执行，不会过度淘汰。
                if len(pool.gpu_models(gpu)) <= settings.max_concurrent_models:
                    _logger.debug("Max_concurrent raised; skip unload of %s (GPU %s)", mid, gpu)
                    return
                await self._unload_instance(mid, path, gpu)
            _logger.info("Evicted for max_concurrent: %s (GPU %s)", mid, gpu)

        async with self._op_lock:
            for gpu in settings.gpu_list():
                models = sorted(
                    pool.gpu_models(gpu),
                    key=lambda p: self._last_used(os.path.basename(p), gpu),
                )
                while len(models) > settings.max_concurrent_models:
                    path = models.pop(0)
                    mid = os.path.basename(path)
                    if tracker.is_busy(mid, gpu) or pool.instance_inflight(path, gpu) > 0:
                        asyncio.create_task(_unload_when_idle(mid, path, gpu))
                    else:
                        await self._unload_instance(mid, path, gpu)
                        evicted.append({"id": mid, "gpu": gpu})
                        _logger.info("Evicted for max_concurrent: %s (GPU %s)", mid, gpu)
        return evicted

    async def clear(self) -> None:
        async with self._op_lock:
            async with self._lock:
                entries = [
                    (mid, g) for mid, instances in self._cache.items() for g in instances
                ]
            for mid, gpu in entries:
                model_path = resolve_model_path(mid)
                await self._wait_instance_idle(mid, model_path, gpu)
                await self._unload_instance(mid, model_path, gpu)

    # ── Worker 生命周期 ──────────────────────────────────────

    async def worker_start(self, gpu_id: Optional[str] = None) -> None:
        await self._get_branch().worker_start(gpu_id)
        from .routers.ws import broadcast_worker_status
        asyncio.create_task(broadcast_worker_status())

    async def worker_stop(self, gpu_id: Optional[str] = None, stop_all: bool = False) -> None:
        branch = self._get_branch()
        async with self._op_lock:
            pool = self.pool
            if stop_all:
                targets = [g for g, w in pool.workers.items() if w.alive]
            elif gpu_id is not None:
                targets = [gpu_id]
            else:
                target = pool.first_alive_gpu()
                targets = [target] if target is not None else []
            for g in targets:
                for path in list(pool.gpu_models(g)):
                    mid = os.path.basename(path)
                    await self._wait_instance_idle(mid, path, g)
                    await self._unload_instance(mid, path, g)
                await branch.worker_stop(g)
        from .routers.ws import broadcast_cache_status, broadcast_worker_status
        asyncio.create_task(broadcast_cache_status())
        asyncio.create_task(broadcast_worker_status())

    async def worker_force_stop(self, gpu_id: Optional[str] = None, stop_all: bool = False) -> None:
        """立即终止 Worker，并清除服务端缓存状态。"""
        branch = self._get_branch()
        pool = self.pool
        # 先确定目标：stop_all 为全部，否则为指定 GPU 或按优先级第一个运行中的
        if stop_all:
            targets: Optional[set] = None  # None 表示全部
        else:
            target = gpu_id or pool.first_alive_gpu()
            targets = {target} if target is not None else set()
        # 不等待 _op_lock：强停必须能够打断正在加载/推理的 Worker。
        await branch.worker_force_stop(gpu_id, stop_all)
        async with self._op_lock:
            # 若已有加载请求排在操作锁队列中，它可能在首次强停后重启
            # Worker；进入锁后再强停一次，确保返回时一定已停止。
            await branch.worker_force_stop(gpu_id, stop_all)
            async with self._lock:
                for mid in list(self._cache):
                    if targets is None:
                        del self._cache[mid]
                        self._kinds.pop(mid, None)
                        invalidate_model_meta(mid)
                        continue
                    instances = self._cache[mid]
                    for g in list(instances):
                        if g in targets:
                            del instances[g]
                    if not instances:
                        del self._cache[mid]
                        self._kinds.pop(mid, None)
                        invalidate_model_meta(mid)
        from .routers.ws import broadcast_cache_status, broadcast_worker_status
        asyncio.create_task(broadcast_cache_status())
        asyncio.create_task(broadcast_worker_status())

    async def cleanup_idle(self, model_idle_seconds: float, worker_idle_seconds: float) -> Dict[str, Any]:
        """卸载闲置模型实例，并停止空闲超时的无模型 Worker。

        超时值 <= 0 表示禁用对应的自动清理（模型卸载 / Worker 停止）。
        """
        unloaded: List[Dict[str, str]] = []
        if model_idle_seconds > 0:
            unloaded = await self.unload_idle(model_idle_seconds)
        workers_stopped: List[str] = []

        if worker_idle_seconds > 0:
            # 与模型加载/卸载共用操作锁，防止检查后有新模型加载，
            # 却仍将刚加载完成的 Worker 误杀。
            async with self._op_lock:
                pool = self.pool
                for gpu in pool.idle_worker_gpus(worker_idle_seconds):
                    _logger.info("Worker (GPU %s) idle for too long; force stopping", gpu)
                    await self._get_branch().worker_force_stop(gpu_id=gpu)
                    workers_stopped.append(gpu)

        return {
            "unloaded": unloaded,
            "workers_stopped": workers_stopped,
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
    """定期卸载闲置模型实例，并停止空闲超时的 Worker。"""
    while True:
        await asyncio.sleep(check_interval_seconds)
        try:
            result = await get_cache_manager().cleanup_idle(
                float(settings.idle_unload_seconds),
                float(settings.worker_idle_unload_seconds),
            )
            if result["unloaded"]:
                from .routers.ws import broadcast_cache_status
                await broadcast_cache_status()
            if result["workers_stopped"]:
                from .routers.ws import broadcast_cache_status, broadcast_worker_status
                await broadcast_cache_status()
                await broadcast_worker_status()
                _logger.info("Idle cleanup stopped workers: %s", result["workers_stopped"])
        except asyncio.CancelledError:
            raise
        except Exception:
            _logger.exception("Idle cleanup cycle failed")

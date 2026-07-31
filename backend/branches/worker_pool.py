"""Worker 进程池 — 每 GPU 一个 Worker 子进程，负责生命周期管理与请求路由。

池本身不感知模型加载命令的细节（由 Branch 负责构建协议命令），
只维护三类状态：
- workers:      gpu_id -> WorkerProcess（子进程生命周期）
- assignments:  model_path -> {gpu_id}（模型实例分布，同一 GPU 不允许重复实例）
- inflight:     推理任务计数（GPU 维度与模型实例维度），供负载均衡路由

所有计数操作均为同步原语（单事件循环内无并发问题），
进程生命周期操作通过 asyncio.Lock 串行化。
"""
import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from ..config import settings
from .worker_client import WorkerProcess


class WorkerPool:
    def __init__(self, provider_file: str, logger: Optional[logging.Logger] = None):
        self._provider_file = provider_file
        self._logger = logger or logging.getLogger("qwen-webui.worker-pool")
        self._workers: Dict[str, WorkerProcess] = {}
        self._lock = asyncio.Lock()
        self._assignments: Dict[str, Set[str]] = {}
        self._gpu_inflight: Dict[str, int] = {}
        self._inst_inflight: Dict[Tuple[str, str], int] = {}

    # ── 基础查询 ──────────────────────────────────────────────

    @staticmethod
    def gpu_priority() -> List[str]:
        """按优先级排序的 GPU 列表（每次实时读取配置）"""
        return settings.gpu_list()

    def _priority_index(self, gpu_id: str) -> int:
        try:
            return self.gpu_priority().index(gpu_id)
        except ValueError:
            return len(self.gpu_priority())

    def _by_priority(self, gpu_ids) -> List[str]:
        return sorted(gpu_ids, key=self._priority_index)

    @property
    def workers(self) -> Dict[str, WorkerProcess]:
        return dict(self._workers)

    def worker_for_gpu(self, gpu_id: str) -> Optional[WorkerProcess]:
        w = self._workers.get(gpu_id)
        return w if w is not None and w.alive else None

    def any_alive_worker(self) -> Optional[WorkerProcess]:
        for gpu_id in self._by_priority(self._workers.keys()):
            w = self.worker_for_gpu(gpu_id)
            if w is not None:
                return w
        return None

    # ── 生命周期 ──────────────────────────────────────────────

    async def ensure_worker(self, gpu_id: str) -> WorkerProcess:
        """返回指定 GPU 的存活 Worker，必要时启动；失败抛 RuntimeError。"""
        async with self._lock:
            w = self._workers.get(gpu_id)
            if w is not None and w.alive:
                return w
            w = WorkerProcess(self._provider_file, self._logger, gpu_id=gpu_id)
            started = await w.start()
            self._workers[gpu_id] = w
            if started:
                from ..routers.ws import broadcast_worker_status
                asyncio.create_task(broadcast_worker_status())
            elif w.error:
                raise RuntimeError(f"Worker (GPU {gpu_id}) unavailable: {w.error}")
            return w

    async def start_next(self) -> Optional[str]:
        """按优先级启动第一个未运行的 GPU Worker，返回其 gpu_id；全部运行中则返回 None。"""
        for gpu_id in self.gpu_priority():
            if self.worker_for_gpu(gpu_id) is None:
                await self.ensure_worker(gpu_id)
                return gpu_id
        return None

    def first_alive_gpu(self) -> Optional[str]:
        """按优先级返回第一个运行中的 gpu_id"""
        for gpu_id in self.gpu_priority():
            if self.worker_for_gpu(gpu_id) is not None:
                return gpu_id
        # 配置外的 Worker（优先级列表已修改）也纳入
        for gpu_id in self._by_priority(self._workers.keys()):
            if self.worker_for_gpu(gpu_id) is not None:
                return gpu_id
        return None

    async def stop_gpu(self, gpu_id: str, *, force: bool = False) -> None:
        async with self._lock:
            w = self._workers.get(gpu_id)
            if w is None:
                return
            if force:
                await w.force_stop()
            else:
                await w.stop()
            self._workers.pop(gpu_id, None)
            self._drop_gpu_assignments(gpu_id)

    async def stop_all(self, *, force: bool = False) -> None:
        for gpu_id in list(self._workers.keys()):
            await self.stop_gpu(gpu_id, force=force)

    # ── 模型实例分布 ──────────────────────────────────────────

    def add_assignment(self, model_path: str, gpu_id: str) -> None:
        self._assignments.setdefault(model_path, set()).add(gpu_id)

    def remove_assignment(self, model_path: str, gpu_id: Optional[str] = None) -> None:
        if gpu_id is None:
            self._assignments.pop(model_path, None)
            for key in [k for k in self._inst_inflight if k[0] == model_path]:
                self._inst_inflight.pop(key, None)
            return
        gpus = self._assignments.get(model_path)
        if gpus is not None:
            gpus.discard(gpu_id)
            if not gpus:
                self._assignments.pop(model_path, None)
        self._inst_inflight.pop((model_path, gpu_id), None)

    def _drop_gpu_assignments(self, gpu_id: str) -> None:
        for model_path in [p for p, gpus in self._assignments.items() if gpu_id in gpus]:
            self.remove_assignment(model_path, gpu_id)
        self._gpu_inflight.pop(gpu_id, None)

    def model_gpus(self, model_path: str) -> List[str]:
        """模型当前存活实例所在的 GPU 列表（按优先级排序）"""
        gpus = [
            g for g in self._assignments.get(model_path, set())
            if self.worker_for_gpu(g) is not None
        ]
        return self._by_priority(gpus)

    def gpu_models(self, gpu_id: str) -> Set[str]:
        """指定 GPU 上加载的模型路径集合（仅统计存活 Worker）"""
        if self.worker_for_gpu(gpu_id) is None:
            return set()
        return {p for p, gpus in self._assignments.items() if gpu_id in gpus}

    async def resync(self) -> None:
        """与各 Worker 的实际缓存对齐 assignments（崩溃/外部卸载后的纠偏）。"""
        for gpu_id, w in list(self._workers.items()):
            if not w.alive:
                self._drop_gpu_assignments(gpu_id)
                continue
            try:
                resp = await w.send_cmd({"cmd": "cached_models"})
            except Exception:
                continue
            if not resp or not resp.get("ok"):
                continue
            actual = set((resp.get("models") or {}).keys())
            known = self.gpu_models(gpu_id)
            for removed in known - actual:
                self.remove_assignment(removed, gpu_id)
            for added in actual - known:
                self.add_assignment(added, gpu_id)

    # ── 负载计数与路由 ────────────────────────────────────────

    def gpu_inflight(self, gpu_id: str) -> int:
        return self._gpu_inflight.get(gpu_id, 0)

    def any_inflight(self) -> bool:
        """是否存在任何进行中的推理任务"""
        return any(count > 0 for count in self._gpu_inflight.values())

    def instance_inflight(self, model_path: str, gpu_id: str) -> int:
        return self._inst_inflight.get((model_path, gpu_id), 0)

    def mark_acquire(self, model_path: str, gpu_id: str) -> None:
        self._gpu_inflight[gpu_id] = self._gpu_inflight.get(gpu_id, 0) + 1
        key = (model_path, gpu_id)
        self._inst_inflight[key] = self._inst_inflight.get(key, 0) + 1

    def mark_release(self, model_path: str, gpu_id: str) -> None:
        if self._gpu_inflight.get(gpu_id, 0) > 0:
            self._gpu_inflight[gpu_id] -= 1
        key = (model_path, gpu_id)
        if self._inst_inflight.get(key, 0) > 0:
            self._inst_inflight[key] -= 1

    def has_idle_instance(self, model_path: str) -> bool:
        """模型是否存在无推理任务的存活实例"""
        return any(
            self.instance_inflight(model_path, g) == 0
            for g in self.model_gpus(model_path)
        )

    def pick_instance(self, model_path: str) -> Optional[str]:
        """为一次推理请求选择模型实例所在 GPU。

        优先级：
        1. 空闲实例（实例无任务）中，整卡无任务的 GPU（空闲 GPU）
        2. 其余空闲实例（按 GPU 优先级）
        3. 均分队列：实例任务数最少的 GPU（并列按优先级）
        """
        gpus = self.model_gpus(model_path)
        if not gpus:
            return None
        idle = [g for g in gpus if self.instance_inflight(model_path, g) == 0]
        if idle:
            gpu_idle = [g for g in idle if self.gpu_inflight(g) == 0]
            return (gpu_idle or idle)[0]
        return min(gpus, key=lambda g: (self.instance_inflight(model_path, g), self._priority_index(g)))

    def pick_io_worker(self) -> Optional[WorkerProcess]:
        """为音色文件 I/O 选择最空闲的存活 Worker；不主动启动新 Worker。"""
        alive = [
            w for g in self._by_priority(self._workers.keys())
            if (w := self.worker_for_gpu(g)) is not None
        ]
        if not alive:
            return None
        return min(alive, key=lambda w: (w.active_request_count, self._priority_index(w.gpu_id)))

    async def io_worker(self) -> WorkerProcess:
        """音色文件 I/O 用 Worker：优先空闲 Worker；无运行中 Worker 时才按优先级启动一个。"""
        w = self.pick_io_worker()
        if w is not None:
            return w
        gpu_id = self.gpu_priority()[0]
        return await self.ensure_worker(gpu_id)

    # ── 状态 ──────────────────────────────────────────────────

    def status(self) -> Dict[str, Any]:
        workers_status: List[Dict[str, Any]] = []
        gpu_ids = sorted(
            set(self._workers.keys()) | set(self.gpu_priority()),
            key=self._priority_index,
        )
        first_error: Optional[str] = None
        any_alive = False
        for gpu_id in gpu_ids:
            w = self._workers.get(gpu_id)
            alive = w is not None and w.alive
            error = w.error if w is not None else None
            if error and first_error is None:
                first_error = error
            any_alive = any_alive or alive
            workers_status.append({
                "gpu": gpu_id,
                "alive": alive,
                "error": error,
                "pid": w.pid if w is not None else None,
                "models": sorted(self.gpu_models(gpu_id)),
                "inflight": self.gpu_inflight(gpu_id),
                "last_activity": w.last_activity if w is not None else None,
            })
        return {
            "alive": any_alive,
            "error": first_error,
            "gpus": self.gpu_priority(),
            "workers": workers_status,
        }

    def idle_worker_gpus(self, max_idle_seconds: float) -> List[str]:
        """返回无模型加载且空闲超时的存活 Worker 所在 GPU 列表"""
        now = time.monotonic()
        result = []
        for gpu_id, w in self._workers.items():
            if not w.alive:
                continue
            if self.gpu_models(gpu_id):
                continue
            if now - w.last_activity >= max_idle_seconds:
                result.append(gpu_id)
        return result

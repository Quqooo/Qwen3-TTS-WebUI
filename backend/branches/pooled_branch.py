"""基于 Worker 进程池的分支基类

将三个后端分支共有的 Worker 通信管道统一实现：
- 模型命令（加载/卸载/推理/流式）按 模型路径 × GPU 路由到对应 Worker
- 音色文件 I/O 命令路由到最空闲的 Worker
- 推理请求通过 lease 或自动选择实例完成多卡负载均衡

子类只需提供：分支名、provider 文件路径、加载参数与流式参数。
"""
import asyncio
import base64
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import numpy as np

from .base import NotSupportedError, TTSBranch
from .worker_client import WorkerProcess
from .worker_pool import WorkerPool
from ..voices import manager as voice_manager
from ..config import settings


class PooledWorkerBranch(TTSBranch):
    """Worker 子进程池化分支实现（每 GPU 一个 Worker 进程）"""

    _streaming_supported: bool = True

    def __init__(self, provider_file: str, logger: logging.Logger):
        self._provider_file = provider_file
        self._logger = logger
        self._pool = WorkerPool(provider_file, logger)

    # ── 子类钩子 ──────────────────────────────────────────────

    @property
    def pool(self) -> WorkerPool:
        return self._pool

    def _load_provider_options(self) -> Dict[str, Any]:
        """加载模型时的 provider_options，由各分支覆盖"""
        return {}

    def _generation_runtime_params(self) -> Dict[str, Any]:
        """Return provider-internal settings attached to every generation request."""
        return {}

    def _stream_params(
        self,
        dffdeeq: Optional[Dict[str, Any]] = None,
        andimarafioti: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """按分支命名空间传递显式流式参数，不注入默认值。"""
        return {
            "dffdeeq": dict(dffdeeq or {}),
            "andimarafioti": dict(andimarafioti or {}),
        }

    # ── 路由 ──────────────────────────────────────────────────

    @asynccontextmanager
    async def _route(
        self, model_path: str, lease: Any = None, gpu_id: Optional[str] = None
    ) -> AsyncGenerator[Tuple[WorkerProcess, str], None]:
        """解析模型实例对应的 Worker。

        lease 由缓存管理器在分配时完成计数，此处仅做路由；
        无 lease 的调用（音色预览等）在上下文中临时计数，供负载均衡参考。
        """
        if lease is not None:
            gpu = lease.gpu
        else:
            gpu = gpu_id or self._pool.pick_instance(model_path)
        if gpu is None:
            raise RuntimeError(f"Model not loaded: {os.path.basename(model_path)}")
        w = self._pool.worker_for_gpu(gpu)
        if w is None:
            raise RuntimeError(f"Worker (GPU {gpu}) unavailable")
        track = lease is None
        if track:
            self._pool.mark_acquire(model_path, gpu)
        try:
            yield w, gpu
        finally:
            if track:
                self._pool.mark_release(model_path, gpu)

    # ── Worker 生命周期 ───────────────────────────────────────

    async def worker_start(self, gpu_id: Optional[str] = None) -> None:
        if gpu_id is not None:
            await self._pool.ensure_worker(gpu_id)
            return
        started = await self._pool.start_next()
        if started is None and self._pool.any_alive_worker() is None:
            # 配置列表为空等极端情况：确保至少有一个可用 Worker
            await self._pool.ensure_worker(self._pool.gpu_priority()[0])

    async def worker_stop(self, gpu_id: Optional[str] = None, stop_all: bool = False) -> None:
        if stop_all:
            await self._pool.stop_all(force=False)
            return
        target = gpu_id or self._pool.first_alive_gpu()
        if target is not None:
            await self._pool.stop_gpu(target, force=False)

    async def worker_force_stop(self, gpu_id: Optional[str] = None, stop_all: bool = False) -> None:
        if stop_all:
            await self._pool.stop_all(force=True)
            return
        target = gpu_id or self._pool.first_alive_gpu()
        if target is not None:
            await self._pool.stop_gpu(target, force=True)

    async def worker_status(self) -> Dict[str, Any]:
        return self._pool.status()

    # ── 模型生命周期 ──────────────────────────────────────────

    async def load_model(self, model_path: str, model_kind: str,
                         load_kwargs: Optional[Dict[str, Any]] = None,
                         gpu_id: Optional[str] = None) -> None:
        gpu = gpu_id or self._pool.gpu_priority()[0]
        w = await self._pool.ensure_worker(gpu)
        load_options: Dict[str, Any] = {"dtype": settings.dtype}
        load_options.update(load_kwargs or {})
        resp = await w.send_cmd({
            "cmd": "load_model", "model_path": model_path,
            "model_kind": model_kind, "load_options": load_options,
            "provider_options": self._load_provider_options(),
        })
        if not resp or not resp.get("ok"):
            raise RuntimeError((resp or {}).get("error", "Failed to load model"))
        self._pool.add_assignment(model_path, gpu)

    async def unload_model(self, model_path: str, gpu_id: Optional[str] = None) -> None:
        gpus = [gpu_id] if gpu_id is not None else self._pool.model_gpus(model_path)
        for gpu in gpus:
            w = self._pool.worker_for_gpu(gpu)
            if w is not None:
                await w.send_cmd({"cmd": "unload_model", "model_path": model_path})
            self._pool.remove_assignment(model_path, gpu)

    async def wait_model_stoppable(self, model_path: str, gpu_id: Optional[str] = None) -> None:
        gpus = [gpu_id] if gpu_id is not None else self._pool.model_gpus(model_path)
        for gpu in gpus:
            w = self._pool.worker_for_gpu(gpu)
            if w is not None:
                await w.wait_model_idle(model_path)

    def unload_idle_models(self, max_idle_seconds: float) -> List[str]:
        return []

    async def cached_models(self) -> Dict[str, Dict[str, Any]]:
        """聚合各 Worker 的模型缓存，键为 "model_path@gpu" """
        result: Dict[str, Dict[str, Any]] = {}
        for gpu, w in self._pool.workers.items():
            if not w.alive:
                continue
            resp = await w.send_cmd({"cmd": "cached_models"})
            if not resp or not resp.get("ok"):
                continue
            for path, info in (resp.get("models") or {}).items():
                result[f"{path}@{gpu}"] = {**info, "gpu": gpu, "model_path": path}
        return result

    async def get_supported_options(self, model_path: str) -> Dict[str, Any]:
        async with self._route(model_path) as (w, _gpu):
            resp = await w.send_cmd({"cmd": "get_supported_options", "model_path": model_path})
        if resp and resp.get("ok"):
            return resp
        raise RuntimeError((resp or {}).get("error", "Failed to get model options"))

    # ── 生成接口 ──────────────────────────────────────────────

    def _build_clone_cmd(self, model_path: str, text: str, language: str,
                         ref_audio: Optional[Any], ref_text: Optional[str],
                         x_vector_only: bool, voice_file: Optional[str],
                         generation_params: Optional[Dict[str, Any]],
                         cmd_name: str, instruct: Optional[str] = None) -> Dict[str, Any]:
        cmd: Dict[str, Any] = {
            "cmd": cmd_name, "model_path": model_path,
            "text": text, "language": language,
            "generation_params": generation_params or {},
            **self._generation_runtime_params(),
        }
        if instruct:
            cmd["instruct"] = instruct
        if voice_file:
            vf = voice_manager.resolve_voice_file(voice_file)
            if not vf:
                raise ValueError(f"Voice file not found: {voice_file}")
            cmd["voice_file"] = vf
        elif ref_audio is not None:
            wav, sr = ref_audio
            cmd["ref_audio"] = base64.b64encode(np.asarray(wav, dtype=np.float32).tobytes()).decode("ascii")
            cmd["ref_audio_sr"] = int(sr)
            cmd["ref_text"] = ref_text
            cmd["x_vector_only"] = x_vector_only
        else:
            raise ValueError("Base model requires voice_file or ref_audio")
        return cmd

    @staticmethod
    def _decode_audio_response(resp: Optional[Dict[str, Any]]) -> Tuple[List[np.ndarray], int]:
        if not resp or not resp.get("ok"):
            raise RuntimeError((resp or {}).get("error", "Generation failed"))
        return [np.frombuffer(base64.b64decode(resp["audio"]), dtype=np.float32)], resp["sr"]

    async def generate_voice_clone(
        self, model_path: str, text: str, language: str = "Auto",
        ref_audio: Optional[Any] = None, ref_text: Optional[str] = None,
        x_vector_only: bool = False, voice_file: Optional[str] = None,
        generation_params: Optional[Dict[str, Any]] = None,
        instruct: Optional[str] = None, lease: Any = None,
    ) -> Tuple[List[np.ndarray], int]:
        cmd = self._build_clone_cmd(model_path, text, language, ref_audio, ref_text,
                                    x_vector_only, voice_file, generation_params,
                                    "generate_voice_clone", instruct)
        async with self._route(model_path, lease=lease) as (w, _gpu):
            resp = await w.send_cmd_detached(cmd)
        return self._decode_audio_response(resp)

    async def generate_custom_voice(
        self, model_path: str, text: str, speaker: str, language: str = "Auto",
        instruct: Optional[str] = None, generation_params: Optional[Dict[str, Any]] = None,
        lease: Any = None,
    ) -> Tuple[List[np.ndarray], int]:
        async with self._route(model_path, lease=lease) as (w, _gpu):
            resp = await w.send_cmd_detached({
                "cmd": "generate_custom_voice", "model_path": model_path,
                "text": text, "speaker": speaker, "language": language,
                "instruct": instruct, "generation_params": generation_params or {},
                **self._generation_runtime_params(),
            })
        return self._decode_audio_response(resp)

    async def generate_voice_design(
        self, model_path: str, text: str, instruct: str, language: str = "Auto",
        generation_params: Optional[Dict[str, Any]] = None,
        lease: Any = None,
    ) -> Tuple[List[np.ndarray], int]:
        async with self._route(model_path, lease=lease) as (w, _gpu):
            resp = await w.send_cmd_detached({
                "cmd": "generate_voice_design", "model_path": model_path,
                "text": text, "instruct": instruct, "language": language,
                "generation_params": generation_params or {},
                **self._generation_runtime_params(),
            })
        return self._decode_audio_response(resp)

    # ── 流式生成接口 ──────────────────────────────────────────

    def _check_streaming(self) -> None:
        if not self._streaming_supported:
            raise NotSupportedError(f"{self.name} does not support streaming inference")

    async def _stream(self, cmd: Dict[str, Any], model_path: str,
                      lease: Any = None) -> AsyncGenerator[Tuple[np.ndarray, int], None]:
        started = time.monotonic()
        received_chunk = False
        completed = False
        self._logger.info("Streaming request sent to worker: model=%s", os.path.basename(model_path))
        messages = None
        async with self._route(model_path, lease=lease) as (w, _gpu):
            try:
                messages = w.stream_cmd(cmd)
                async for msg in messages:
                    if msg.get("type") == "chunk":
                        chunk = np.frombuffer(base64.b64decode(msg["data"]), dtype=np.float32)
                        if not received_chunk:
                            received_chunk = True
                            self._logger.info(
                                "Streaming first chunk received from worker: %.2fs, %d samples",
                                time.monotonic() - started,
                                len(chunk),
                            )
                        yield chunk, msg["sr"]
                    elif msg.get("type") == "done":
                        completed = True
                        return
                    elif not msg.get("ok", True):
                        err = msg.get("error", "Stream generation failed")
                        self._logger.error("Stream generation failed from worker: %s", err)
                        raise RuntimeError(err)
            finally:
                if messages is not None:
                    await messages.aclose()
                if not completed and w.alive:
                    self._logger.info("Streaming request aborted by client")

    async def stream_generate_voice_clone(
        self, model_path: str, text: str, language: str = "Auto",
        ref_audio: Optional[Any] = None, ref_text: Optional[str] = None,
        x_vector_only: bool = False, voice_file: Optional[str] = None,
        dffdeeq: Optional[Dict[str, Any]] = None,
        andimarafioti: Optional[Dict[str, Any]] = None,
        generation_params: Optional[Dict[str, Any]] = None,
        instruct: Optional[str] = None, lease: Any = None,
    ) -> AsyncGenerator[Tuple[np.ndarray, int], None]:
        self._check_streaming()
        cmd = self._build_clone_cmd(model_path, text, language, ref_audio, ref_text,
                                    x_vector_only, voice_file, generation_params,
                                    "stream_generate_voice_clone", instruct)
        cmd.update(self._stream_params(dffdeeq, andimarafioti))
        cmd.update(self._generation_runtime_params())
        async for item in self._stream(cmd, model_path, lease=lease):
            yield item

    async def stream_generate_custom_voice(
        self, model_path: str, text: str, speaker: str,
        language: str = "Auto", instruct: Optional[str] = None,
        dffdeeq: Optional[Dict[str, Any]] = None,
        andimarafioti: Optional[Dict[str, Any]] = None,
        generation_params: Optional[Dict[str, Any]] = None,
        lease: Any = None,
    ) -> AsyncGenerator[Tuple[np.ndarray, int], None]:
        self._check_streaming()
        cmd: Dict[str, Any] = {
            "cmd": "stream_generate_custom_voice", "model_path": model_path,
            "text": text, "speaker": speaker, "language": language,
            "instruct": instruct or "",
            **self._stream_params(dffdeeq, andimarafioti),
            **self._generation_runtime_params(),
            "generation_params": generation_params or {},
        }
        async for item in self._stream(cmd, model_path, lease=lease):
            yield item

    async def stream_generate_voice_design(
        self, model_path: str, text: str, instruct: str,
        language: str = "Auto",
        dffdeeq: Optional[Dict[str, Any]] = None,
        andimarafioti: Optional[Dict[str, Any]] = None,
        generation_params: Optional[Dict[str, Any]] = None,
        lease: Any = None,
    ) -> AsyncGenerator[Tuple[np.ndarray, int], None]:
        self._check_streaming()
        cmd: Dict[str, Any] = {
            "cmd": "stream_generate_voice_design", "model_path": model_path,
            "text": text, "instruct": instruct, "language": language,
            **self._stream_params(dffdeeq, andimarafioti),
            **self._generation_runtime_params(),
            "generation_params": generation_params or {},
        }
        async for item in self._stream(cmd, model_path, lease=lease):
            yield item

    # ── 音色文件 I/O ──────────────────────────────────────────

    async def create_voice_clone_prompt(
        self, model_path: str, ref_audio: Any,
        ref_text: Optional[str] = None, x_vector_only: bool = False,
    ) -> List[dict]:
        wav, sr = ref_audio
        async with self._route(model_path) as (w, _gpu):
            resp = await w.send_cmd_detached({
                "cmd": "create_voice_clone_prompt", "model_path": model_path,
                "ref_audio": base64.b64encode(np.asarray(wav, dtype=np.float32).tobytes()).decode("ascii"),
                "ref_audio_sr": int(sr),
                "ref_text": ref_text,
                "x_vector_only": x_vector_only,
            })
        if not resp or not resp.get("ok"):
            raise RuntimeError((resp or {}).get("error", "Failed to create voice clone prompt"))
        return resp["items"]

    async def voice_load_meta(self, voice_file_path: str) -> Optional[Dict[str, Any]]:
        w = await self._pool.io_worker()
        norm_path = os.path.normpath(voice_file_path)
        resp = await w.send_cmd_detached({"cmd": "load_voice_meta", "voice_file_path": norm_path})
        if resp and resp.get("ok"):
            return resp["meta"]
        if resp:
            self._logger.warning("load_voice_meta failed: %s", resp.get("error"))
        return None

    async def voice_save(
        self, items: List[dict], custom_name: str,
    ) -> str:
        w = await self._pool.io_worker()
        voice_manager._ensure_voice_dir()
        safe_name = voice_manager.sanitize_voice_name(custom_name)
        safe = voice_manager._safe_join_name(safe_name)
        if safe is None:
            raise ValueError(f"voice_dir not configured or invalid name: {custom_name}")
        out_path = str(safe)
        resp = await w.send_cmd_detached({
            "cmd": "save_voice", "out_path": out_path, "items": items,
        })
        if not resp or not resp.get("ok"):
            raise RuntimeError((resp or {}).get("error", "Failed to save voice"))
        return resp["path"]

    async def voice_update_meta(self, voice_file_path: str, item_updates: Optional[Dict[int, Dict[str, Any]]] = None) -> str:
        w = await self._pool.io_worker()
        resp = await w.send_cmd_detached({
            "cmd": "update_voice_meta", "voice_file_path": voice_file_path,
            "item_updates": {str(k): v for k, v in (item_updates or {}).items()},
        })
        if not resp or not resp.get("ok"):
            raise RuntimeError((resp or {}).get("error", "Failed to update voice metadata"))
        return resp["path"]

    async def decode_voice_preview(
        self, voice_file_path: str, model_path: str,
        gpu_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        async with self._route(model_path, gpu_id=gpu_id) as (w, _gpu):
            resp = await w.send_cmd_detached({
                "cmd": "decode_voice_preview", "voice_file_path": voice_file_path, "model_path": model_path,
            })
        if resp and resp.get("ok"):
            return resp
        if resp and "error" in resp:
            raise RuntimeError(resp["error"])
        return None

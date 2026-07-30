"""
andimarafioti/faster-qwen3-tts 分支桥接模块

使用 FasterQwen3TTS (CUDA graph) 实现 6-10x 推理加速
"""
import asyncio
import base64
import logging
import os
import time
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import numpy as np

from ..base import TTSBranch
from ..worker_client import WorkerProcess
from ...config import settings
from ...voices import manager as voice_manager

_logger = logging.getLogger("qwen-webui.branch.faster")

_PROVIDER_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "worker_provider.py"))


# ── Branch 实现 ─────────────────────────────────────────────────


class FasterBranch(TTSBranch):
    """andimarafioti/faster-qwen3-tts 分支实现（子进程 Worker 模式，CUDA graph 加速）

    支持流式和非流式生成。使用 chunk_size 控制流式输出粒度。
    """

    @property
    def name(self) -> str:
        return "andimarafioti/faster-qwen3-tts"

    def __init__(self):
        self._worker: Optional[WorkerProcess] = None
        self._lock = asyncio.Lock()

    async def _get_worker(self) -> WorkerProcess:
        async with self._lock:
            if self._worker is not None and self._worker.alive:
                return self._worker
            w = WorkerProcess(_PROVIDER_FILE, _logger)
            started = await w.start()
            if started:
                self._worker = w
                from ...routers.ws import broadcast_worker_status
                asyncio.create_task(broadcast_worker_status())
            else:
                self._worker = w
            return self._worker

    def _is_alive(self) -> bool:
        return self._worker is not None and self._worker.alive

    async def _check(self):
        w = await self._get_worker()
        if w.error:
            raise RuntimeError(f"Faster Worker unavailable: {w.error}")

    # ── Worker 生命周期 ────────────────────────────────────────

    async def worker_start(self) -> None:
        await self._check()

    async def worker_stop(self) -> None:
        async with self._lock:
            if self._worker is not None:
                await self._worker.stop()
                self._worker = None

    async def worker_force_stop(self) -> None:
        async with self._lock:
            if self._worker is not None:
                await self._worker.force_stop()
                self._worker = None

    async def worker_status(self) -> Dict[str, Any]:
        w = self._worker
        alive = w is not None and w.alive
        return {
            "alive": alive,
            "error": w.error if w is not None else None,
        }

    # ── 模型生命周期 ──────────────────────────────────────────

    async def load_model(self, model_path: str, model_kind: str, load_kwargs: Optional[Dict[str, Any]] = None) -> None:
        await self._check()
        w = await self._get_worker()
        resp = await w.send_cmd({
            "cmd": "load_model", "model_path": model_path,
            "model_kind": model_kind, "load_options": load_kwargs or {},
            "provider_options": {
                "backend": "torch",
                "max_seq_len": settings.max_seq_len,
                "warmup_prefill_len": min(100, settings.max_seq_len - 1),
            },
        })
        if not resp or not resp.get("ok"):
            raise RuntimeError((resp or {}).get("error", "Failed to load model"))

    async def unload_model(self, model_path: str) -> None:
        w = await self._get_worker()
        if w.alive:
            await w.send_cmd({"cmd": "unload_model", "model_path": model_path})

    async def wait_model_stoppable(self, model_path: str) -> None:
        w = await self._get_worker()
        if w.alive:
            await w.wait_model_idle(model_path)

    def unload_idle_models(self, max_idle_seconds: float) -> List[str]:
        return []

    async def cached_models(self) -> Dict[str, Dict[str, Any]]:
        if not self._is_alive():
            return {}
        w = self._worker
        if w is None:
            return {}
        resp = await w.send_cmd({"cmd": "cached_models"})
        return resp.get("models", {}) if resp else {}

    async def get_supported_options(self, model_path: str) -> Dict[str, Any]:
        await self._check()
        w = await self._get_worker()
        resp = await w.send_cmd({"cmd": "get_supported_options", "model_path": model_path})
        if resp and resp.get("ok"):
            return resp
        raise RuntimeError((resp or {}).get("error", "Failed to get model options"))

    # ── 生成接口（全部 async） ────────────────────────────────

    async def generate_voice_clone(
        self, model_path: str, text: str, language: str = "Auto",
        ref_audio: Optional[Any] = None, ref_text: Optional[str] = None,
        x_vector_only: bool = False, voice_file: Optional[str] = None,
        generation_params: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[np.ndarray], int]:
        await self._check()
        w = await self._get_worker()
        cmd: Dict[str, Any] = {
            "cmd": "generate_voice_clone", "model_path": model_path,
            "text": text, "language": language,
            "generation_params": generation_params or {},
        }
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
        resp = await w.send_cmd_detached(cmd)
        if not resp or not resp.get("ok"):
            raise RuntimeError((resp or {}).get("error", "Generation failed"))
        return [np.frombuffer(base64.b64decode(resp["audio"]), dtype=np.float32)], resp["sr"]

    async def generate_custom_voice(
        self, model_path: str, text: str, speaker: str, language: str = "Auto",
        instruct: Optional[str] = None, generation_params: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[np.ndarray], int]:
        await self._check()
        w = await self._get_worker()
        resp = await w.send_cmd_detached({
            "cmd": "generate_custom_voice", "model_path": model_path,
            "text": text, "speaker": speaker, "language": language,
            "instruct": instruct, "generation_params": generation_params or {},
        })
        if not resp or not resp.get("ok"):
            raise RuntimeError((resp or {}).get("error", "Generation failed"))
        return [np.frombuffer(base64.b64decode(resp["audio"]), dtype=np.float32)], resp["sr"]

    async def generate_voice_design(
        self, model_path: str, text: str, instruct: str, language: str = "Auto",
        generation_params: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[np.ndarray], int]:
        await self._check()
        w = await self._get_worker()
        resp = await w.send_cmd_detached({
            "cmd": "generate_voice_design", "model_path": model_path,
            "text": text, "instruct": instruct, "language": language,
            "generation_params": generation_params or {},
        })
        if not resp or not resp.get("ok"):
            raise RuntimeError((resp or {}).get("error", "Generation failed"))
        return [np.frombuffer(base64.b64decode(resp["audio"]), dtype=np.float32)], resp["sr"]

    # ── 流式生成接口 ──────────────────────────────────────────

    async def stream_generate_voice_clone(
        self, model_path: str, text: str, language: str = "Auto",
        ref_audio: Optional[Any] = None, ref_text: Optional[str] = None,
        x_vector_only: bool = False, voice_file: Optional[str] = None,
        emit_every_frames: int = 8, decode_window_frames: int = 80,
        overlap_samples: int = 0, max_frames: int = 10000,
        generation_params: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Tuple[np.ndarray, int], None]:
        await self._check()
        w = await self._get_worker()
        started = time.monotonic()
        received_chunk = False
        completed = False
        _logger.info("Streaming request sent to worker: model=%s", os.path.basename(model_path))
        try:
            cmd: Dict[str, Any] = {
                "cmd": "stream_generate_voice_clone", "model_path": model_path,
                "text": text, "language": language,
                "stream_params": {"chunk_size": 12},
                "generation_params": generation_params or {},
            }
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
            messages = w.stream_cmd(cmd)
            async for msg in messages:
                if msg.get("type") == "chunk":
                    chunk = np.frombuffer(base64.b64decode(msg["data"]), dtype=np.float32)
                    if not received_chunk:
                        received_chunk = True
                        _logger.info(
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
                    _logger.error("Stream generation failed from worker: %s", err)
                    raise RuntimeError(err)
        finally:
            if "messages" in locals():
                await messages.aclose()
            if not completed and w.alive:
                _logger.info("Streaming request aborted by client")

    async def stream_generate_custom_voice(
        self, model_path: str, text: str, speaker: str,
        language: str = "Auto", instruct: Optional[str] = None,
        emit_every_frames: int = 8, decode_window_frames: int = 80,
        overlap_samples: int = 0, max_frames: int = 10000,
        generation_params: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Tuple[np.ndarray, int], None]:
        await self._check()
        w = await self._get_worker()
        started = time.monotonic()
        received_chunk = False
        completed = False
        _logger.info("Streaming request sent to worker: model=%s", os.path.basename(model_path))
        try:
            messages = w.stream_cmd({
                "cmd": "stream_generate_custom_voice", "model_path": model_path,
                "text": text, "speaker": speaker, "language": language,
                "instruct": instruct or "",
                "stream_params": {"chunk_size": 12},
                "generation_params": generation_params or {},
            })
            async for msg in messages:
                if msg.get("type") == "chunk":
                    chunk = np.frombuffer(base64.b64decode(msg["data"]), dtype=np.float32)
                    if not received_chunk:
                        received_chunk = True
                        _logger.info(
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
                    _logger.error("Stream generation failed from worker: %s", err)
                    raise RuntimeError(err)
        finally:
            if "messages" in locals():
                await messages.aclose()
            if not completed and w.alive:
                _logger.info("Streaming request aborted by client")

    async def stream_generate_voice_design(
        self, model_path: str, text: str, instruct: str,
        language: str = "Auto",
        emit_every_frames: int = 8, decode_window_frames: int = 80,
        overlap_samples: int = 0, max_frames: int = 10000,
        generation_params: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Tuple[np.ndarray, int], None]:
        await self._check()
        w = await self._get_worker()
        started = time.monotonic()
        received_chunk = False
        completed = False
        _logger.info("Streaming request sent to worker: model=%s", os.path.basename(model_path))
        try:
            messages = w.stream_cmd({
                "cmd": "stream_generate_voice_design", "model_path": model_path,
                "text": text, "instruct": instruct, "language": language,
                "stream_params": {"chunk_size": 12},
                "generation_params": generation_params or {},
            })
            async for msg in messages:
                if msg.get("type") == "chunk":
                    chunk = np.frombuffer(base64.b64decode(msg["data"]), dtype=np.float32)
                    if not received_chunk:
                        received_chunk = True
                        _logger.info(
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
                    _logger.error("Stream generation failed from worker: %s", err)
                    raise RuntimeError(err)
        finally:
            if "messages" in locals():
                await messages.aclose()
            if not completed and w.alive:
                _logger.info("Streaming request aborted by client")

    # ── 音色文件 I/O（全部 async） ────────────────────────────

    async def create_voice_clone_prompt(
        self, model_path: str, ref_audio: Any,
        ref_text: Optional[str] = None, x_vector_only: bool = False,
    ) -> List[dict]:
        await self._check()
        w = await self._get_worker()
        wav, sr = ref_audio
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
        await self._check()
        w = await self._get_worker()
        norm_path = os.path.normpath(voice_file_path)
        resp = await w.send_cmd_detached({"cmd": "load_voice_meta", "voice_file_path": norm_path})
        if resp and resp.get("ok"):
            return resp["meta"]
        if resp:
            _logger.warning("load_voice_meta failed: %s", resp.get("error"))
        return None

    async def voice_save(
        self, items: List[dict], custom_name: str,
    ) -> str:
        await self._check()
        w = await self._get_worker()
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

    async def voice_update_meta(self, voice_file_path: str, item_updates: Optional[Dict[int, Dict[str, Any]]] = None) -> dict:
        await self._check()
        w = await self._get_worker()
        resp = await w.send_cmd_detached({
            "cmd": "update_voice_meta", "voice_file_path": voice_file_path,
            "item_updates": {str(k): v for k, v in (item_updates or {}).items()},
        })
        if not resp or not resp.get("ok"):
            raise RuntimeError((resp or {}).get("error", "Failed to update voice metadata"))
        return resp["path"]

    async def voice_get_preview(
        self, voice_file_path: str, model_path: str,
    ) -> Optional[Dict[str, Any]]:
        await self._check()
        w = await self._get_worker()
        resp = await w.send_cmd_detached({
            "cmd": "decode_voice_preview", "voice_file_path": voice_file_path, "model_path": model_path,
        })
        if resp and resp.get("ok"):
            return resp
        if resp and "error" in resp:
            raise RuntimeError(resp["error"])
        return None

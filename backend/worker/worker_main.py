"""Provider-driven TCP worker using a length-prefixed JSON protocol."""
from __future__ import annotations

import argparse
import asyncio
import gc
import json
import logging
import os
import struct
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

# Direct script execution only places backend/worker on sys.path. Providers use
# canonical backend.worker imports, so make the repository package visible first.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from backend.worker.common import (
    close_stream, decode_audio, deserialize_tensor, load_voice_payload,
    make_audio_result, make_stream_chunk, next_stream_item, read_voice_meta,
    release_cuda_cache, save_voice_payload, update_voice_meta,
)
from backend.worker.provider import ProviderNotSupportedError, WorkerProvider, load_provider

logging.basicConfig(level=logging.INFO, format="[QwenWorker] %(asctime)s %(levelname)s: %(message)s", datefmt="%H:%M:%S")
_logger = logging.getLogger("qwen-worker")


@dataclass
class WorkerState:
    provider: WorkerProvider
    models: Dict[str, Any] = field(default_factory=dict)
    kinds: Dict[str, str] = field(default_factory=dict)
    last_used: Dict[str, float] = field(default_factory=dict)
    executors: Dict[str, ThreadPoolExecutor] = field(default_factory=dict)
    operation_locks: Dict[str, asyncio.Lock] = field(default_factory=dict)

    def executor(self, model_path: str) -> ThreadPoolExecutor:
        executor = self.executors.get(model_path)
        if executor is None:
            executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="qwen-model")
            self.executors[model_path] = executor
        return executor

    def operation_lock(self, model_path: str) -> asyncio.Lock:
        lock = self.operation_locks.get(model_path)
        if lock is None:
            lock = asyncio.Lock()
            self.operation_locks[model_path] = lock
        return lock

    def model(self, model_path: str) -> Any:
        model = self.models.get(model_path)
        if model is not None:
            self.last_used[model_path] = time.monotonic()
        return model

    def shutdown_executor(self, model_path: str) -> None:
        executor = self.executors.pop(model_path, None)
        if executor is not None:
            executor.shutdown(wait=False)

    def shutdown(self) -> None:
        for executor in list(self.executors.values()):
            executor.shutdown(wait=False)
        self.executors.clear()


class WorkerServer:
    def __init__(self, provider: WorkerProvider):
        self.state = WorkerState(provider)
        self._lifecycle_lock = asyncio.Lock()

    async def _in_model_thread(self, model_path: str, function: Any, *args: Any) -> Any:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.state.executor(model_path), function, *args)

    async def _unload_locked(self, model_path: str, reason: str) -> Dict[str, Any]:
        async with self.state.operation_lock(model_path):
            model = self.state.models.get(model_path)
            if model is None:
                self.state.shutdown_executor(model_path)
                return {"ok": True}

            started = time.monotonic()
            _logger.info(
                "Unloading model: provider=%s model=%s reason=%s",
                self.state.provider.provider_id,
                model_path,
                reason,
            )

            model_holder = [model]
            del model

            def run() -> Dict[str, Any]:
                self.state.provider.release_model(model_holder.pop())
                return {"ok": True}

            try:
                result = await self._in_model_thread(model_path, run)
            finally:
                self.state.models.pop(model_path, None)
                self.state.kinds.pop(model_path, None)
                self.state.last_used.pop(model_path, None)
                gc.collect()
                release_cuda_cache()
                self.state.shutdown_executor(model_path)
            _logger.info(
                "Model unloaded: provider=%s model=%s elapsed=%.2fs",
                self.state.provider.provider_id,
                model_path,
                time.monotonic() - started,
            )
            return result

    async def _unload(self, model_path: str, reason: str = "requested") -> Dict[str, Any]:
        async with self._lifecycle_lock:
            return await self._unload_locked(model_path, reason)

    async def _with_model(self, model_path: str, function: Any) -> Dict[str, Any]:
        async with self.state.operation_lock(model_path):
            model = self.state.model(model_path)
            if model is None:
                return {"ok": False, "error": f"Model not loaded: {model_path}"}
            return await function(model)

    async def command(self, data: Dict[str, Any]) -> Dict[str, Any]:
        cmd = data.get("cmd", "")
        if cmd == "ping":
            return {"ok": True}
        if cmd == "cached_models":
            async with self._lifecycle_lock:
                paths = list(self.state.models)
                return {"ok": True, "models": {path: {
                    "kind": self.state.kinds[path],
                    "model_path": path,
                    "last_used": self.state.last_used.get(path, 0.0),
                } for path in paths}}
        if cmd == "load_model":
            return await self._load_model(data)
        if cmd == "unload_model":
            return await self._unload(data["model_path"])
        if cmd == "wait_model_idle":
            async with self.state.operation_lock(data["model_path"]):
                return {"ok": True}
        if cmd == "load_voice_meta":
            return read_voice_meta(data["voice_file_path"])
        if cmd == "save_voice":
            return self._save_voice(data)
        if cmd == "update_voice_meta":
            try:
                path = update_voice_meta(data["voice_file_path"], data.get("item_updates"))
                return {"ok": True, "path": path}
            except Exception as exc:
                return {"ok": False, "error": str(exc)}

        methods = {
            "generate_voice_clone": self.state.provider.generate_voice_clone,
            "generate_custom_voice": self.state.provider.generate_custom_voice,
            "generate_voice_design": self.state.provider.generate_voice_design,
        }
        if cmd not in methods and cmd not in {
            "get_supported_options", "decode_voice_preview", "create_voice_clone_prompt"
        }:
            return {"ok": False, "error": f"Unknown command: {cmd}"}

        model_path = data.get("model_path", "")

        async def execute(model: Any) -> Dict[str, Any]:
            if cmd == "get_supported_options":
                result = await self._in_model_thread(
                    model_path, self.state.provider.get_supported_options, model
                )
                return {"ok": True, **result}
            if cmd == "decode_voice_preview":
                self._require_capability("voice_preview")

                def preview() -> Any:
                    items = load_voice_payload(data["voice_file_path"]).get("items", [])
                    if not items:
                        raise ValueError("No items in voice file")
                    return self.state.provider.decode_voice_preview(model, items[0])

                result = await self._in_model_thread(model_path, preview)
                return make_audio_result(result) if result is not None else {"ok": True}
            if cmd == "create_voice_clone_prompt":
                self._require_capability("voice_prompt")

                def create_prompt() -> Any:
                    return self.state.provider.create_voice_clone_prompt(model, self._request(data))

                items = await self._in_model_thread(model_path, create_prompt)
                return {"ok": True, "items": items}

            def generate() -> Any:
                return methods[cmd](model, self._request(data))

            result = await self._in_model_thread(model_path, generate)
            return make_audio_result(result)

        return await self._with_model(model_path, execute)

    async def _load_model(self, data: Dict[str, Any]) -> Dict[str, Any]:
        path = data["model_path"]
        kind = data.get("model_kind", "base")
        async with self._lifecycle_lock:
            for cached_path, cached_kind in list(self.state.kinds.items()):
                if cached_kind != kind:
                    await self._unload_locked(cached_path, "kind mismatch")

            async with self.state.operation_lock(path):
                if path in self.state.models:
                    self.state.last_used[path] = time.monotonic()
                    return {"ok": True, "message": "already loaded"}

                started = time.monotonic()
                _logger.info(
                    "Loading model: provider=%s model=%s kind=%s",
                    self.state.provider.provider_id,
                    path,
                    kind,
                )

                def run() -> Dict[str, Any]:
                    model = self.state.provider.load_model(
                        path, kind, data.get("load_options") or {}, data.get("provider_options") or {}
                    )
                    self.state.models[path] = model
                    self.state.kinds[path] = kind
                    self.state.last_used[path] = time.monotonic()
                    return {"ok": True}

                try:
                    result = await self._in_model_thread(path, run)
                except Exception:
                    if path not in self.state.models:
                        self.state.shutdown_executor(path)
                    _logger.error(
                        "Model load failed: provider=%s model=%s elapsed=%.2fs",
                        self.state.provider.provider_id,
                        path,
                        time.monotonic() - started,
                        exc_info=True,
                    )
                    raise
                _logger.info(
                    "Model loaded: provider=%s model=%s elapsed=%.2fs",
                    self.state.provider.provider_id,
                    path,
                    time.monotonic() - started,
                )
                return result

    def _request(self, data: Dict[str, Any]) -> Dict[str, Any]:
        request = {key: value for key, value in data.items() if key != "cmd"}
        if data.get("ref_audio"):
            request["ref_audio"] = (decode_audio(data["ref_audio"]), data["ref_audio_sr"])
        if data.get("voice_file"):
            payload = load_voice_payload(data["voice_file"])
            request["voice_clone_prompt"] = self.state.provider.deserialize_voice_items(payload.get("items", []))
        return request

    def _save_voice(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            items = []
            for source in data["items"]:
                item = dict(source)
                for key in ("ref_code", "ref_spk_embedding"):
                    if isinstance(item.get(key), dict) and "data" in item[key]:
                        item[key] = deserialize_tensor(item[key])
                ref_code = item.get("ref_code")
                if ref_code is not None and ref_code.is_floating_point():
                    raise ValueError(f"ref_code dtype must be integer, got {ref_code.dtype}")
                ref_spk = item.get("ref_spk_embedding")
                if ref_spk is None or not ref_spk.is_floating_point():
                    dtype = getattr(ref_spk, "dtype", None)
                    raise ValueError(f"ref_spk_embedding dtype must be float, got {dtype}")
                items.append(item)
            path = save_voice_payload(data["out_path"], items)
            return {"ok": True, "path": path}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _require_capability(self, name: str) -> None:
        if not getattr(self.state.provider.capabilities, name):
            raise ProviderNotSupportedError(f"{self.state.provider.provider_id} does not support {name}")

    async def stream(self, data: Dict[str, Any], writer: asyncio.StreamWriter) -> None:
        command = data["cmd"]
        mapping = {
            "stream_generate_voice_clone": ("stream_voice_clone", self.state.provider.stream_voice_clone),
            "stream_generate_custom_voice": ("stream_custom_voice", self.state.provider.stream_custom_voice),
            "stream_generate_voice_design": ("stream_voice_design", self.state.provider.stream_voice_design),
        }
        capability, method = mapping[command]
        self._require_capability(capability)
        path = data["model_path"]
        async with self.state.operation_lock(path):
            model = self.state.model(path)
            if model is None:
                await send_json(writer, {"ok": False, "error": f"Model not loaded: {path}"})
                return

            def create_generator() -> Any:
                return method(model, self._request(data))

            started = time.monotonic()
            generator = await self._in_model_thread(path, create_generator)
            chunk_count = 0
            _logger.info(
                "Streaming started: provider=%s model=%s text_chars=%d",
                self.state.provider.provider_id,
                os.path.basename(path),
                len(data.get("text", "")),
            )
            try:
                while True:
                    present, item = await self._in_model_thread(path, next_stream_item, generator)
                    if not present:
                        break
                    chunk_count += 1
                    await send_json(writer, make_stream_chunk(item))
                    if chunk_count == 1:
                        _logger.info("Streaming first chunk: %.2fs", time.monotonic() - started)
                await send_json(writer, {"type": "done"})
                self.state.last_used[path] = time.monotonic()
                _logger.info(
                    "Streaming completed: provider=%s elapsed=%.2fs chunks=%d",
                    self.state.provider.provider_id,
                    time.monotonic() - started,
                    chunk_count,
                )
            finally:
                await self._in_model_thread(path, close_stream, generator)

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                data = await read_message(reader)
                try:
                    if data.get("cmd") in STREAM_COMMANDS:
                        await self.stream(data, writer)
                    else:
                        await send_json(writer, await self.command(data))
                except (ConnectionError, BrokenPipeError, ConnectionResetError):
                    _logger.info("Client disconnected during command %s", data.get("cmd"))
                    return
                except Exception as exc:
                    _logger.error("Command %s failed: %s", data.get("cmd"), exc, exc_info=True)
                    await send_json(writer, {"ok": False, "error": str(exc), "traceback": traceback.format_exc()})
        except (ConnectionError, asyncio.IncompleteReadError, BrokenPipeError, ConnectionResetError):
            _logger.info("Client disconnected")
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def shutdown(self) -> None:
        for model_path in list(self.state.models):
            try:
                await self._unload(model_path)
            except Exception:
                _logger.error("Failed to release model during shutdown: %s", model_path, exc_info=True)
        self.state.shutdown()


STREAM_COMMANDS = {
    "stream_generate_voice_clone", "stream_generate_custom_voice", "stream_generate_voice_design"
}


async def read_exact(reader: asyncio.StreamReader, size: int) -> bytes:
    value = bytearray()
    while len(value) < size:
        chunk = await reader.read(size - len(value))
        if not chunk:
            raise ConnectionError("Connection closed")
        value.extend(chunk)
    return bytes(value)


async def read_message(reader: asyncio.StreamReader) -> Dict[str, Any]:
    size = struct.unpack(">I", await read_exact(reader, 4))[0]
    return json.loads((await read_exact(reader, size)).decode("utf-8"))


async def send_json(writer: asyncio.StreamWriter, value: Dict[str, Any]) -> None:
    body = json.dumps(value, ensure_ascii=False).encode("utf-8")
    writer.write(struct.pack(">I", len(body)) + body)
    await writer.drain()


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Unified Qwen TTS worker")
    parser.add_argument("--project-dir", default="")
    parser.add_argument("--provider", required=True)
    parser.add_argument("--port", type=int, default=0)
    return parser.parse_args(argv)


async def main(argv: Optional[list[str]] = None) -> None:
    args = parse_args(argv)
    if args.project_dir:
        sys.path.insert(0, os.path.abspath(args.project_dir))
    worker = WorkerServer(load_provider(args.provider))
    server = await asyncio.start_server(worker.handle_client, "127.0.0.1", args.port)
    actual_port = server.sockets[0].getsockname()[1]
    print(f"WORKER_PORT:{actual_port}", flush=True)
    _logger.info(
        "Worker listening: provider=%s port=%d",
        worker.state.provider.provider_id,
        actual_port,
    )
    try:
        async with server:
            await server.serve_forever()
    finally:
        await worker.shutdown()


if __name__ == "__main__":
    asyncio.run(main())

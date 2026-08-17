"""Shared asynchronous client for branch worker subprocesses."""

import asyncio
from collections import deque
import json
import logging
import os
import struct
import subprocess
import sys
import threading
import time
import uuid
from typing import AsyncGenerator, Deque, IO, List, Optional

from ..config import resolve_env_python, settings


_WORKER_SCRIPT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "worker", "worker_main.py")
)


class WorkerProcess:
    """Manage a unified worker and its main, detached, and stream connections.

    Each worker is bound to a single device slot via environment injection
    (see start()): numeric slots expose exactly one CUDA/HIP device through
    CUDA_VISIBLE_DEVICES / ROCR_VISIBLE_DEVICES, the "cpu" slot hides every
    accelerator and marks the worker as CPU-only, and the "mps" slot enables
    Apple Metal with PYTORCH_ENABLE_MPS_FALLBACK. The resolved device kind is
    passed to the worker via QWEN_WEBUI_DEVICE.
    """

    def __init__(
        self,
        provider_file: str,
        logger: Optional[logging.Logger] = None,
        gpu_id: str = "0",
    ):
        self.provider_file = os.path.abspath(provider_file)
        self.gpu_id = str(gpu_id)
        self._logger = logger or logging.getLogger("qwen-webui.worker-client")
        self._process: Optional[subprocess.Popen] = None
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._port: Optional[int] = None
        self._lock = asyncio.Lock()
        self._cleanup_lock = asyncio.Lock()
        self._error: Optional[str] = None
        self._output_threads: List[threading.Thread] = []
        self._stderr_tail: Deque[str] = deque(maxlen=40)
        self._startup_stdout: Deque[str] = deque(maxlen=1)
        self._active_requests: set[str] = set()
        self._active_requests_changed = asyncio.Condition()
        # 最近一次任意命令活动的时间戳（含音色元数据读取），
        # 供 Worker 空闲超时停止策略使用。
        self.last_activity: float = time.monotonic()

    def touch_activity(self) -> None:
        self.last_activity = time.monotonic()

    @property
    def pid(self) -> Optional[int]:
        return self._process.pid if self._process is not None else None

    @property
    def error(self) -> Optional[str]:
        return self._error

    @property
    def alive(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @property
    def active_request_count(self) -> int:
        """Number of worker operations that have not reached a safe stop point."""
        return len(self._active_requests)

    async def _register_request(self) -> str:
        request_id = uuid.uuid4().hex
        async with self._active_requests_changed:
            self._active_requests.add(request_id)
        return request_id

    async def _finish_request(self, request_id: str) -> None:
        async with self._active_requests_changed:
            self._active_requests.discard(request_id)
            self._active_requests_changed.notify_all()

    async def wait_until_stoppable(self) -> None:
        """Wait until all non-interruptible worker operations reach a safe point."""
        async with self._active_requests_changed:
            await self._active_requests_changed.wait_for(lambda: not self._active_requests)

    @staticmethod
    async def _close_writer(
        writer: Optional[asyncio.StreamWriter], timeout: float = 1.0
    ) -> None:
        """Close a client connection without letting transport cleanup hang."""
        if writer is None:
            return
        try:
            writer.close()
            await asyncio.wait_for(writer.wait_closed(), timeout=timeout)
        except Exception:
            # close() 已请求优雅关闭；若底层 transport 仍不收敛，则直接
            # abort，避免遗留连接句柄继续拖住 Windows Proactor。
            transport = getattr(writer, "transport", None)
            if transport is not None:
                try:
                    transport.abort()
                except Exception:
                    pass

    async def _wait_for_request_after_cancel(
        self,
        request_id: str,
        response_task: asyncio.Task,
        writer: asyncio.StreamWriter,
    ) -> None:
        self._logger.info(
            "Worker request %s cannot be interrupted; waiting for a safe stop point",
            request_id,
        )
        try:
            while not response_task.done():
                try:
                    await asyncio.shield(response_task)
                except asyncio.CancelledError:
                    # Repeated cancellation must not make the worker look idle while
                    # the model thread is still running.
                    continue
                except Exception:
                    break
            if response_task.done() and not response_task.cancelled():
                try:
                    response_task.exception()
                except Exception:
                    pass
        finally:
            # 请求已经完成即到达安全点；transport 清理不得阻止活动计数释放。
            await self._finish_request(request_id)
            await self._close_writer(writer)
            self._logger.info("Worker request %s reached a safe stop point", request_id)

    def resolve_python(self) -> str:
        if settings.env_dir:
            executable = resolve_env_python(settings.env_dir)
            if executable:
                self._logger.info("Using configured env python: %s", executable)
                return executable
            self._logger.warning("Configured env_dir has no python: %s", settings.env_dir)

        if settings.project_dir:
            for name in (".venv", "venv", "env", ".env", "runtime"):
                executable = resolve_env_python(os.path.join(settings.project_dir, name))
                if executable:
                    self._logger.info("Found virtual env in project: %s", executable)
                    return executable

        self._logger.info("Falling back to current python: %s", sys.executable)
        return sys.executable

    async def start(self) -> bool:
        if self.alive:
            return True

        if not os.path.isfile(_WORKER_SCRIPT):
            self._error = f"Worker script not found: {_WORKER_SCRIPT}"
            return False
        if not os.path.isfile(self.provider_file):
            self._error = f"Worker provider not found: {self.provider_file}"
            return False

        self._stderr_tail.clear()
        self._startup_stdout.clear()
        env = dict(os.environ)
        if self.gpu_id == "cpu":
            env["CUDA_VISIBLE_DEVICES"] = ""
            env["QWEN_WEBUI_DEVICE"] = "cpu"
        elif self.gpu_id == "mps":
            env["CUDA_VISIBLE_DEVICES"] = ""
            env["QWEN_WEBUI_DEVICE"] = "mps"
            env["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"
        else:
            env["CUDA_VISIBLE_DEVICES"] = self.gpu_id
            # ROCm 双保险：ROCm 构建同样读取 CUDA_VISIBLE_DEVICES，
            # 但部分运行时组合下 ROCR_VISIBLE_DEVICES 更直接。
            env["ROCR_VISIBLE_DEVICES"] = self.gpu_id
            env["QWEN_WEBUI_DEVICE"] = "cuda"
        try:
            self._process = subprocess.Popen(
                [
                    self.resolve_python(),
                    _WORKER_SCRIPT,
                    "--project-dir", settings.project_dir or "",
                    "--provider", self.provider_file,
                    "--port", "0",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
            )
            if self._process.stderr:
                self._start_output_forwarder(self._process.stderr, self._stderr_tail)

            port = await asyncio.wait_for(asyncio.to_thread(self._read_startup_port), 30)
            self._port = port
            if self._process.stdout:
                self._start_output_forwarder(self._process.stdout)
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", port), timeout=10
            )
            response = await self._send_recv({"cmd": "ping"})
            if not response or not response.get("ok"):
                raise RuntimeError("worker health check failed")

            self._error = None
            self.touch_activity()
            self._logger.info(
                "Worker started (gpu=%s, pid=%d, port=%d, provider=%s)",
                self.gpu_id,
                self._process.pid,
                port,
                self.provider_file,
            )
            return True
        except Exception as exc:
            process = self._process
            exit_code = process.poll() if process is not None else None
            if process is not None and exit_code is None:
                await asyncio.sleep(0.05)
                exit_code = process.poll()
            tail = "\n".join(self._stderr_tail) or "<no stderr>"
            stdout_line = self._startup_stdout[0] if self._startup_stdout else "<no stdout>"
            self._error = (
                f"Worker startup failed: {exc}; exit_code={exit_code}; "
                f"provider={self.provider_file}; stdout={stdout_line}; stderr_tail={tail}"
            )
            self._logger.error("%s", self._error)
            await self._cleanup()
            return False
        except asyncio.CancelledError:
            await self._cleanup()
            raise

    def _read_startup_port(self) -> int:
        process = self._process
        if process is None or process.stdout is None:
            raise RuntimeError("worker stdout is unavailable")
        while True:
            line = process.stdout.readline()
            if not line:
                raise RuntimeError("worker exited before reporting its port")
            message = line.rstrip()
            if message.startswith("WORKER_PORT:"):
                sys.stderr.write(message + "\n")
                sys.stderr.flush()
                return int(message.partition(":")[2])
            if message:
                if not self._startup_stdout:
                    self._startup_stdout.append(message)
                sys.stderr.write(message + "\n")
                sys.stderr.flush()

    def _start_output_forwarder(
        self,
        stream: IO[str],
        tail: Optional[Deque[str]] = None,
    ) -> None:
        def forward() -> None:
            try:
                for line in iter(stream.readline, ""):
                    message = line.rstrip()
                    if not message:
                        continue
                    if tail is not None:
                        tail.append(message)
                    sys.stderr.write(message + "\n")
                    sys.stderr.flush()
            except Exception:
                self._logger.debug("Worker output forwarding stopped", exc_info=True)

        thread = threading.Thread(target=forward, daemon=True)
        thread.start()
        self._output_threads.append(thread)

    async def _cleanup(self, *, force: bool = False) -> None:
        async with self._cleanup_lock:
            writer = self._writer
            self._reader = None
            self._writer = None
            self._port = None
            # Windows Proactor 在对端/事件循环异常时可能一直卡在
            # wait_closed；正常停止和强停都不能被 transport 清理永久阻塞。
            await self._close_writer(writer)

            process = self._process
            if process is not None and process.poll() is None:
                try:
                    if force:
                        process.kill()
                    else:
                        process.terminate()
                    await asyncio.wait_for(asyncio.to_thread(process.wait), timeout=3.0)
                except Exception:
                    try:
                        process.kill()
                        await asyncio.wait_for(asyncio.to_thread(process.wait), timeout=3.0)
                    except Exception:
                        self._logger.error(
                            "Worker process did not exit after forced termination (gpu=%s, pid=%s)",
                            self.gpu_id,
                            process.pid,
                        )
            exited = process is None or process.poll() is not None
            if process is not None and exited:
                for stream in (process.stdout, process.stderr):
                    if stream is not None:
                        try:
                            stream.close()
                        except Exception:
                            pass
            self._process = None if exited else process
            if exited:
                self._output_threads = []

    async def stop(self) -> None:
        # Model inference runs in a worker thread and cannot be terminated safely.
        # Defer process shutdown until every such operation reaches its boundary.
        await self.wait_until_stoppable()
        async with self._lock:
            await self._cleanup()

    async def force_stop(self) -> None:
        """Terminate the worker immediately without waiting for safe boundaries."""
        self._logger.warning(
            "Force stopping Worker (active_requests=%d)",
            self.active_request_count,
        )
        await self._cleanup(force=True)
        async with self._active_requests_changed:
            self._active_requests.clear()
            self._active_requests_changed.notify_all()
        if self.alive:
            raise RuntimeError(
                f"Worker (GPU {self.gpu_id}, PID {self.pid}) survived forced termination"
            )

    @staticmethod
    async def _write_command(
        writer: asyncio.StreamWriter, cmd: dict, timeout: float
    ) -> None:
        body = json.dumps(cmd, ensure_ascii=False).encode("utf-8")
        writer.write(struct.pack(">I", len(body)) + body)
        await asyncio.wait_for(writer.drain(), timeout=timeout)

    @staticmethod
    async def _read_response(
        reader: asyncio.StreamReader, timeout: float
    ) -> dict:
        header = await asyncio.wait_for(reader.readexactly(4), timeout=timeout)
        length = struct.unpack(">I", header)[0]
        body = await asyncio.wait_for(reader.readexactly(length), timeout=timeout)
        return json.loads(body.decode("utf-8"))

    async def _send_recv(
        self, cmd: dict, timeout: float = 3600.0
    ) -> Optional[dict]:
        async with self._lock:
            if self._reader is None or self._writer is None:
                return None
            self.touch_activity()
            try:
                await self._write_command(self._writer, cmd, timeout)
                return await self._read_response(self._reader, timeout)
            except (
                asyncio.TimeoutError, asyncio.IncompleteReadError, ConnectionError, OSError
            ) as exc:
                self._error = f"Worker communication error: {exc}"
                self._logger.error("%s", self._error)
                await self._cleanup()
                return None

    async def send_cmd(self, cmd: dict) -> Optional[dict]:
        return await self._send_recv(cmd)

    async def wait_model_idle(self, model_path: str) -> None:
        """Wait until the worker model lock reaches the next safe boundary."""
        response = await self.send_cmd_detached({
            "cmd": "wait_model_idle",
            "model_path": model_path,
        })
        if not response or not response.get("ok"):
            raise RuntimeError((response or {}).get("error", "Failed to wait for model idle"))

    async def _wait_for_stream_after_cancel(
        self, request_id: str, model_path: str
    ) -> None:
        self._logger.info(
            "Worker stream %s cannot stop immediately; waiting for a safe point",
            request_id,
        )
        try:
            await self.wait_model_idle(model_path)
        except Exception:
            self._logger.warning(
                "Failed while waiting for worker stream %s safe point",
                request_id,
                exc_info=True,
            )
        finally:
            await self._finish_request(request_id)
            self._logger.info("Worker stream %s reached a safe stop point", request_id)

    async def send_cmd_detached(
        self, cmd: dict, timeout: float = 3600.0
    ) -> Optional[dict]:
        if not self._port:
            return None
        self.touch_activity()
        request_id = await self._register_request()
        writer: Optional[asyncio.StreamWriter] = None
        response_task: Optional[asyncio.Task] = None
        defer_finish = False
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", self._port), timeout=10
            )

            async def exchange() -> dict:
                await self._write_command(writer, cmd, timeout)
                return await self._read_response(reader, timeout)

            # Shield the complete write/read exchange: cancellation can arrive
            # after the command bytes were sent but before drain() returns.
            response_task = asyncio.create_task(exchange())
            return await asyncio.shield(response_task)
        except asyncio.CancelledError:
            if response_task is not None and writer is not None:
                defer_finish = True
                deferred_writer = writer
                writer = None
                asyncio.create_task(
                    self._wait_for_request_after_cancel(
                        request_id, response_task, deferred_writer
                    )
                )
            raise
        except (
            asyncio.TimeoutError, asyncio.IncompleteReadError, ConnectionError, OSError
        ) as exc:
            self._logger.error("Detached worker command failed: %s", exc)
            return None
        finally:
            # 先释放活动计数，连接关闭只是后续有界清理，不能反向阻塞 stop()。
            if not defer_finish:
                await self._finish_request(request_id)
            await self._close_writer(writer)

    async def stream_cmd(
        self, cmd: dict, timeout: float = 600.0
    ) -> AsyncGenerator[dict, None]:
        if not self._port:
            return
        self.touch_activity()
        request_id = await self._register_request()
        model_path = cmd.get("model_path", "")
        completed = False
        defer_finish = False
        writer: Optional[asyncio.StreamWriter] = None
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", self._port), timeout=10
            )
            await self._write_command(writer, cmd, timeout)
            while True:
                message = await self._read_response(reader, timeout)
                yield message
                if message.get("type") == "done" or not message.get("ok", True):
                    completed = True
                    return
        except (
            asyncio.TimeoutError, asyncio.IncompleteReadError, ConnectionError, OSError
        ) as exc:
            # A stream is an independent client connection. Its failure must not
            # invalidate the main control connection or terminate the worker.
            self._logger.error("Worker stream failed: %s", exc)
            return
        finally:
            if not completed and self.alive and model_path:
                defer_finish = True
                asyncio.create_task(
                    self._wait_for_stream_after_cancel(request_id, model_path)
                )
            if not defer_finish:
                await self._finish_request(request_id)
            await self._close_writer(writer)

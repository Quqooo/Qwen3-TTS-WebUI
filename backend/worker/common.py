"""Model-independent worker utilities with lazy numerical dependencies."""
from __future__ import annotations

import base64
import contextlib
import hashlib
import logging
import os
from typing import Any, Dict, Iterator, List, Optional, Tuple

_logger = logging.getLogger("qwen-webui.worker.common")


def _numpy() -> Any:
    import numpy
    return numpy


def _torch() -> Any:
    import torch
    return torch


def decode_audio(value: str) -> Any:
    np = _numpy()
    return np.frombuffer(base64.b64decode(value), dtype=np.float32).copy()


def encode_audio(wav: Any) -> str:
    np = _numpy()
    data = np.asarray(wav, dtype=np.float32).tobytes()
    return base64.b64encode(data).decode("ascii")


def make_audio_result(result: Tuple[Any, int]) -> Dict[str, Any]:
    if not isinstance(result, tuple) or len(result) != 2:
        raise ValueError("Provider audio result must be a (wavs, sample_rate) tuple")
    wavs, sample_rate = result
    np = _numpy()
    if not isinstance(sample_rate, int) or sample_rate <= 0:
        raise ValueError(f"Provider returned invalid sample rate: {sample_rate}")
    if not isinstance(wavs, (list, tuple)) or not wavs:
        raise ValueError("Provider returned no audio")
    wav = np.asarray(wavs[0], dtype=np.float32)
    return {
        "ok": True,
        "audio": encode_audio(wav),
        "sr": int(sample_rate),
        "duration": float(len(wav) / sample_rate),
    }


def make_stream_chunk(result: Tuple[Any, int]) -> Dict[str, Any]:
    if not isinstance(result, tuple) or len(result) != 2:
        raise ValueError("Provider stream chunk must be an (audio, sample_rate) tuple")
    wav, sample_rate = result
    if not isinstance(sample_rate, int) or sample_rate <= 0:
        raise ValueError(f"Provider returned invalid stream sample rate: {sample_rate}")
    return {"type": "chunk", "data": encode_audio(wav), "sr": int(sample_rate)}


def release_cuda_cache() -> None:
    """Release CUDA allocator cache without making torch a core import."""
    try:
        torch = _torch()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def serialize_tensor(tensor: Any) -> Dict[str, Any]:
    torch = _torch()
    value = tensor.detach().cpu()
    if value.dtype in (torch.bfloat16, torch.half, torch.float64):
        value = value.float()
    arr = value.numpy()
    return {
        "data": base64.b64encode(arr.tobytes()).decode("ascii"),
        "dtype": str(arr.dtype),
        "shape": list(arr.shape),
    }


def deserialize_tensor(value: Dict[str, Any]) -> Any:
    np = _numpy()
    torch = _torch()
    arr = np.frombuffer(base64.b64decode(value["data"]), dtype=np.dtype(value["dtype"]))
    return torch.from_numpy(arr.reshape(value["shape"]).copy())


def resolve_device() -> str:
    """当前 Worker 的设备类型："cpu" 或 "cuda"（由主进程注入的环境变量决定）。"""
    return "cpu" if os.environ.get("QWEN_WEBUI_DEVICE") == "cpu" else "cuda"


def resolve_device_map() -> str:
    """HuggingFace device_map 参数：CPU 槽位返回 "cpu"，GPU 槽位返回 "cuda:0"。"""
    return "cpu" if resolve_device() == "cpu" else "cuda:0"


def resolve_dtype(value: Any) -> Any:
    """将 dtype 配置（"auto"/"bf16"/"fp16"/"float32" 或 torch.dtype）解析为 torch dtype。

    "auto" 优先 bf16，其次 fp16，最后 float32。
    """
    torch = _torch()
    if isinstance(value, torch.dtype):
        return value
    name = str(value or "auto").strip().lower()
    if name == "auto":
        if torch.cuda.is_available():
            return torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        mps = getattr(torch.backends, "mps", None)
        if mps is not None and mps.is_available():
            return torch.float16
        return torch.float32
    mapping = {
        "bf16": torch.bfloat16,
        "bfloat16": torch.bfloat16,
        "fp16": torch.float16,
        "float16": torch.float16,
        "float32": torch.float32,
        "fp32": torch.float32,
    }
    if name not in mapping:
        raise ValueError(f"Unsupported dtype: {value!r}")
    return mapping[name]


def resolve_attn_implementation(value: Any) -> str:
    """解析注意力实现配置："auto" 时优先 flash_attention_2，未安装则回退 sdpa。

    CPU 设备上 flash-attn 不可用：auto 与显式的 flash_attention_2/3 均回退 sdpa
    （含用户显式配置的 flash_attention_2/3，直接透传会导致 CPU 加载失败）。
    """
    name = str(value or "auto").strip().lower()
    if resolve_device() == "cpu":
        if name in ("", "auto", "flash_attention_2", "flash_attention_3"):
            if name.startswith("flash_attention"):
                _logger.info(
                    "attn_implementation %s is unavailable on CPU, falling back to sdpa",
                    name,
                )
            return "sdpa"
        return name
    if name in ("", "auto"):
        try:
            import importlib.util

            if importlib.util.find_spec("flash_attn") is not None:
                return "flash_attention_2"
        except Exception:
            pass
        return "sdpa"
    return name


def next_stream_item(generator: Any) -> Tuple[bool, Any]:
    try:
        return True, next(generator)
    except StopIteration:
        return False, None


def close_stream(generator: Any) -> None:
    close = getattr(generator, "close", None)
    if callable(close):
        close()


def load_voice_payload(path: str) -> Dict[str, Any]:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Voice file not found: {path}")
    return _torch().load(path, map_location="cpu", weights_only=True)


def save_voice_payload(path: str, items: List[Dict[str, Any]]) -> str:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    _torch().save({"items": items}, path)
    return path


def read_voice_meta(path: str) -> Dict[str, Any]:
    if not os.path.isfile(path):
        return {"ok": False, "error": f"File not found: {path}"}
    try:
        payload = load_voice_payload(path)
        if isinstance(payload, dict):
            items = payload.get("items", [])
        elif isinstance(payload, list):
            items = payload
        else:
            return {"ok": False, "error": "Invalid voice file format"}
        text = ""
        x_vector_only = False
        spk_dim = 0
        if items and isinstance(items[0], dict):
            text = items[0].get("ref_text", "") or ""
            x_vector_only = bool(items[0].get("x_vector_only_mode", False))
            ref_spk = items[0].get("ref_spk_embedding")
            if ref_spk is not None:
                shape = getattr(ref_spk, "shape", None)
                spk_dim = int(shape[-1]) if shape is not None else len(ref_spk)
        name = os.path.splitext(os.path.basename(path))[0]
        return {"ok": True, "meta": {
            "customName": name,
            "text": text,
            "x_vector_only": x_vector_only,
            "_spk_dim": spk_dim,
        }}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def update_voice_meta(
    path: str,
    item_updates: Optional[Dict[str, Any]],
) -> str:
    payload = load_voice_payload(path)
    if isinstance(payload, dict):
        items = payload.get("items", [])
    elif isinstance(payload, list):
        items = payload
    else:
        items = []
    for index_value, update in (item_updates or {}).items():
        index = int(index_value)
        if 0 <= index < len(items) and isinstance(items[index], dict):
            items[index].update(update)
    return save_voice_payload(path, items)


def derive_stream_seed(seed: int, stream: str) -> int:
    """从请求 seed 派生独立随机流的种子，避免简单加法带来的流间关联。"""
    digest = hashlib.sha256(f"qwen3tts-seed:{seed}:{stream}".encode()).digest()
    return int.from_bytes(digest[:8], "big") & 0x7FFFFFFFFFFFFFFF


@contextlib.contextmanager
def scoped_torch_seed(seed: int) -> Iterator[None]:
    """请求作用域内固定全局 RNG，退出时恢复原状态，避免污染后续请求。

    适用于底层走 HF `generate`（不接受 generator 参数）的路径；依赖调用方
    串行执行保证同一时刻只有一个请求使用全局 RNG。
    """
    torch = _torch()
    cpu_state = torch.get_rng_state()
    cuda_states = torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None
    torch.manual_seed(seed)
    if cuda_states is not None:
        torch.cuda.manual_seed_all(seed)
    try:
        yield
    finally:
        torch.set_rng_state(cpu_state)
        if cuda_states is not None:
            torch.cuda.set_rng_state_all(cuda_states)

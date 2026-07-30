"""
音频处理工具模块

包含音频格式转换、增益调整、重采样、归一化、URL 音频下载等
与具体后端分支无关的通用音频处理函数。
"""
import base64
import io
import ipaddress
import os
import re
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse
from urllib.request import urlopen, Request as URLRequest

import numpy as np
import soundfile as sf

try:
    import librosa
except ImportError:
    librosa = None

# 支持的音频格式对应的 MIME 类型
MEDIA_TYPES: Dict[str, str] = {
    "mp3": "audio/mpeg",
    "opus": "audio/ogg",
    "wav": "audio/wav",
    "pcm": "audio/L16",
    "aac": "audio/aac",
    "flac": "audio/flac",
    "ogg": "audio/ogg",
}


def _has_ffmpeg() -> bool:
    """检查系统是否安装了 ffmpeg

    用于 mp3/opus/aac 格式的转换。
    """
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


_HAS_FFMPEG = _has_ffmpeg()

_BLOCKED_NETS = [
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.168.0.0/16"),
    ipaddress.IPv4Network("127.0.0.0/8"),
    ipaddress.IPv4Network("169.254.0.0/16"),
    ipaddress.IPv6Network("::1/128"),
    ipaddress.IPv6Network("fc00::/7"),
    ipaddress.IPv6Network("fe80::/10"),
]


def _validate_remote_url(url: str):
    """Raise ValueError if URL resolves to a loopback, private, or link-local address."""
    hostname = urlparse(url).hostname
    if not hostname:
        raise ValueError("Invalid URL: no hostname")

    try:
        ip = ipaddress.ip_address(hostname)
        if any(ip in net for net in _BLOCKED_NETS):
            raise ValueError(f"URL resolves to a blocked address: {hostname}")
        return
    except ValueError:
        pass

    try:
        addrs = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise ValueError(f"Cannot resolve hostname: {hostname}")

    for _family, _type, _proto, _cname, sockaddr in addrs:
        ip = sockaddr[0]
        try:
            addr = ipaddress.ip_address(ip)
            if any(addr in net for net in _BLOCKED_NETS):
                raise ValueError(f"URL resolves to a blocked address: {hostname} → {ip}")
        except ValueError:
            pass


def download_audio(url: str) -> Tuple[np.ndarray, int]:
    """从 URL 或 data URI 下载音频数据

    支持：
    - http(s)://  URL
    - data:audio/...;base64,...  data URI
    返回 (waveform, sample_rate)。
    """
    parsed = urlparse(url)
    if parsed.scheme.startswith("data"):
        match = re.match(r"data:audio/\w+;base64,(.+)", url)
        if not match:
            raise ValueError("Invalid data URI format")
        raw = base64.b64decode(match.group(1))
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(raw)
            tmp_path = tmp.name
        try:
            wav, sr = sf.read(tmp_path)
        finally:
            os.unlink(tmp_path)
        return wav, sr
    else:
        _validate_remote_url(url)
        req = URLRequest(url, headers={"User-Agent": "Qwen3-TTS-API/1.0"})
        with urlopen(req, timeout=60) as resp:
            data = resp.read()
        suffix = Path(urlparse(url).path).suffix or ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        try:
            wav, sr = sf.read(tmp_path)
        finally:
            os.unlink(tmp_path)
        return wav, int(sr)


def apply_gain(wav: np.ndarray, gain_db: float) -> np.ndarray:
    """应用增益（分贝）"""
    if abs(gain_db) < 1e-6:
        return wav
    factor = 10.0 ** (gain_db / 20.0)
    return np.clip(wav * factor, -1.0, 1.0)


def normalize_audio(wav: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    """归一化音频到 [-1.0, 1.0] 范围

    多声道取平均；归一化后裁剪超出部分。
    """
    x = np.asarray(wav, dtype=np.float32)
    if x.ndim > 1:
        x = np.mean(x, axis=-1)
    m = np.max(np.abs(x)) if x.size else 0.0
    if m > 1.0 + 1e-6:
        x = x / (m + eps)
    return np.clip(x, -1.0, 1.0)


def resample(wav: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """重采样音频到目标采样率

    优先使用 librosa，否则使用 numpy 线性插值。
    """
    if orig_sr == target_sr:
        return wav
    if librosa is not None:
        return librosa.resample(wav, orig_sr=orig_sr, target_sr=target_sr)
    ratio = target_sr / orig_sr
    new_len = int(len(wav) * ratio)
    return np.interp(
        np.linspace(0, len(wav) - 1, new_len),
        np.arange(len(wav)),
        wav,
    ).astype(np.float32)


def convert_audio(wav: np.ndarray, sr: int, fmt: str) -> bytes:
    """将音频数组转换为指定格式的字节数据

    支持的格式: wav, flac, ogg, pcm, mp3, opus, aac
    mp3/opus/aac 需要 ffmpeg。
    """
    if fmt == "pcm":
        int16 = (wav * 32767).astype(np.int16)
        return int16.tobytes()

    if fmt == "wav":
        buf = io.BytesIO()
        sf.write(buf, wav, sr, format="WAV", subtype="PCM_16")
        return buf.getvalue()

    if fmt == "flac":
        buf = io.BytesIO()
        sf.write(buf, wav, sr, format="FLAC")
        return buf.getvalue()

    if fmt in ("mp3", "opus", "aac"):
        if not _HAS_FFMPEG:
            raise RuntimeError(f"Format '{fmt}' requires ffmpeg")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_in:
            sf.write(tmp_in, wav, sr, format="WAV", subtype="PCM_16")
            tmp_in_path = tmp_in.name
        tmp_out_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=f".{fmt}", delete=False) as tmp_out:
                tmp_out_path = tmp_out.name
            codec_map = {"mp3": "libmp3lame", "opus": "libopus", "aac": "aac"}
            subprocess.run(
                ["ffmpeg", "-y", "-i", tmp_in_path,
                 "-codec:a", codec_map[fmt],
                 "-b:a", "192k" if fmt == "mp3" else "128k",
                 tmp_out_path],
                capture_output=True, check=True, timeout=120,
            )
            with open(tmp_out_path, "rb") as f:
                return f.read()
        finally:
            os.unlink(tmp_in_path)
            if tmp_out_path and os.path.exists(tmp_out_path):
                os.unlink(tmp_out_path)

    if fmt == "ogg":
        buf = io.BytesIO()
        sf.write(buf, wav, sr, format="OGG")
        return buf.getvalue()

    raise ValueError(f"Unsupported format: {fmt}")


def split_text(text: str, chars: Optional[List[str]] = None) -> List[str]:
    """按指定字符切分文本"""
    if not chars:
        return [text]
    pattern = "|".join(re.escape(c) for c in chars)
    parts = [p.strip() for p in re.split(pattern, text) if p.strip()]
    return parts if parts else [text]


def estimate_duration(wav: np.ndarray, sr: int) -> float:
    """估算音频时长（秒）"""
    return len(wav) / sr if sr > 0 else 0.0

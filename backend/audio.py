"""
音频处理工具模块

包含音频格式转换、增益调整、重采样、归一化、URL 音频下载等
与具体后端分支无关的通用音频处理函数。
"""
import base64
import binascii
import io
import ipaddress
import os
import re
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError
from urllib.parse import urljoin, urlparse
from urllib.request import build_opener, HTTPRedirectHandler, Request as URLRequest

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

MAX_AUDIO_BYTES = 200 * 1024 * 1024
_DOWNLOAD_CHUNK_BYTES = 64 * 1024
_MAX_REDIRECTS = 5

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


def _is_blocked_address(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return whether an address must not be contacted by remote audio fetches."""
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
        or any(addr in net for net in _BLOCKED_NETS)
    )


def _validate_remote_url(url: str) -> None:
    """Raise ValueError unless URL is HTTP(S) and resolves only to public addresses."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Remote audio URL must use HTTP or HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Remote audio URL must not contain credentials")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Invalid URL: no hostname")

    try:
        literal_addr = ipaddress.ip_address(hostname)
    except ValueError:
        literal_addr = None

    if literal_addr is not None:
        if _is_blocked_address(literal_addr):
            raise ValueError(f"URL resolves to a blocked address: {hostname}")
        return

    try:
        addrs = socket.getaddrinfo(hostname, parsed.port, type=socket.SOCK_STREAM)
    except (socket.gaierror, ValueError) as exc:
        raise ValueError(f"Cannot resolve hostname: {hostname}") from exc

    if not addrs:
        raise ValueError(f"Cannot resolve hostname: {hostname}")

    for _family, _type, _proto, _cname, sockaddr in addrs:
        ip = sockaddr[0]
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError as exc:
            raise ValueError(f"Hostname resolved to an invalid address: {ip}") from exc
        if _is_blocked_address(addr):
            raise ValueError(f"URL resolves to a blocked address: {hostname} -> {ip}")


class _RejectRedirectHandler(HTTPRedirectHandler):
    """Disable urllib's automatic redirects so every hop can be revalidated."""

    def redirect_request(self, req: Any, fp: Any, code: Any, msg: Any, headers: Any, newurl: Any) -> None:
        return None


def _decode_audio_data_uri(url: str) -> bytes:
    """Decode an audio data URI without allowing more than MAX_AUDIO_BYTES."""
    match = re.fullmatch(r"data:audio/[\w.+-]+;base64,([A-Za-z0-9+/=\r\n]+)", url)
    if not match:
        raise ValueError("Invalid data URI format")

    encoded = match.group(1)
    compact = "".join(encoded.split())
    if len(compact) % 4 != 0:
        raise ValueError("Invalid base64 audio data")
    padding = len(compact) - len(compact.rstrip("="))
    decoded_size = (len(compact) // 4) * 3 - padding
    if decoded_size > MAX_AUDIO_BYTES:
        raise ValueError("Audio input exceeds the 50 MB limit")

    try:
        raw = base64.b64decode(compact, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("Invalid base64 audio data") from exc
    if len(raw) > MAX_AUDIO_BYTES:
        raise ValueError("Audio input exceeds the 50 MB limit")
    return raw


def _download_remote_audio(url: str) -> Tuple[bytes, str]:
    """Download public HTTP(S) audio with redirect and 50 MB enforcement."""
    opener = build_opener(_RejectRedirectHandler())
    current_url = url

    for redirect_count in range(_MAX_REDIRECTS + 1):
        _validate_remote_url(current_url)
        req = URLRequest(current_url, headers={"User-Agent": "Qwen3-TTS-API/1.0"})
        try:
            resp = opener.open(req, timeout=60)
        except HTTPError as exc:
            if exc.code not in (301, 302, 303, 307, 308):
                raise
            if redirect_count >= _MAX_REDIRECTS:
                raise ValueError("Too many redirects while downloading audio") from exc
            location = exc.headers.get("Location")
            if not location:
                raise ValueError("Audio redirect is missing a Location header") from exc
            current_url = urljoin(current_url, location)
            continue

        with resp:
            final_url = resp.geturl()
            _validate_remote_url(final_url)
            content_length = resp.headers.get("Content-Length")
            if content_length is not None:
                try:
                    declared_size = int(content_length)
                except ValueError as exc:
                    raise ValueError("Invalid audio Content-Length header") from exc
                if declared_size < 0:
                    raise ValueError("Invalid audio Content-Length header")
                if declared_size > MAX_AUDIO_BYTES:
                    raise ValueError("Audio input exceeds the 50 MB limit")

            chunks = []
            total = 0
            while True:
                chunk = resp.read(_DOWNLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_AUDIO_BYTES:
                    raise ValueError("Audio input exceeds the 50 MB limit")
                chunks.append(chunk)
            return b"".join(chunks), final_url

    raise ValueError("Too many redirects while downloading audio")


def download_audio(url: str) -> Tuple[np.ndarray, int]:
    """从 URL 或 data URI 下载音频数据，输入上限为 50 MB。

    支持：
    - http(s)://  URL
    - data:audio/...;base64,...  data URI
    返回 (waveform, sample_rate)。
    """
    parsed = urlparse(url)
    if parsed.scheme == "data":
        raw = _decode_audio_data_uri(url)
        suffix = ".wav"
    else:
        raw, final_url = _download_remote_audio(url)
        suffix = Path(urlparse(final_url).path).suffix or ".wav"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(raw)
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

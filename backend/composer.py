"""
音频合成引擎

Pure-audio compositing: silence detection, trimming, time-stretch,
overlap mixing, and SRT subtitle generation.  No TTS model dependency.
"""
import base64
import binascii
import io
import logging
import math
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
import soundfile as sf

try:
    import librosa
except ImportError:
    librosa = None

from .audio import apply_gain, normalize_audio, resample

logger = logging.getLogger("qwen-webui.composer")

SILENCE_THRESHOLD_DB = -35
FRAME_MS = 20
HOP_MS = 10
MAX_OUTPUT_SAMPLES = 100_000_000
MAX_DECODED_SAMPLES = 100_000_000
MAX_TOTAL_DECODED_SAMPLES = 100_000_000
MAX_TIME_STRETCH_RATE = 16.0


@dataclass
class SegmentInput:
    sort: int
    audio_b64: str
    start: Optional[float] = None
    end: Optional[float] = None
    text: str = ""


@dataclass
class SRTEntry:
    index: int
    start_s: float
    end_s: float
    text: str = ""


@dataclass
class ComposedSegment:
    wav: np.ndarray
    start_sample: int = 0
    seg_sort: int = 0
    source: Optional[SegmentInput] = None
    speech_start_sample: int = 0
    speech_end_sample: int = 0


def decode_base64_audio(b64: str, target_sr: Optional[int] = None) -> Tuple[np.ndarray, int]:
    try:
        raw = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("audio must be valid base64") from exc
    if not raw:
        raise ValueError("audio must not be empty")
    audio_io = io.BytesIO(raw)
    try:
        info = sf.info(audio_io)
        if info.frames <= 0 or info.samplerate <= 0:
            raise ValueError("audio must contain samples")
        projected_frames = info.frames
        if target_sr is not None:
            projected_frames = math.ceil(info.frames * target_sr / info.samplerate)
        if projected_frames > MAX_DECODED_SAMPLES:
            raise ValueError("decoded audio is too long")
        audio_io.seek(0)
        wav, sr = sf.read(audio_io, dtype="float32", always_2d=False)
    except RuntimeError as exc:
        raise ValueError("audio must contain a supported audio file") from exc
    if not np.all(np.isfinite(wav)):
        raise ValueError("audio samples must be finite")
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    return wav.astype(np.float32), sr


def _rms_frames(wav: np.ndarray, frame_len: int, hop_len: int) -> Tuple[np.ndarray, List[int]]:
    last_start = max(0, len(wav) - frame_len)
    starts = list(range(0, last_start + 1, hop_len))
    if not starts or starts[-1] != last_start:
        starts.append(last_start)
    rms = np.zeros(len(starts), dtype=np.float32)
    for i, s in enumerate(starts):
        rms[i] = np.sqrt(np.mean(wav[s : s + frame_len] ** 2))
    return rms, starts


def detect_silence_samples(wav: np.ndarray, sr: int) -> Tuple[int, int]:
    """Return (first_non_silent_sample, last_non_silent_sample)."""
    if len(wav) < sr * 0.02:
        return 0, len(wav)
    frame_len = max(1, int(sr * FRAME_MS / 1000))
    hop_len = max(1, int(sr * HOP_MS / 1000))
    rms, starts = _rms_frames(wav, frame_len, hop_len)
    peak = np.max(rms)
    if peak < 1e-10:
        return 0, 0
    thr = peak * (10.0 ** (SILENCE_THRESHOLD_DB / 20.0))
    non_silent = rms >= thr
    if not np.any(non_silent):
        return 0, len(wav)
    first_frame = int(np.argmax(non_silent))
    last_frame = int(len(non_silent) - np.argmax(non_silent[::-1]) - 1)
    first = 0 if first_frame == 0 else starts[first_frame] + frame_len // 2
    last = len(wav) if last_frame == len(non_silent) - 1 else starts[last_frame] + frame_len // 2
    return max(0, first), min(len(wav), last)


def _atempo_filter(rate: float) -> str:
    factors: List[float] = []
    while rate > 2.0:
        factors.append(2.0)
        rate /= 2.0
    while rate < 0.5:
        factors.append(0.5)
        rate /= 0.5
    factors.append(rate)
    return ",".join(f"atempo={factor:.10g}" for factor in factors)


def time_stretch(wav: np.ndarray, rate: float, sr: int) -> np.ndarray:
    """Time-stretch without pitch change. rate > 1 = speed up = shorter."""
    if abs(rate - 1.0) < 1e-6:
        return wav
    if rate <= 0:
        raise ValueError("time-stretch rate must be positive")
    if not 1 / MAX_TIME_STRETCH_RATE <= rate <= MAX_TIME_STRETCH_RATE:
        raise ValueError(f"time-stretch rate must be between 1/{MAX_TIME_STRETCH_RATE:g} and {MAX_TIME_STRETCH_RATE:g}")
    if librosa is not None:
        return librosa.effects.time_stretch(y=wav.astype(np.float64), rate=rate).astype(np.float32)

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("Pitch-preserving time stretch requires librosa or ffmpeg")

    input_path = output_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as input_file:
            input_path = input_file.name
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as output_file:
            output_path = output_file.name
        sf.write(input_path, wav, sr, format="WAV", subtype="FLOAT")
        subprocess.run(
            [
                ffmpeg,
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-i",
                input_path,
                "-filter:a",
                _atempo_filter(rate),
                "-ar",
                str(sr),
                "-ac",
                "1",
                output_path,
            ],
            capture_output=True,
            check=True,
            timeout=120,
        )
        stretched, _ = sf.read(output_path, dtype="float32", always_2d=False)
        return np.asarray(stretched, dtype=np.float32)
    finally:
        if input_path and os.path.exists(input_path):
            os.unlink(input_path)
        if output_path and os.path.exists(output_path):
            os.unlink(output_path)


def _fit_duration(wav: np.ndarray, target_samples: int, sr: int) -> np.ndarray:
    if target_samples <= 0:
        return np.array([], dtype=np.float32)
    if len(wav) == 0:
        return np.zeros(target_samples, dtype=np.float32)
    stretched = time_stretch(wav, len(wav) / target_samples, sr)
    if len(stretched) > target_samples:
        return stretched[:target_samples]
    if len(stretched) < target_samples:
        return np.pad(stretched, (0, target_samples - len(stretched)))
    return stretched


def compose(
    segments: List[SegmentInput],
    mode: str,
    sr: int,
    gain_db: float = 0.0,
    min_silence_ms: float = 0.0,
) -> Tuple[np.ndarray, List[SRTEntry]]:
    """
    Compose multiple audio segments with timeline alignment.

    Args:
        segments: Audio segments to compose.
        mode: 'lenient' or 'strict'.
        sr: Target sample rate.
        gain_db: Output gain in dB.
        min_silence_ms: Minimum silence between adjacent segments (ms).
            - lenient mode: min_silence has higher priority than timeline.
              Always ensures minimum gap; timeline is respected only after.
            - strict mode: min_silence is ignored for timeline segments;
              only applied between untimed segments.

    Returns (composite_wav, srt_entries).
    """
    if mode not in ("lenient", "strict"):
        raise ValueError("mode must be 'lenient' or 'strict'")
    if sr <= 0:
        raise ValueError("sample rate must be positive")
    if not math.isfinite(gain_db) or not -120 <= gain_db <= 24:
        raise ValueError("gain must be between -120 and 24 dB")
    if not math.isfinite(min_silence_ms) or min_silence_ms < 0:
        raise ValueError("minimum silence must be non-negative")

    sorted_segs = sorted(segments, key=lambda s: s.sort)
    previous_timeline_start: Optional[float] = None
    for seg in sorted_segs:
        if seg.start is None:
            continue
        if not math.isfinite(seg.start) or seg.start < 0:
            raise ValueError("segment start must be a non-negative finite number")
        if seg.end is not None and (not math.isfinite(seg.end) or seg.end < seg.start):
            raise ValueError("segment end must be finite and not before start")
        if previous_timeline_start is not None and seg.start < previous_timeline_start:
            raise ValueError("timeline start values must be non-decreasing in sort order")
        previous_timeline_start = seg.start
    min_silence_samples = round(min_silence_ms / 1000 * sr)
    if min_silence_samples > MAX_OUTPUT_SAMPLES:
        raise ValueError("minimum silence is too large")

    decoded: List[Tuple[SegmentInput, np.ndarray, int, int]] = []
    total_decoded_samples = 0
    for seg in sorted_segs:
        if (
            mode == "strict"
            and seg.start is not None
            and seg.end is not None
            and round(seg.start * sr) == round(seg.end * sr)
        ):
            continue
        wav, seg_sr = decode_base64_audio(seg.audio_b64, sr)
        if seg_sr != sr:
            wav = resample(wav, seg_sr, sr)
        wav = np.asarray(wav, dtype=np.float32)
        total_decoded_samples += len(wav)
        if total_decoded_samples > MAX_TOTAL_DECODED_SAMPLES:
            raise ValueError("total decoded audio is too long")
        speech_start, speech_end = detect_silence_samples(wav, sr)
        decoded.append((seg, wav, speech_start, speech_end))

    timeline = [item for item in decoded if item[0].start is not None]
    untimed = [item for item in decoded if item[0].start is None]
    placed: List[ComposedSegment] = []

    # Timeline segments are handled first, in task order. Untimed segments are
    # deliberately deferred so they can never displace a timeline segment.
    previous: Optional[ComposedSegment] = None
    for seg, original, speech_start, speech_end in timeline:
        target_start = round(seg.start * sr)
        if target_start > MAX_OUTPUT_SAMPLES:
            raise ValueError("requested segment start is too large")
        if mode == "lenient":
            wav = original[speech_start:]
            audible_end = max(0, speech_end - speech_start)
            actual_start = target_start
            if previous is not None:
                minimum_start = previous.start_sample + previous.speech_end_sample + min_silence_samples
                actual_start = max(target_start, minimum_start)
                previous_end = previous.start_sample + len(previous.wav)
                if previous_end > actual_start:
                    previous.wav = previous.wav[: actual_start - previous.start_sample]
            current = ComposedSegment(
                wav=wav,
                start_sample=actual_start,
                seg_sort=seg.sort,
                source=seg,
                speech_start_sample=0,
                speech_end_sample=audible_end,
            )
        else:
            wav = original[speech_start:speech_end]
            if seg.end is not None:
                target_duration = round((seg.end - seg.start) * sr)
                if target_start + target_duration > MAX_OUTPUT_SAMPLES:
                    raise ValueError("requested segment end is too large")
                wav = _fit_duration(wav, target_duration, sr)
            if (
                previous is not None
                and previous.start_sample + len(previous.wav) > target_start
                and previous.source is not None
                and previous.source.end is None
            ):
                available = target_start - previous.start_sample
                if available > 0:
                    previous.wav = _fit_duration(previous.wav, available, sr)
                    previous.speech_end_sample = len(previous.wav)
                else:
                    logger.warning(
                        "Cannot shorten segment %s to non-positive duration before segment %s; mixing overlap",
                        previous.seg_sort,
                        seg.sort,
                    )
            current = ComposedSegment(
                wav=wav,
                start_sample=target_start,
                seg_sort=seg.sort,
                source=seg,
                speech_start_sample=0,
                speech_end_sample=len(wav),
            )
        placed.append(current)
        previous = current

    # Untimed audio keeps all original leading/trailing silence. Add only the
    # silence missing from the natural gap between actual speech regions.
    for seg, original, speech_start, speech_end in untimed:
        waveform_end = max((p.start_sample + len(p.wav) for p in placed), default=0)
        audible_end = max((p.start_sample + p.speech_end_sample for p in placed), default=0)
        start_sample = waveform_end
        previous_is_untimed = bool(placed) and placed[-1].source is not None and placed[-1].source.start is None
        if placed and (mode == "lenient" or previous_is_untimed):
            natural_speech_start = waveform_end + speech_start
            start_sample += max(0, audible_end + min_silence_samples - natural_speech_start)
        current = ComposedSegment(
            wav=original,
            start_sample=start_sample,
            seg_sort=seg.sort,
            source=seg,
            speech_start_sample=speech_start,
            speech_end_sample=speech_end,
        )
        placed.append(current)

    # Build the final waveform. Absolute placement naturally produces strict
    # mode overlap by summing simultaneously playing segments.
    total_len = max((p.start_sample + len(p.wav)) for p in placed) if placed else 0
    if total_len > MAX_OUTPUT_SAMPLES:
        raise ValueError("composed audio is too long")
    result = np.zeros(total_len, dtype=np.float32)
    for p in placed:
        e = p.start_sample + len(p.wav)
        result[p.start_sample:e] += p.wav

    result = normalize_audio(result)
    if abs(gain_db) > 1e-6:
        result = apply_gain(result, gain_db)

    # Subtitles use the same placement records as audio, so lenient and untimed
    # entries reflect actual detected speech after all collision handling.
    srt_entries: List[SRTEntry] = []
    for p in placed:
        seg = p.source
        if seg is None:
            continue
        text = "\n".join(line for line in seg.text.strip().splitlines() if line.strip()) or f"Segment {seg.sort}"
        if mode == "strict" and seg.start is not None:
            s_start = seg.start
            s_end = seg.end if seg.end is not None else (p.start_sample + p.speech_end_sample) / sr
        else:
            s_start = (p.start_sample + p.speech_start_sample) / sr
            s_end = (p.start_sample + p.speech_end_sample) / sr
        srt_entries.append(SRTEntry(index=0, start_s=s_start, end_s=s_end, text=text))

    srt_entries.sort(key=lambda e: e.start_s)
    for i, entry in enumerate(srt_entries):
        entry.index = i + 1

    return result, srt_entries


def build_srt(entries: List[SRTEntry]) -> str:
    """Format SRT entries into a .srt string."""
    lines: List[str] = []
    for e in entries:
        lines.append(str(e.index))
        lines.append(f"{_fmt_srt_time(e.start_s)} --> {_fmt_srt_time(e.end_s)}")
        lines.append(e.text)
        lines.append("")
    return "\n".join(lines)


def _fmt_srt_time(s: float) -> str:
    total_ms = max(0, round(s * 1000))
    h, remainder = divmod(total_ms, 3_600_000)
    m, remainder = divmod(remainder, 60_000)
    sec, ms = divmod(remainder, 1000)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"

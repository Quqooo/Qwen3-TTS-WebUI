"""
批量任务 API — 音频合成

POST /api/batch/compose
    将多段已生成的音频按时间轴对齐并合成为一条音频 + SRT 字幕。
"""
import asyncio
import base64
import logging
import math
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from .. import composer as composer_module
from ..audio import MEDIA_TYPES, convert_audio, estimate_duration
from ..composer import (
    SegmentInput,
    compose,
    build_srt,
)
from ..config import settings
from ..errors import raise_error

logger = logging.getLogger("qwen-webui.batch")

router = APIRouter(prefix="/api", tags=["batch"])

_compose_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="compose")

_DEFAULT_MAX_SEGMENTS = 1000
_DEFAULT_MAX_OUTPUT_SAMPLES = 100_000_000
_DEFAULT_MAX_DECODED_SAMPLES = 100_000_000
_DEFAULT_MAX_TOTAL_DECODED_SAMPLES = 100_000_000
_DEFAULT_MAX_TIME_STRETCH_RATE = 16.0
_DEFAULT_MAX_AUDIO_MIB = 32
_DEFAULT_MAX_TOTAL_AUDIO_MIB = 256
_DEFAULT_MIN_SAMPLE_RATE = 8000
_DEFAULT_MAX_SAMPLE_RATE = 192000


def _effective_limits() -> dict:
    config = settings.batch_composer or {}
    return {
        "max_segments": config.get("max_segments", _DEFAULT_MAX_SEGMENTS),
        "max_output_samples": config.get("max_output_samples", _DEFAULT_MAX_OUTPUT_SAMPLES),
        "max_decoded_samples": config.get("max_decoded_samples", _DEFAULT_MAX_DECODED_SAMPLES),
        "max_total_decoded_samples": config.get("max_total_decoded_samples", _DEFAULT_MAX_TOTAL_DECODED_SAMPLES),
        "max_time_stretch_rate": config.get("max_time_stretch_rate", _DEFAULT_MAX_TIME_STRETCH_RATE),
        "max_audio_chars": int(config.get("max_audio_mib", _DEFAULT_MAX_AUDIO_MIB) * 1024 * 1024),
        "max_total_audio_chars": int(config.get("max_total_audio_mib", _DEFAULT_MAX_TOTAL_AUDIO_MIB) * 1024 * 1024),
        "min_sample_rate": config.get("min_sample_rate", _DEFAULT_MIN_SAMPLE_RATE),
        "max_sample_rate": config.get("max_sample_rate", _DEFAULT_MAX_SAMPLE_RATE),
    }


def _apply_composer_limits(limits: dict):
    composer_module.MAX_OUTPUT_SAMPLES = limits["max_output_samples"]
    composer_module.MAX_DECODED_SAMPLES = limits["max_decoded_samples"]
    composer_module.MAX_TOTAL_DECODED_SAMPLES = limits["max_total_decoded_samples"]
    composer_module.MAX_TIME_STRETCH_RATE = limits["max_time_stretch_rate"]


class ComposeSegment(BaseModel):
    sort: int
    audio: str
    start: Optional[float] = None
    end: Optional[float] = None
    text: str = ""


class ComposeRequest(BaseModel):
    segments: List[ComposeSegment]
    mode: str = "lenient"
    format: str = "wav"
    sample_rate: int = 24000
    gain_db: float = 0.0
    min_silence_ms: float = 200.0


class ComposeResponse(BaseModel):
    audio_base64: str
    subtitle_srt: str
    format: str
    duration: float
    sample_rate: int


def _run_compose(body: ComposeRequest) -> ComposeResponse:
    limits = _effective_limits()
    _apply_composer_limits(limits)

    segments = [
        SegmentInput(
            sort=s.sort,
            audio_b64=s.audio,
            start=s.start,
            end=s.end,
            text=s.text,
        )
        for s in body.segments
    ]

    wav, srt_entries = compose(
        segments=segments,
        mode=body.mode,
        sr=body.sample_rate,
        gain_db=body.gain_db,
        min_silence_ms=body.min_silence_ms,
    )

    fmt = body.format.lower()
    if fmt not in MEDIA_TYPES:
        raise ValueError(f"Unsupported format: {fmt}")

    audio_bytes = convert_audio(wav, body.sample_rate, fmt)
    srt_str = build_srt(srt_entries)
    dur = estimate_duration(wav, body.sample_rate)

    return ComposeResponse(
        audio_base64=base64.b64encode(audio_bytes).decode("ascii"),
        subtitle_srt=srt_str,
        format=fmt,
        duration=round(dur, 3),
        sample_rate=body.sample_rate,
    )


@router.post("/batch/compose", response_model=ComposeResponse)
async def batch_compose(body: ComposeRequest) -> ComposeResponse:
    """将多段音频按时间轴对齐并合成为一条音频 + SRT 字幕。"""
    limits = _effective_limits()

    if body.mode not in ("lenient", "strict"):
        raise_error(status_code=422, detail="mode must be 'lenient' or 'strict'")
    if not limits["min_sample_rate"] <= body.sample_rate <= limits["max_sample_rate"]:
        raise_error(
            status_code=422,
            detail=f"sample_rate must be between {limits['min_sample_rate']} and {limits['max_sample_rate']}",
        )
    if not math.isfinite(body.gain_db) or not -120 <= body.gain_db <= 24:
        raise_error(status_code=422, detail="gain_db must be between -120 and 24")
    max_duration_s = limits["max_output_samples"] / body.sample_rate
    if (
        not math.isfinite(body.min_silence_ms)
        or body.min_silence_ms < 0
        or body.min_silence_ms > max_duration_s * 1000
    ):
        raise_error(status_code=422, detail="min_silence_ms must be a non-negative finite number")
    if body.format.lower() not in MEDIA_TYPES:
        raise_error(status_code=422, detail=f"Unsupported format: {body.format}")
    if not body.segments:
        raise_error(status_code=422, detail="segments must not be empty")
    if len(body.segments) > limits["max_segments"]:
        raise_error(status_code=422, detail=f"segments must contain at most {limits['max_segments']} items")
    total_audio_chars = sum(len(seg.audio) for seg in body.segments)
    if any(len(seg.audio) > limits["max_audio_chars"] for seg in body.segments):
        raise_error(status_code=413, detail="A segment audio payload is too large")
    if total_audio_chars > limits["max_total_audio_chars"]:
        raise_error(status_code=413, detail="Total audio payload is too large")
    sorts = [s.sort for s in body.segments]
    if len(sorts) != len(set(sorts)):
        raise_error(status_code=422, detail="Segment sort values must be unique")
    for seg in body.segments:
        if seg.start is not None and (not math.isfinite(seg.start) or seg.start < 0):
            raise_error(status_code=422, detail="start must be a non-negative finite number")
        if seg.end is not None and seg.start is None:
            raise_error(status_code=422, detail="end requires start")
        if seg.end is not None and not math.isfinite(seg.end):
            raise_error(status_code=422, detail="end must be finite")
        if seg.start is not None and seg.end is not None and seg.end < seg.start:
            raise_error(status_code=422, detail="end must be >= start")
        if seg.start is not None and seg.start > max_duration_s:
            raise_error(status_code=422, detail="start exceeds the maximum output duration")
        if seg.end is not None and seg.end > max_duration_s:
            raise_error(status_code=422, detail="end exceeds the maximum output duration")

    timeline_starts = [seg.start for seg in sorted(body.segments, key=lambda seg: seg.sort) if seg.start is not None]
    if any(current < previous for previous, current in zip(timeline_starts, timeline_starts[1:])):
        raise_error(
            status_code=422,
            detail="Timeline start values must be non-decreasing in sort order",
        )

    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(_compose_executor, _run_compose, body)
    except ValueError as e:
        raise_error(status_code=422, detail="Invalid compose parameters", debug=str(e))
    except Exception as e:
        logger.error("Compose failed: %s", e, exc_info=True)
        raise_error(status_code=500, detail="Audio compose failed", debug=str(e))

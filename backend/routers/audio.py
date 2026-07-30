"""
通用音频处理 API 路由

提供与 TTS 模型无关的音频处理操作，如裁剪、格式转换等。
"""
import base64

import numpy as np
from fastapi import APIRouter
from pydantic import BaseModel

from ..audio import convert_audio, download_audio
from ..errors import raise_error

router = APIRouter(prefix="/api/audio", tags=["audio"])


class TrimRequest(BaseModel):
    audio: str       # base64-encoded WAV or URL
    start: float     # 裁剪起始时间（秒）
    end: float       # 裁剪结束时间（秒）


@router.post("/trim")
async def trim_audio(body: TrimRequest):
    """裁剪音频"""
    if body.start >= body.end:
        raise_error(status_code=400, detail="start must be less than end")

    try:
        wav, sr = download_audio(body.audio)
    except Exception as e:
        raise_error(status_code=400, detail="Failed to read audio", debug=str(e))

    wav = np.asarray(wav, dtype=np.float32)
    if wav.ndim > 1:
        wav = np.mean(wav, axis=-1)

    start_sample = max(0, min(int(body.start * sr), len(wav) - 1))
    end_sample = max(start_sample + 1, min(int(body.end * sr), len(wav)))
    trimmed = wav[start_sample:end_sample]

    audio_bytes = convert_audio(trimmed, sr, "wav")
    return {
        "ok": True,
        "audio": base64.b64encode(audio_bytes).decode("ascii"),
        "sample_rate": sr,
        "duration": float(len(trimmed) / sr),
    }

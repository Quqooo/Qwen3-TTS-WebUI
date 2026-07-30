"""
语音合成 API 路由

提供语音合成端点，根据请求中的模型类型自动分发到对应的生成方法。
合成的音频格式转换、增益调整、重采样等后处理在此路由中完成。
"""
import os
import asyncio
from typing import Any, Dict, List, Optional

import numpy as np
from fastapi import APIRouter, Depends
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field, StrictInt, model_validator

from ..audio import (
    MEDIA_TYPES,
    apply_gain,
    convert_audio,
    download_audio,
    normalize_audio,
    resample,
    split_text,
)
from ..branches.base import NotSupportedError
from ..cache import get_cache_manager
from ..config import require_qwen, resolve_model_path
from ..errors import APIError, raise_error
from ..routers.ws import broadcast_cache_status, broadcast_tracker_status
from ..tracker import get_tracker
from ..voices import manager as voice_manager

router = APIRouter(prefix="/api", tags=["synthesis"], dependencies=[Depends(require_qwen)])
FIRST_STREAM_CHUNK_TIMEOUT = 600.0
_MAX_GENERATION_LENGTH = 32767


class GenerationParamsModel(BaseModel):
    """生成参数

    对应前端 GenerationParams 类型，所有字段均为可选。
    """
    do_sample: Optional[bool] = None
    top_k: Optional[int] = None
    top_p: Optional[float] = None
    temperature: Optional[float] = None
    repetition_penalty: Optional[float] = None
    subtalker_top_k: Optional[int] = None
    subtalker_top_p: Optional[float] = None
    subtalker_temperature: Optional[float] = None
    max_new_tokens: Optional[StrictInt] = Field(None, ge=1, le=_MAX_GENERATION_LENGTH)


class SynthesisRequest(BaseModel):
    """合成请求体

    覆盖三种模型类型的所有参数。实际生效的参数取决于 kind：
    - base: 使用 ref_audio/ref_text/voice_file/x_vector_only
    - custom_voice: 使用 speaker/instruct
    - voice_design: 使用 voice_description
    """
    model: str                                          # 模型路径或 ID
    text: str                                           # 合成文本
    language: str = "Auto"                              # 语言
    kind: str = "base"                                  # 模型类型: base/custom_voice/voice_design

    # 模型类型相关参数
    speaker: Optional[str] = None                       # kind=custom_voice 时必填
    instruct: Optional[str] = None                      # kind=custom_voice 可选
    voice_description: Optional[str] = None             # kind=voice_design 时必填

    # Base 模型参数（仅 kind=base 可填）
    ref_audio: Optional[str] = None                     # 参考音频 URL 或 data URI
    ref_text: Optional[str] = None                      # 参考文本，与 x_vector_only 互斥
    voice_file: Optional[str] = None                    # 音色文件名称，与 ref_audio/ref_text/x_vector_only 互斥
    x_vector_only: bool = False                         # 是否仅使用 x-vector，与 ref_text/voice_file 互斥

    # 流式参数（仅 streaming=true 可填）
    streaming: bool = False
    emit_every_frames: int = 8
    decode_window_frames: int = 80
    overlap_samples: int = 0
    max_frames: StrictInt = Field(10000, ge=1, le=_MAX_GENERATION_LENGTH)

    # 输出参数
    output_format: str = "wav"                          # wav/flac/mp3/ogg/pcm/opus/aac
    output_sample_rate: int = 24000                     # 输出采样率
    gain: float = 0.0                                   # 增益（分贝）

    # 文本切分参数（仅 streaming=false 且 split_enabled=true 时启用）
    split_enabled: bool = False
    split_characters: Optional[List[str]] = None

    # 生成参数
    generation_params: Optional[GenerationParamsModel] = None

    @model_validator(mode="after")
    def validate_request(self) -> "SynthesisRequest":
        kind = self.kind
        if kind == "custom_voice" and not self.speaker:
            raise ValueError("speaker is required when kind=custom_voice")
        if kind == "voice_design" and not self.voice_description:
            raise ValueError("voice_description is required when kind=voice_design")

        if kind != "base":
            if self.ref_audio or self.ref_text or self.voice_file or self.x_vector_only:
                raise ValueError(f"ref_audio/ref_text/voice_file/x_vector_only are only allowed when kind=base")

        if self.ref_text and self.x_vector_only:
            raise ValueError("ref_text and x_vector_only are mutually exclusive")
        if self.voice_file and (self.ref_audio or self.ref_text or self.x_vector_only):
            raise ValueError("voice_file is mutually exclusive with ref_audio/ref_text/x_vector_only")

        if not self.streaming:
            if "max_frames" in self.model_fields_set:
                raise ValueError("max_frames is only allowed when streaming=true")
            if self.emit_every_frames != 8:
                self.emit_every_frames = 8
            if self.decode_window_frames != 80:
                self.decode_window_frames = 80
            if self.overlap_samples != 0:
                self.overlap_samples = 0
        else:
            if self.output_format != "pcm":
                raise ValueError("streaming only supports pcm format")

        if self.split_enabled and self.streaming:
            raise ValueError("split_enabled cannot be true when streaming=true")

        return self


@router.post("/synthesize")
async def synthesize(body: SynthesisRequest):
    """语音合成端点"""
    return await _do_synthesize(body)


async def _do_synthesize(body: SynthesisRequest):
    cache = get_cache_manager()

    streaming = body.streaming
    fmt = body.output_format.lower()

    text = body.text.strip()
    if not text:
        raise_error(status_code=400, detail="Text is required")

    try:
        model_path = resolve_model_path(body.model)
    except ValueError as e:
        raise_error(status_code=400, detail="Failed to resolve model path", debug=str(e))

    kind = body.kind
    try:
        await cache.load_model(body.model, kind)
    except Exception as e:
        raise_error(status_code=500, detail="Failed to load model", debug=str(e))

    # 解析生成参数
    gen_params = body.generation_params.model_dump(exclude_none=True) if body.generation_params else {}

    gen_kwargs: Dict[str, Any] = dict(
        model_path=model_path,
        language=body.language,
        generation_params=gen_params,
    )

    tbl = cache.branch
    async def touch():
        await cache.touch_model(body.model)
    tracker = get_tracker()
    tracker_owned_by_response = False
    tracker_released = False
    tracker_release_lock = asyncio.Lock()

    async def release_tracker(*, wait_stoppable: bool = False) -> None:
        nonlocal tracker_released
        async with tracker_release_lock:
            if tracker_released:
                return
            if wait_stoppable:
                await tbl.wait_model_stoppable(model_path)
            await tracker.release_inference(body.model)
            tracker_released = True
            asyncio.create_task(broadcast_tracker_status())
            asyncio.create_task(broadcast_cache_status())

    await tracker.acquire_inference(body.model)
    asyncio.create_task(broadcast_tracker_status())
    try:
        if kind == "base":
            result = await _handle_base_synthesis(
                tbl, body, fmt, gen_kwargs, touch_model=touch,
                finish_stream=release_tracker,
            )
        elif kind == "custom_voice":
            result = await _handle_custom_voice_synthesis(
                tbl, body, fmt, gen_kwargs, touch_model=touch,
                finish_stream=release_tracker,
            )
            if not body.streaming:
                await touch()
        elif kind == "voice_design":
            result = await _handle_voice_design_synthesis(
                tbl, body, fmt, gen_kwargs, touch_model=touch,
                finish_stream=release_tracker,
            )
            if not body.streaming:
                await touch()
        else:
            raise_error(status_code=400, detail=f"Unknown model kind: {kind}")
        tracker_owned_by_response = body.streaming
        return result
    except asyncio.CancelledError:
        # The HTTP request may be cancelled while the worker's synchronous model
        # thread is still inside a non-interruptible inference step. Keep the
        # tracker busy until that step reaches the worker model-lock boundary.
        wait_task = asyncio.create_task(tbl.wait_model_stoppable(model_path))
        while not wait_task.done():
            try:
                await asyncio.shield(wait_task)
            except asyncio.CancelledError:
                continue
        try:
            wait_task.result()
        except Exception as e:
            _logger = __import__("logging").getLogger("qwen-webui.synthesis")
            _logger.error("Failed while waiting for inference safe point: %s", e, exc_info=True)
        raise
    except NotSupportedError as e:
        raise_error(status_code=400, detail="Operation not supported", debug=str(e))
    except ValueError as e:
        raise_error(status_code=400, detail=str(e))
    except APIError:
        raise
    except RuntimeError as e:
        _logger = __import__("logging").getLogger("qwen-webui.synthesis")
        _logger.error("Synthesis failed: %s", e, exc_info=True)
        raise_error(status_code=500, detail=str(e), debug=__import__("traceback").format_exc())
    except Exception as e:
        _logger = __import__("logging").getLogger("qwen-webui.synthesis")
        _logger.error("Synthesis failed: %s", e, exc_info=True)
        raise_error(status_code=500, detail="Speech synthesis failed", debug=str(e))
    finally:
        if not tracker_owned_by_response:
            release_task = asyncio.create_task(release_tracker())
            while not release_task.done():
                try:
                    await asyncio.shield(release_task)
                except asyncio.CancelledError:
                    continue
            try:
                release_task.result()
            except Exception as e:
                _logger = __import__("logging").getLogger("qwen-webui.synthesis")
                _logger.error("Failed to release inference tracker: %s", e, exc_info=True)


def _stream_from_generator(
    async_gen, body, fmt, touch_model=None, first_chunk=None, finish_stream=None,
):
    """将异步生成器包装为逐块 PCM 流式 StreamingResponse"""
    import numpy as np

    async def stream_generator():
        model_sr = None
        completed = False
        cancelled = False
        try:
            if first_chunk is not None:
                chunk_wav, chunk_sr = first_chunk
                model_sr = chunk_sr
                chunk = apply_gain(np.asarray(chunk_wav, dtype=np.float32), body.gain)
                if body.output_sample_rate != model_sr:
                    chunk = resample(chunk, model_sr, body.output_sample_rate)
                chunk = np.clip(chunk, -1.0, 1.0)
                yield (chunk * 32767).astype(np.int16).tobytes()
            async for chunk_wav, chunk_sr in async_gen:
                if model_sr is None:
                    model_sr = chunk_sr
                chunk = apply_gain(np.asarray(chunk_wav, dtype=np.float32), body.gain)
                if body.output_sample_rate != model_sr:
                    chunk = resample(chunk, model_sr, body.output_sample_rate)
                chunk = np.clip(chunk, -1.0, 1.0)
                int16 = (chunk * 32767).astype(np.int16)
                yield int16.tobytes()
            completed = True
        except (GeneratorExit, asyncio.CancelledError):
            cancelled = True
        except Exception as e:
            _logger = __import__("logging").getLogger("qwen-webui.synthesis")
            _logger.error("Stream generation error: %s", e, exc_info=True)
        finally:
            try:
                await async_gen.aclose()
            except asyncio.CancelledError:
                cancelled = True
            except Exception as e:
                _logger = __import__("logging").getLogger("qwen-webui.synthesis")
                _logger.warning("Stream cleanup failed: %s", e, exc_info=True)
            if touch_model and completed:
                try:
                    await touch_model()
                except Exception as e:
                    _logger = __import__("logging").getLogger("qwen-webui.synthesis")
                    _logger.warning("Failed to update completed stream usage: %s", e)
            if finish_stream:
                cleanup_task = asyncio.create_task(
                    finish_stream(wait_stoppable=cancelled or not completed)
                )
                while not cleanup_task.done():
                    try:
                        await asyncio.shield(cleanup_task)
                    except asyncio.CancelledError:
                        cancelled = True
                try:
                    cleanup_task.result()
                except Exception as e:
                    _logger = __import__("logging").getLogger("qwen-webui.synthesis")
                    _logger.error("Failed to finalize stream state: %s", e, exc_info=True)
            if cancelled:
                raise asyncio.CancelledError

    return StreamingResponse(
        stream_generator(),
        media_type="audio/L16;rate=%d" % body.output_sample_rate,
    )


async def _handle_base_synthesis(
    branch, body, fmt, gen_kwargs, touch_model=None, finish_stream=None,
):
    """处理 Base 模型合成"""
    target_sr = body.output_sample_rate

    voice_file_path = None
    if body.voice_file:
        voice_file_path = voice_manager.resolve_voice_file(body.voice_file)
        if not voice_file_path:
            raise_error(status_code=400, detail=f"Voice file not found: {body.voice_file}")

    ref_audio = None
    if not voice_file_path and body.ref_audio:
        ref_audio = await _resolve_ref_audio(body.ref_audio)

    if not voice_file_path and ref_audio is None:
        raise_error(status_code=400, detail="Base model requires either voice_file or ref_audio")

    if body.streaming:
        stream_kwargs = {
            "model_path": gen_kwargs["model_path"],
            "text": body.text,
            "language": body.language,
            "emit_every_frames": body.emit_every_frames,
            "decode_window_frames": body.decode_window_frames,
            "overlap_samples": body.overlap_samples,
            "max_frames": body.max_frames,
            "generation_params": gen_kwargs.get("generation_params"),
        }
        if voice_file_path:
            stream_kwargs["voice_file"] = voice_file_path
        else:
            stream_kwargs["ref_audio"] = ref_audio
            stream_kwargs["ref_text"] = body.ref_text
            stream_kwargs["x_vector_only"] = body.x_vector_only
        async_gen = branch.stream_generate_voice_clone(**stream_kwargs)
        try:
            first_chunk = await asyncio.wait_for(
                anext(async_gen),
                timeout=FIRST_STREAM_CHUNK_TIMEOUT,
            )
        except asyncio.TimeoutError:
            await async_gen.aclose()
            raise_error(
                status_code=504,
                detail=f"流式生成超时，未在 {FIRST_STREAM_CHUNK_TIMEOUT:.0f}s 内产生音频",
                debug=f"timeout={FIRST_STREAM_CHUNK_TIMEOUT}s",
            )
        except StopAsyncIteration:
            raise_error(status_code=500, detail="Streaming generation ended without audio")
        return _stream_from_generator(
            async_gen, body, fmt, touch_model=touch_model, first_chunk=first_chunk,
            finish_stream=finish_stream,
        )

    gen_fn_kwargs = {**gen_kwargs}
    if voice_file_path:
        gen_fn_kwargs["voice_file"] = voice_file_path
    else:
        gen_fn_kwargs["ref_audio"] = ref_audio
        gen_fn_kwargs["ref_text"] = body.ref_text
        gen_fn_kwargs["x_vector_only"] = body.x_vector_only

    parts = split_text(body.text, body.split_characters) if body.split_enabled else [body.text]
    all_wavs = []
    model_sr = 24000

    for part in parts:
        wavs, sr = await branch.generate_voice_clone(
            text=part,
            **{k: v for k, v in gen_fn_kwargs.items() if k != "text"},
        )
        model_sr = sr
        all_wavs.append(np.asarray(wavs[0], dtype=np.float32))

    if touch_model:
        await touch_model()

    return _finalize_audio(all_wavs, model_sr, target_sr, body.gain, fmt)


async def _handle_custom_voice_synthesis(
    branch, body, fmt, gen_kwargs, touch_model=None, finish_stream=None,
):
    """处理 CustomVoice 模型合成"""
    target_sr = body.output_sample_rate
    speaker = body.speaker or "serena"

    if body.streaming:
        return _stream_from_generator(
            branch.stream_generate_custom_voice(
                model_path=gen_kwargs["model_path"],
                text=body.text,
                speaker=speaker,
                language=body.language,
                instruct=body.instruct,
                emit_every_frames=body.emit_every_frames,
                decode_window_frames=body.decode_window_frames,
                overlap_samples=body.overlap_samples,
                max_frames=body.max_frames,
                generation_params=gen_kwargs.get("generation_params"),
            ),
            body, fmt, touch_model=touch_model, finish_stream=finish_stream,
        )

    parts = split_text(body.text, body.split_characters) if body.split_enabled else [body.text]
    all_wavs = []
    model_sr = 24000

    for part in parts:
        wavs, sr = await branch.generate_custom_voice(
            text=part,
            speaker=speaker,
            instruct=body.instruct,
            **gen_kwargs,
        )
        model_sr = sr
        all_wavs.append(np.asarray(wavs[0], dtype=np.float32))

    return _finalize_audio(all_wavs, model_sr, target_sr, body.gain, fmt)


async def _handle_voice_design_synthesis(
    branch, body, fmt, gen_kwargs, touch_model=None, finish_stream=None,
):
    """处理 VoiceDesign 模型合成"""
    target_sr = body.output_sample_rate
    instruct = body.voice_description or ""

    if not instruct:
        raise_error(status_code=400, detail="VoiceDesign model requires voice_description")

    if body.streaming:
        return _stream_from_generator(
            branch.stream_generate_voice_design(
                model_path=gen_kwargs["model_path"],
                text=body.text,
                instruct=instruct,
                language=body.language,
                emit_every_frames=body.emit_every_frames,
                decode_window_frames=body.decode_window_frames,
                overlap_samples=body.overlap_samples,
                max_frames=body.max_frames,
                generation_params=gen_kwargs.get("generation_params"),
            ),
            body, fmt, touch_model=touch_model, finish_stream=finish_stream,
        )

    parts = split_text(body.text, body.split_characters) if body.split_enabled else [body.text]
    all_wavs = []
    model_sr = 24000

    for part in parts:
        wavs, sr = await branch.generate_voice_design(
            text=part,
            instruct=instruct,
            **gen_kwargs,
        )
        model_sr = sr
        all_wavs.append(np.asarray(wavs[0], dtype=np.float32))

    return _finalize_audio(all_wavs, model_sr, target_sr, body.gain, fmt)


async def _resolve_ref_audio(ref_audio_url: str):
    """解析参考音频输入，返回 (waveform, sample_rate) 元组"""
    if ref_audio_url.startswith(("http://", "https://", "data:")):
        return download_audio(ref_audio_url)
    raise_error(status_code=400, detail="ref_audio must be an HTTP(S) URL or data URI")


def _finalize_audio(all_wavs, model_sr, target_sr, gain_db, fmt):
    """拼接、后处理并返回最终音频"""
    if len(all_wavs) > 1:
        wav = np.concatenate(all_wavs)
    else:
        wav = all_wavs[0]

    wav = apply_gain(wav, gain_db)
    if target_sr != model_sr:
        wav = resample(wav, model_sr, target_sr)
    wav = normalize_audio(wav)
    audio_bytes = convert_audio(wav, target_sr, fmt)

    return Response(content=audio_bytes, media_type=MEDIA_TYPES[fmt])

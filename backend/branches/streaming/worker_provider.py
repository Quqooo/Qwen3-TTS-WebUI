"""Worker provider for dffdeeq/Qwen3-TTS-streaming."""

from typing import Any, Dict, Iterator, List, Optional

from backend.worker import common
from backend.worker.provider import (
    AudioResult,
    ProviderCapabilities,
    ProviderValidationError,
    StreamChunk,
    WorkerProvider,
)


_LOAD_OPTIONS = {"device_map", "dtype", "attn_implementation", "local_files_only"}
_GENERATION_OPTIONS = {
    "do_sample", "top_k", "top_p", "temperature", "repetition_penalty",
    "subtalker_dosample", "subtalker_top_k", "subtalker_top_p",
    "subtalker_temperature", "max_new_tokens", "min_new_tokens", "seed",
}
_STREAM_GENERATION_OPTIONS = {
    "do_sample", "top_k", "top_p", "temperature",
    "subtalker_dosample", "subtalker_top_k",
    "subtalker_top_p", "subtalker_temperature", "seed",
}
_PROVIDER_OPTIONS = {
    "use_compile", "use_cuda_graphs", "compile_mode", "use_fast_codebook",
    "compile_codebook_predictor", "compile_talker",
}


def _filtered(values: Dict[str, Any], allowed: set) -> Dict[str, Any]:
    return {key: value for key, value in (values or {}).items() if key in allowed and value is not None}


def _generation_values(request: Dict[str, Any], allowed: set = _GENERATION_OPTIONS) -> Dict[str, Any]:
    values = dict(request.get("generation_params") or {})
    non_streaming_mode = values.pop("non_streaming_mode", None)
    filtered = _filtered(values, allowed)
    if non_streaming_mode is not None:
        filtered["non_streaming_mode"] = non_streaming_mode
    return filtered


def _audio_result(result: Any) -> AudioResult:
    import numpy as np

    wavs, sample_rate = result
    return [np.asarray(wav, dtype=np.float32) for wav in wavs], int(sample_rate)


def _scoped_generate(model: Any, method: str, kwargs: Dict[str, Any]) -> Any:
    """取出 seed 后包裹模型调用；HF generate 不接受 generator，用作用域全局 seed。"""
    seed = kwargs.pop("seed", None)
    fn = getattr(model, method)
    if seed is None:
        return fn(**kwargs)
    with common.scoped_torch_seed(seed):
        return fn(**kwargs)


def _scoped_yield_from(model: Any, method: str, kwargs: Dict[str, Any]) -> Iterator[Any]:
    """流式生成：seed 的作用域必须覆盖整个迭代过程。"""
    seed = kwargs.pop("seed", None)
    generator = getattr(model, method)(**kwargs)
    if seed is None:
        yield from generator
    else:
        with common.scoped_torch_seed(seed):
            yield from generator


class StreamingQwenProvider(WorkerProvider):
    provider_id = "qwen-dffdeeq-streaming"
    capabilities = ProviderCapabilities(
        stream_generate_voice_clone=True, stream_generate_custom_voice=True, stream_generate_voice_design=True,
        voice_prompt=True, voice_preview=True,
    )

    def load_model(self, model_path: str, model_kind: str,
                   load_options: Dict[str, Any], provider_options: Dict[str, Any]) -> Any:
        import torch
        from qwen_tts import Qwen3TTSModel
        from qwen_tts.core.models.modeling_qwen3_tts import (
            Qwen3TTSTalkerCodePredictorModelForConditionalGeneration,
            Qwen3TTSTalkerForConditionalGeneration,
        )

        def compile_code_predictor(instance, mode="reduce-overhead"):
            forward = instance.model.forward
            if hasattr(forward, "__wrapped__"):
                forward = forward.__wrapped__.__get__(instance.model, type(instance.model))
            instance.model.forward = torch.compile(forward, mode=mode, fullgraph=False)

        def compile_talker(instance, mode="default"):
            forward = instance.model.forward
            if hasattr(forward, "__wrapped__"):
                forward = forward.__wrapped__.__get__(instance.model, type(instance.model))
            instance.model.forward = torch.compile(forward, mode=mode, fullgraph=False)

        Qwen3TTSTalkerCodePredictorModelForConditionalGeneration.enable_compile = compile_code_predictor
        Qwen3TTSTalkerForConditionalGeneration.enable_compile = compile_talker

        kwargs = {
            "device_map": "cuda:0", "dtype": torch.bfloat16,
            "attn_implementation": "flash_attention_2", "local_files_only": True,
        }
        kwargs.update(_filtered(load_options, _LOAD_OPTIONS))
        model = Qwen3TTSModel.from_pretrained(model_path, **kwargs)
        optimization = {
            "use_compile": True, "use_cuda_graphs": False,
            "compile_mode": "reduce-overhead", "use_fast_codebook": True,
            "compile_codebook_predictor": True, "compile_talker": True,
        }
        optimization.update(_filtered(provider_options, _PROVIDER_OPTIONS))
        model.enable_streaming_optimizations(**optimization)
        return model

    def get_supported_options(self, model: Any) -> Dict[str, Any]:
        def label(value: str) -> str:
            return " ".join(word[:1].upper() + word[1:] for word in value.replace("_", " ").split())
        languages = [{"value": "Auto", "label": "Auto"}]
        seen = {"auto"}
        getter = getattr(model.model, "get_supported_languages", None)
        for value in (getter() or []) if getter is not None else []:
            value = str(value).strip()
            if value and value.casefold() not in seen:
                seen.add(value.casefold())
                languages.append({"value": value, "label": label(value)})
        getter = getattr(model.model, "get_supported_speakers", None)
        speakers = [{"value": value, "label": label(str(value))}
                    for value in ((getter() or []) if getter is not None else [])]
        return {"languages": languages, "speakers": speakers}

    def generate_voice_clone(self, model: Any, request: Dict[str, Any]) -> AudioResult:
        kwargs = {"text": request["text"], "language": request.get("language", "Auto"),
                  **_generation_values(request)}
        if request.get("voice_clone_prompt") is not None:
            kwargs["voice_clone_prompt"] = request["voice_clone_prompt"]
        elif request.get("ref_audio") is not None:
            kwargs.update(ref_audio=request["ref_audio"], ref_text=request.get("ref_text"),
                          x_vector_only_mode=request.get("x_vector_only", False))
        else:
            raise ProviderValidationError("Base model requires voice_file or ref_audio")
        return _audio_result(_scoped_generate(model, "generate_voice_clone", kwargs))

    def generate_custom_voice(self, model: Any, request: Dict[str, Any]) -> AudioResult:
        return _audio_result(_scoped_generate(model, "generate_custom_voice", {
            "text": request["text"], "speaker": request["speaker"], "language": request.get("language", "Auto"),
            "instruct": request.get("instruct"),
            **_generation_values(request)}))

    def generate_voice_design(self, model: Any, request: Dict[str, Any]) -> AudioResult:
        return _audio_result(_scoped_generate(model, "generate_voice_design", {
            "text": request["text"], "instruct": request["instruct"], "language": request.get("language", "Auto"),
            **_generation_values(request)}))

    def stream_generate_voice_clone(self, model: Any, request: Dict[str, Any]) -> Iterator[StreamChunk]:
        kwargs = {"text": request["text"], "language": request.get("language", "Auto"),
                  **self._stream_options(request),
                   **_generation_values(request, _STREAM_GENERATION_OPTIONS)}
        if request.get("voice_clone_prompt") is not None:
            items = request["voice_clone_prompt"]
            kwargs["voice_clone_prompt"] = items[0] if len(items) == 1 else items
        elif request.get("ref_audio") is not None:
            kwargs.update(ref_audio=request["ref_audio"], ref_text=request.get("ref_text"),
                          x_vector_only_mode=request.get("x_vector_only", False))
        else:
            raise ProviderValidationError("Base model requires voice_file or ref_audio")
        yield from _scoped_yield_from(model, "stream_generate_voice_clone", kwargs)

    def stream_generate_custom_voice(self, model: Any, request: Dict[str, Any]) -> Iterator[StreamChunk]:
        input_ids = model._tokenize_texts([model._build_assistant_text(request["text"])])
        instruct = request.get("instruct") or ""
        instruct_ids = model._tokenize_texts([model._build_instruct_text(instruct)]) if instruct else None
        yield from _scoped_yield_from(model.model, "stream_generate_pcm", {
            "input_ids": input_ids, "instruct_ids": instruct_ids,
            "languages": [request.get("language", "Auto")], "speakers": [request["speaker"]],
            **self._stream_options(request),
            **_filtered(request.get("generation_params", {}), _STREAM_GENERATION_OPTIONS)})

    def stream_generate_voice_design(self, model: Any, request: Dict[str, Any]) -> Iterator[StreamChunk]:
        input_ids = model._tokenize_texts([model._build_assistant_text(request["text"])])
        instruct_ids = model._tokenize_texts([model._build_instruct_text(request["instruct"])])
        yield from _scoped_yield_from(model.model, "stream_generate_pcm", {
            "input_ids": input_ids, "instruct_ids": instruct_ids,
            "languages": [request.get("language", "Auto")],
            **self._stream_options(request),
            **_filtered(request.get("generation_params", {}), _STREAM_GENERATION_OPTIONS)})

    @staticmethod
    def _stream_options(request: Dict[str, Any]) -> Dict[str, Any]:
        values = request.get("dffdeeq") or {}
        return {
            key: values[key]
            for key in (
                "emit_every_frames",
                "decode_window_frames",
                "overlap_samples",
                "max_frames",
            )
            if key in values and values[key] is not None
        }

    def create_voice_clone_prompt(self, model: Any, request: Dict[str, Any]) -> List[Dict[str, Any]]:
        items = model.create_voice_clone_prompt(
            ref_audio=request["ref_audio"], ref_text=request.get("ref_text"),
            x_vector_only_mode=request.get("x_vector_only", False))
        return [{"ref_code": common.serialize_tensor(item.ref_code) if item.ref_code is not None else None,
                 "ref_spk_embedding": common.serialize_tensor(item.ref_spk_embedding),
                 "x_vector_only_mode": item.x_vector_only_mode, "icl_mode": item.icl_mode,
                 "ref_text": item.ref_text} for item in items]

    def deserialize_voice_items(self, items: List[Dict[str, Any]]) -> Any:
        import torch
        from qwen_tts import VoiceClonePromptItem
        result = []
        for item in items:
            ref_code = item.get("ref_code")
            ref_spk = item.get("ref_spk_embedding")
            if ref_code is not None and not isinstance(ref_code, torch.Tensor):
                ref_code = torch.as_tensor(ref_code)
            if not isinstance(ref_spk, torch.Tensor):
                ref_spk = torch.as_tensor(ref_spk)
            xvec = bool(item.get("x_vector_only_mode", False))
            result.append(VoiceClonePromptItem(ref_code=ref_code, ref_spk_embedding=ref_spk,
                          x_vector_only_mode=xvec, icl_mode=bool(item.get("icl_mode", not xvec)),
                          ref_text=item.get("ref_text")))
        return result

    def decode_voice_preview(self, model: Any, item: Dict[str, Any]) -> Optional[AudioResult]:
        import numpy as np
        import torch
        code = item.get("ref_code")
        if code is None:
            return None
        code = code if isinstance(code, torch.Tensor) else torch.as_tensor(code)
        if code.is_floating_point():
            raise ProviderValidationError(f"ref_code has invalid dtype {code.dtype}, expected integer")
        if code.dim() == 1:
            code = code.unsqueeze(-1)
        wavs, sample_rate = model.model.speech_tokenizer.decode({"audio_codes": code.to(model.device)})
        return [np.asarray(wavs[0], dtype=np.float32)], int(sample_rate)


def create_provider() -> WorkerProvider:
    return StreamingQwenProvider()

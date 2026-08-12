"""Worker provider for andimarafioti/faster-qwen3-tts."""

from typing import Any, Dict, List

from backend.worker import common
from backend.worker.provider import ProviderCapabilities, ProviderValidationError, WorkerProvider


_LOAD_OPTIONS = {"device", "dtype", "local_files_only"}
_GENERATION_OPTIONS = {
    "max_new_tokens", "min_new_tokens", "temperature", "top_k", "top_p",
    "do_sample", "repetition_penalty", "non_streaming_mode", "seed",
}
_PREDICTOR_GRAPH_DEFAULTS = {
    "do_sample": True,
    "top_k": 50,
    "top_p": 1.0,
    "temperature": 0.9,
}


def _filtered(values: Dict[str, Any], allowed: set) -> Dict[str, Any]:
    return {key: value for key, value in (values or {}).items() if key in allowed and value is not None}


def _audio_result(result: Any):
    import numpy as np
    wavs, sample_rate = result
    return [np.asarray(wav, dtype=np.float32) for wav in wavs], int(sample_rate)


def _scoped_generate(model: Any, method: str, kwargs: Dict[str, Any]) -> Any:
    """取出 seed 后包裹模型调用；图内/图外采样均消费全局 RNG，作用域固定即可整体复现。"""
    seed = kwargs.pop("seed", None)
    fn = getattr(model, method)
    if seed is None:
        return fn(**kwargs)
    with common.scoped_torch_seed(seed):
        return fn(**kwargs)


def _scoped_yield_from(model: Any, method: str, kwargs: Dict[str, Any]):
    """流式生成：seed 的作用域必须覆盖整个迭代过程（含 CUDA Graph 图内采样）。"""
    seed = kwargs.pop("seed", None)
    generator = getattr(model, method)(**kwargs)
    if seed is None:
        yield from generator
    else:
        with common.scoped_torch_seed(seed):
            yield from generator


def _predictor_graph_options(values: Dict[str, Any] | None) -> Dict[str, Any]:
    return {**_PREDICTOR_GRAPH_DEFAULTS, **(values or {})}


class FasterQwenProvider(WorkerProvider):
    provider_id = "qwen-andimarafioti-faster"
    capabilities = ProviderCapabilities(
        stream_generate_voice_clone=True, stream_generate_custom_voice=True, stream_generate_voice_design=True,
        voice_prompt=True, voice_preview=True,
    )

    def load_model(self, model_path: str, model_kind: str,
                   load_options: Dict[str, Any], provider_options: Dict[str, Any]) -> Any:
        import torch
        from faster_qwen3_tts import FasterQwen3TTS
        kwargs = {
            "device": "cuda", "dtype": torch.bfloat16,
            "attn_implementation": "sdpa", "max_seq_len": 2048,
            "backend": "torch", "local_files_only": True,
        }
        kwargs.update(_filtered(provider_options, {"max_seq_len"}))
        kwargs.update(_filtered(load_options, _LOAD_OPTIONS))
        model = FasterQwen3TTS.from_pretrained(model_path, **kwargs)
        predictor_options = _predictor_graph_options(provider_options.get("predictor_graph"))
        self._configure_predictor_graph(model, predictor_options)
        model.warmup(prefill_len=int(provider_options.get("warmup_prefill_len", 100)))
        model._webui_predictor_graph_options = predictor_options
        return model

    @staticmethod
    def _configure_predictor_graph(model: Any, options: Dict[str, Any]) -> None:
        graph = model.predictor_graph
        for key, value in options.items():
            setattr(graph, key, value)

    def model_requires_prepare(self, model: Any, request: Dict[str, Any]) -> bool:
        runtime = request.get("provider_runtime") or {}
        if "predictor_graph" not in runtime:
            return False
        requested = _predictor_graph_options(runtime["predictor_graph"])
        return requested != getattr(model, "_webui_predictor_graph_options", None)

    def prepare_model(self, model: Any, request: Dict[str, Any]) -> None:
        requested = _predictor_graph_options(
            (request.get("provider_runtime") or {}).get("predictor_graph")
        )
        self._configure_predictor_graph(model, requested)
        model.predictor_graph.capture(num_warmup=3)
        model._webui_predictor_graph_options = requested

    def get_supported_options(self, model: Any) -> Dict[str, Any]:
        def label(value: str) -> str:
            return " ".join(word[:1].upper() + word[1:] for word in value.replace("_", " ").split())
        qwen = model.model
        languages = [{"value": "Auto", "label": "Auto"}]
        seen = {"auto"}
        getter = getattr(qwen.model, "get_supported_languages", None)
        for value in (getter() or []) if callable(getter) else []:
            value = str(value).strip()
            if value and value.casefold() not in seen:
                seen.add(value.casefold())
                languages.append({"value": value, "label": label(value)})
        getter = getattr(qwen.model, "get_supported_speakers", None)
        speakers = [{"value": value, "label": label(str(value))}
                    for value in ((getter() or []) if callable(getter) else [])]
        return {"languages": languages, "speakers": speakers}

    def _clone_kwargs(self, model: Any, request: Dict[str, Any]) -> Dict[str, Any]:
        kwargs = {"text": request["text"], "language": request.get("language", "Auto"),
                  **_filtered(request.get("generation_params", {}), _GENERATION_OPTIONS)}
        instruct = request.get("instruct")
        if instruct:
            kwargs["instruct"] = instruct
        if request.get("voice_clone_prompt") is not None:
            kwargs["voice_clone_prompt"] = request["voice_clone_prompt"]
        elif request.get("ref_audio") is not None:
            ref_text = request.get("ref_text")
            xvec = request.get("x_vector_only", False)
            kwargs["voice_clone_prompt"] = model.model.create_voice_clone_prompt(
                ref_audio=request["ref_audio"], ref_text=ref_text or "", x_vector_only_mode=xvec)
            if not xvec and ref_text:
                kwargs["ref_text"] = ref_text
        else:
            raise ProviderValidationError("Base model requires voice_file or ref_audio")
        return kwargs

    def generate_voice_clone(self, model: Any, request: Dict[str, Any]):
        return _audio_result(_scoped_generate(model, "generate_voice_clone", self._clone_kwargs(model, request)))

    def generate_custom_voice(self, model: Any, request: Dict[str, Any]):
        return _audio_result(_scoped_generate(model, "generate_custom_voice", {
            "text": request["text"], "speaker": request["speaker"], "language": request.get("language", "Auto"),
            "instruct": request.get("instruct"),
            **_filtered(request.get("generation_params", {}), _GENERATION_OPTIONS)}))

    def generate_voice_design(self, model: Any, request: Dict[str, Any]):
        return _audio_result(_scoped_generate(model, "generate_voice_design", {
            "text": request["text"], "instruct": request["instruct"], "language": request.get("language", "Auto"),
            **_filtered(request.get("generation_params", {}), _GENERATION_OPTIONS)}))

    def stream_generate_voice_clone(self, model: Any, request: Dict[str, Any]):
        kwargs = self._clone_kwargs(model, request)
        kwargs.update(self._stream_options(request))
        parity_mode = (request.get("andimarafioti") or {}).get("parity_mode")
        if parity_mode is not None:
            kwargs["parity_mode"] = parity_mode
        yield from self._normalize_stream(_scoped_yield_from(model, "generate_voice_clone_streaming", kwargs))

    def stream_generate_custom_voice(self, model: Any, request: Dict[str, Any]):
        yield from self._normalize_stream(_scoped_yield_from(model, "generate_custom_voice_streaming", {
            "text": request["text"], "speaker": request["speaker"], "language": request.get("language", "Auto"),
            "instruct": request.get("instruct"), **self._stream_options(request),
            **_filtered(request.get("generation_params", {}), _GENERATION_OPTIONS)}))

    def stream_generate_voice_design(self, model: Any, request: Dict[str, Any]):
        yield from self._normalize_stream(_scoped_yield_from(model, "generate_voice_design_streaming", {
            "text": request["text"], "instruct": request["instruct"], "language": request.get("language", "Auto"),
            **self._stream_options(request),
            **_filtered(request.get("generation_params", {}), _GENERATION_OPTIONS)}))

    @staticmethod
    def _stream_options(request: Dict[str, Any]) -> Dict[str, Any]:
        values = request.get("andimarafioti") or {}
        return {"chunk_size": values["chunk_size"]} if "chunk_size" in values else {}

    @staticmethod
    def _normalize_stream(iterator: Any):
        import numpy as np
        for item in iterator:
            if not isinstance(item, tuple) or len(item) not in (2, 3):
                raise ProviderValidationError("Faster streaming result must be a 2- or 3-tuple")
            yield np.asarray(item[0], dtype=np.float32), int(item[1])

    def create_voice_clone_prompt(self, model: Any, request: Dict[str, Any]) -> List[Dict[str, Any]]:
        items = model.model.create_voice_clone_prompt(
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
            code = item.get("ref_code")
            embedding = item.get("ref_spk_embedding")
            if code is not None and not isinstance(code, torch.Tensor):
                code = torch.as_tensor(code)
            if not isinstance(embedding, torch.Tensor):
                embedding = torch.as_tensor(embedding)
            xvec = bool(item.get("x_vector_only_mode", False))
            result.append(VoiceClonePromptItem(
                ref_code=code, ref_spk_embedding=embedding, x_vector_only_mode=xvec,
                icl_mode=bool(item.get("icl_mode", not xvec)), ref_text=item.get("ref_text")))
        return result

    def decode_voice_preview(self, model: Any, item: Dict[str, Any]):
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
        qwen = model.model
        wavs, sample_rate = qwen.model.speech_tokenizer.decode(
            {"audio_codes": code.to(qwen.device)}
        )
        return [np.asarray(wavs[0], dtype=np.float32)], int(sample_rate)


def create_provider() -> WorkerProvider:
    return FasterQwenProvider()

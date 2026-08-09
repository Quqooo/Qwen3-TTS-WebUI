"""Worker provider for the official Qwen3-TTS implementation."""

from typing import Any, Dict, List

from backend.worker import common
from backend.worker.provider import ProviderCapabilities, ProviderValidationError, WorkerProvider


_LOAD_OPTIONS = {"device_map", "dtype", "attn_implementation", "local_files_only"}
_GENERATION_OPTIONS = {
    "do_sample", "top_k", "top_p", "temperature", "repetition_penalty",
    "subtalker_dosample", "subtalker_top_k", "subtalker_top_p",
    "subtalker_temperature", "max_new_tokens", "min_new_tokens",
    "non_streaming_mode", "seed",
}


def _filtered(values: Dict[str, Any], allowed: set) -> Dict[str, Any]:
    return {key: value for key, value in (values or {}).items() if key in allowed and value is not None}


def _scoped_generate(model: Any, method: str, kwargs: Dict[str, Any]) -> Any:
    """取出 seed 后包裹模型调用；HF generate 不接受 generator，用作用域全局 seed。"""
    seed = kwargs.pop("seed", None)
    fn = getattr(model, method)
    if seed is None:
        return fn(**kwargs)
    with common.scoped_torch_seed(seed):
        return fn(**kwargs)


def _audio_result(result: Any):
    import numpy as np

    wavs, sample_rate = result
    return [np.asarray(wav, dtype=np.float32) for wav in wavs], int(sample_rate)


def _format_options(tts: Any) -> Dict[str, Any]:
    def label(value: str) -> str:
        return " ".join(word[:1].upper() + word[1:] for word in value.replace("_", " ").split())

    languages = [{"value": "Auto", "label": "Auto"}]
    seen = {"auto"}
    getter = getattr(tts.model, "get_supported_languages", None)
    for value in (getter() or []) if callable(getter) else []:
        value = str(value).strip()
        if value and value.casefold() not in seen:
            seen.add(value.casefold())
            languages.append({"value": value, "label": label(value)})
    speakers = []
    getter = getattr(tts.model, "get_supported_speakers", None)
    for value in (getter() or []) if callable(getter) else []:
        speakers.append({"value": value, "label": label(str(value))})
    return {"languages": languages, "speakers": speakers}


class OfficialQwenProvider(WorkerProvider):
    provider_id = "qwen-official"
    capabilities = ProviderCapabilities(
        stream_voice_clone=False,
        stream_custom_voice=False,
        stream_voice_design=False,
        voice_prompt=True,
        voice_preview=True,
    )

    def load_model(self, model_path: str, model_kind: str,
                   load_options: Dict[str, Any], provider_options: Dict[str, Any]) -> Any:
        import torch
        from qwen_tts import Qwen3TTSModel

        defaults = {
            "device_map": "cuda:0",
            "dtype": torch.bfloat16,
            "attn_implementation": "flash_attention_2",
            "local_files_only": True,
        }
        defaults.update(_filtered(load_options, _LOAD_OPTIONS))
        return Qwen3TTSModel.from_pretrained(model_path, **defaults)

    def get_supported_options(self, model: Any) -> Dict[str, Any]:
        return _format_options(model)

    def generate_voice_clone(self, model: Any, request: Dict[str, Any]):
        kwargs = {
            "text": request["text"],
            "language": request.get("language", "Auto"),
            **_filtered(request.get("generation_params", {}), _GENERATION_OPTIONS),
        }
        if request.get("voice_clone_prompt") is not None:
            kwargs["voice_clone_prompt"] = request["voice_clone_prompt"]
        elif request.get("ref_audio") is not None:
            kwargs.update(
                ref_audio=request["ref_audio"],
                ref_text=request.get("ref_text"),
                x_vector_only_mode=request.get("x_vector_only", False),
            )
        else:
            raise ProviderValidationError("Base model requires voice_file or ref_audio")
        return _audio_result(_scoped_generate(model, "generate_voice_clone", kwargs))

    def generate_custom_voice(self, model: Any, request: Dict[str, Any]):
        return _audio_result(_scoped_generate(model, "generate_custom_voice", {
            "text": request["text"], "speaker": request["speaker"],
            "language": request.get("language", "Auto"), "instruct": request.get("instruct"),
            **_filtered(request.get("generation_params", {}), _GENERATION_OPTIONS),
        }))

    def generate_voice_design(self, model: Any, request: Dict[str, Any]):
        return _audio_result(_scoped_generate(model, "generate_voice_design", {
            "text": request["text"], "instruct": request["instruct"],
            "language": request.get("language", "Auto"),
            **_filtered(request.get("generation_params", {}), _GENERATION_OPTIONS),
        }))

    def create_voice_clone_prompt(self, model: Any, request: Dict[str, Any]) -> List[Dict[str, Any]]:
        items = model.create_voice_clone_prompt(
            ref_audio=request["ref_audio"], ref_text=request.get("ref_text"),
            x_vector_only_mode=request.get("x_vector_only", False),
        )
        return [self._serialize_item(item) for item in items]

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
            x_vector_only = bool(item.get("x_vector_only_mode", False))
            result.append(VoiceClonePromptItem(
                ref_code=ref_code, ref_spk_embedding=ref_spk,
                x_vector_only_mode=x_vector_only,
                icl_mode=bool(item.get("icl_mode", not x_vector_only)),
                ref_text=item.get("ref_text"),
            ))
        return result

    def decode_voice_preview(self, model: Any, item: Dict[str, Any]):
        import numpy as np
        import torch

        ref_code = item.get("ref_code")
        if ref_code is None:
            return None
        if not isinstance(ref_code, torch.Tensor):
            ref_code = torch.as_tensor(ref_code)
        if ref_code.is_floating_point():
            raise ProviderValidationError(f"ref_code has invalid dtype {ref_code.dtype}, expected integer")
        if ref_code.dim() == 1:
            ref_code = ref_code.unsqueeze(-1)
        wavs, sample_rate = model.model.speech_tokenizer.decode(
            {"audio_codes": ref_code.to(model.device)}
        )
        return [np.asarray(wavs[0], dtype=np.float32)], int(sample_rate)

    @staticmethod
    def _serialize_item(item: Any) -> Dict[str, Any]:
        return {
            "ref_code": common.serialize_tensor(item.ref_code) if item.ref_code is not None else None,
            "ref_spk_embedding": common.serialize_tensor(item.ref_spk_embedding),
            "x_vector_only_mode": item.x_vector_only_mode,
            "icl_mode": item.icl_mode,
            "ref_text": item.ref_text,
        }


def create_provider() -> WorkerProvider:
    return OfficialQwenProvider()

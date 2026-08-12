"""Provider contract and dynamic loader for the unified worker."""
from __future__ import annotations

import hashlib
import importlib.util
import logging
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

_logger = logging.getLogger("qwen-worker")

AudioArray = Any
AudioInput = Tuple[AudioArray, int]
AudioResult = Tuple[List[AudioArray], int]
StreamChunk = Tuple[AudioArray, int]


@dataclass(frozen=True)
class ProviderCapabilities:
    stream_generate_voice_clone: bool = False
    stream_generate_custom_voice: bool = False
    stream_generate_voice_design: bool = False
    voice_prompt: bool = True
    voice_preview: bool = True


class ProviderError(RuntimeError):
    """Base class for provider-facing worker errors."""


class ProviderLoadError(ProviderError):
    pass


class ProviderNotSupportedError(ProviderError):
    pass


class ProviderValidationError(ProviderError):
    pass


class WorkerProvider(ABC):
    """Model-package adapter loaded inside the worker process."""

    provider_id = ""
    capabilities = ProviderCapabilities()

    @abstractmethod
    def load_model(
        self,
        model_path: str,
        model_kind: str,
        load_options: Optional[Dict[str, Any]],
        provider_options: Optional[Dict[str, Any]],
    ) -> Any:
        raise NotImplementedError

    def release_model(self, model: Any) -> None:
        del model

    def model_requires_prepare(self, model: Any, request: Dict[str, Any]) -> bool:
        """Return whether this request requires an exclusive model preparation step."""
        return False

    def prepare_model(self, model: Any, request: Dict[str, Any]) -> None:
        """Prepare a model before inference while the worker holds its GPU write lock."""

    @abstractmethod
    def get_supported_options(self, model: Any) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def generate_voice_clone(self, model: Any, request: Dict[str, Any]) -> AudioResult:
        raise NotImplementedError

    def generate_custom_voice(self, model: Any, request: Dict[str, Any]) -> AudioResult:
        raise ProviderNotSupportedError(f"{self.provider_id} does not support custom voice")

    def generate_voice_design(self, model: Any, request: Dict[str, Any]) -> AudioResult:
        raise ProviderNotSupportedError(f"{self.provider_id} does not support voice design")

    def stream_generate_voice_clone(self, model: Any, request: Dict[str, Any]) -> Iterator[StreamChunk]:
        raise ProviderNotSupportedError(f"{self.provider_id} does not support streaming voice clone")

    def stream_generate_custom_voice(self, model: Any, request: Dict[str, Any]) -> Iterator[StreamChunk]:
        raise ProviderNotSupportedError(f"{self.provider_id} does not support streaming custom voice")

    def stream_generate_voice_design(self, model: Any, request: Dict[str, Any]) -> Iterator[StreamChunk]:
        raise ProviderNotSupportedError(f"{self.provider_id} does not support streaming voice design")

    def create_voice_clone_prompt(self, model: Any, request: Dict[str, Any]) -> List[Dict[str, Any]]:
        raise ProviderNotSupportedError(f"{self.provider_id} does not support voice prompt creation")

    def deserialize_voice_items(self, items: List[Dict[str, Any]]) -> Any:
        return items

    def decode_voice_preview(self, model: Any, item: Dict[str, Any]) -> Optional[AudioResult]:
        raise ProviderNotSupportedError(f"{self.provider_id} does not support voice preview")


def load_provider(provider_file: str) -> WorkerProvider:
    """Load a provider by file path without relying on package naming."""
    provider_path = Path(provider_file).resolve()
    if not provider_path.is_file():
        raise ProviderLoadError(f"Provider file not found: {provider_path}")

    digest = hashlib.sha256(str(provider_path).encode("utf-8")).hexdigest()[:16]
    module_name = f"qwen_worker_provider_{digest}"
    spec = importlib.util.spec_from_file_location(module_name, str(provider_path))
    if spec is None or spec.loader is None:
        raise ProviderLoadError(f"Could not create module spec for: {provider_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop(module_name, None)
        raise ProviderLoadError(f"Failed to execute provider module: {exc}") from exc

    create_provider = getattr(module, "create_provider", None)
    if not callable(create_provider):
        raise ProviderLoadError(
            f"Provider module {provider_path} must expose a create_provider() callable"
        )
    try:
        provider = create_provider()
    except Exception as exc:
        raise ProviderLoadError(f"Provider factory failed: {exc}") from exc
    validate_provider(provider)
    _logger.info("Provider loaded: id=%s file=%s", provider.provider_id, provider_path)
    return provider


def validate_provider(provider: Any) -> None:
    if not isinstance(provider, WorkerProvider):
        raise ProviderValidationError(
            f"Provider must be a WorkerProvider instance, got {type(provider).__name__}"
        )
    if not isinstance(provider.provider_id, str) or not provider.provider_id.strip():
        raise ProviderValidationError("Provider must set a non-empty provider_id")
    if not isinstance(provider.capabilities, ProviderCapabilities):
        raise ProviderValidationError(
            "Provider.capabilities must be a ProviderCapabilities instance"
        )

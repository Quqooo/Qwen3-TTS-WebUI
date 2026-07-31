import json
import os
from typing import Any, Dict, List, Optional

DEFAULT_LANGUAGES: List[Dict[str, str]] = [
    {"value": "Auto", "label": "Auto"},
    {"value": "Chinese", "label": "Chinese"},
    {"value": "English", "label": "English"},
    {"value": "Japanese", "label": "Japanese"},
    {"value": "Korean", "label": "Korean"},
    {"value": "French", "label": "French"},
    {"value": "German", "label": "German"},
    {"value": "Russian", "label": "Russian"},
    {"value": "Spanish", "label": "Spanish"},
    {"value": "Italian", "label": "Italian"},
    {"value": "Portuguese", "label": "Portuguese"},
]

DEFAULT_SPEAKERS: List[Dict[str, str]] = [
    {"value": "serena", "label": "Serena"},
    {"value": "vivian", "label": "Vivian"},
    {"value": "uncle_fu", "label": "Uncle Fu"},
    {"value": "ryan", "label": "Ryan"},
    {"value": "aiden", "label": "Aiden"},
    {"value": "ono_anna", "label": "Ono Anna"},
    {"value": "sohee", "label": "Sohee"},
    {"value": "eric", "label": "Eric"},
    {"value": "dylan", "label": "Dylan"},
]

_meta_cache: Dict[str, Dict[str, List[Dict[str, str]]]] = {}

_KNOWN_KINDS = {"base", "custom_voice", "voice_design"}

# model_id -> kind（None 表示无法从 config.json 确定）
_kind_cache: Dict[str, Optional[str]] = {}


def detect_kind_from_config(model_id: str) -> Optional[str]:
    """从模型目录 config.json 的 tts_model_type 键读取模型类型。

    优先于目录名猜测。返回 None 表示无法确定（config.json 缺失、
    损坏、缺少该键或值不属于已知类型）。
    """
    cached = _kind_cache.get(model_id)
    if cached is not None:
        return cached
    kind: Optional[str] = None
    try:
        from .config import resolve_model_path
        config_path = os.path.join(resolve_model_path(model_id), "config.json")
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        value = data.get("tts_model_type")
        if isinstance(value, str):
            norm = value.strip().lower()
            if norm in _KNOWN_KINDS:
                kind = norm
    except (OSError, ValueError):
        kind = None
    _kind_cache[model_id] = kind
    return kind


def get_model_meta(model_id: str) -> Dict[str, List[Dict[str, str]]]:
    cached = _meta_cache.get(model_id)
    if cached is not None:
        return cached
    return {
        "languages": DEFAULT_LANGUAGES,
        "speakers": DEFAULT_SPEAKERS,
    }


def cache_model_meta(model_id: str, meta: Dict[str, Any]) -> None:
    languages: List[Dict[str, str]] = meta.get("languages") or DEFAULT_LANGUAGES
    speakers: List[Dict[str, str]] = meta.get("speakers") or DEFAULT_SPEAKERS
    _meta_cache[model_id] = {
        "languages": languages,
        "speakers": speakers,
    }


def invalidate_model_meta(model_id: str) -> None:
    _meta_cache.pop(model_id, None)
    _kind_cache.pop(model_id, None)

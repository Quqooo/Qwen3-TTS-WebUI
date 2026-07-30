from typing import Any, Dict, List

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

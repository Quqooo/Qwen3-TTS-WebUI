"""
模型管理 API 路由

提供模型列表查询、缓存状态查询、加载和卸载操作。
所有涉及模型生命周期的操作通过统一缓存管理器进行。
所有端点依赖 require_qwen 校验。
"""
import asyncio
import os
from typing import Dict, List

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..cache import get_cache_manager
from ..config import require_qwen, settings
from ..errors import APIError, raise_error
from ..model_meta import detect_kind_from_config, get_model_meta
from .ws import broadcast_cache_status

router = APIRouter(prefix="/api", tags=["models"], dependencies=[Depends(require_qwen)])


def _get_model_ids() -> List[str]:
    """扫描模型目录，返回所有模型 ID（目录名）"""
    model_dir = settings.model_dir
    if not model_dir and settings.project_dir:
        model_dir = os.path.join(settings.project_dir, "models")
    if not model_dir or not os.path.isdir(model_dir):
        return []

    result = []
    for name in sorted(os.listdir(model_dir)):
        path = os.path.join(model_dir, name)
        if os.path.isdir(path) and "Qwen3-TTS" in name:
            result.append(name)
    return result


def _detect_model_kind(name: str) -> str:
    """判断模型类型：优先读取 config.json 的 tts_model_type 键，无法确定时按目录名猜测"""
    kind = detect_kind_from_config(name)
    if kind:
        return kind

    lower = name.lower().replace("-", "").replace("_", "")

    non_model_keywords = ["tokenizer", "vocab", "safetensors"]
    for kw in non_model_keywords:
        if kw in lower:
            return "unknown"

    if "customvoice" in lower:
        return "custom_voice"
    if "voicedesign" in lower:
        return "voice_design"
    return "base"


@router.get("/models")
async def list_models():
    """列出所有可用模型"""
    model_ids = _get_model_ids()
    models = []
    for name in model_ids:
        kind = _detect_model_kind(name)
        if kind == "unknown":
            continue
        models.append({
            "id": name,
            "kind": kind,
        })
    return {"models": models}


@router.get("/models/cache")
async def cache_status():
    """获取模型缓存状态（含已加载模型的元数据）"""
    try:
        cache = get_cache_manager()
        info = await cache.cached_models()
        loaded = [
            {**item, "meta": get_model_meta(item["id"])}
            for item in info["loaded"]
        ]
        return {
            "loaded": loaded,
            "max_concurrent": settings.max_concurrent_models,
            "usage_order": info["usage_order"],
        }
    except RuntimeError:
        return {"loaded": [], "max_concurrent": settings.max_concurrent_models, "usage_order": []}


class ModelIdRequest(BaseModel):
    model: str
    model_kind: str = "base"


@router.post("/models/load")
async def load_model(body: ModelIdRequest):
    """加载指定模型到缓存"""
    try:
        cache = get_cache_manager()
        await cache.load_model(body.model, body.model_kind)
        asyncio.create_task(broadcast_cache_status())
        return {"status": "loaded", "model": body.model}
    except APIError:
        raise
    except RuntimeError as e:
        raise_error(status_code=500, detail=str(e), debug=__import__("traceback").format_exc())
    except Exception as e:
        raise_error(status_code=500, detail="Failed to load model", debug=str(e))


class UnloadModelRequest(BaseModel):
    model: str


@router.post("/models/unload")
async def unload_model(body: UnloadModelRequest):
    """从缓存中卸载指定模型"""
    try:
        cache = get_cache_manager()
        await cache.unload_model(body.model)
        asyncio.create_task(broadcast_cache_status())
        return {"status": "unloaded", "model": body.model}
    except APIError:
        raise
    except RuntimeError as e:
        raise_error(status_code=500, detail=str(e), debug=__import__("traceback").format_exc())
    except Exception as e:
        raise_error(status_code=500, detail="Failed to unload model", debug=str(e))


@router.post("/models/unload_idle")
async def unload_idle_models():
    """卸载所有空闲超时的模型"""
    try:
        cache = get_cache_manager()
        unloaded = await cache.unload_idle(float(settings.idle_unload_seconds))
        if unloaded:
            asyncio.create_task(broadcast_cache_status())
        return {"unloaded": unloaded}
    except RuntimeError:
        return {"unloaded": []}


@router.get("/models/meta/{model_id}")
async def model_meta(model_id: str):
    """获取模型支持的语言和说话人参数。

    模型加载后自动缓存；未缓存时返回默认值。
    """
    return get_model_meta(model_id)

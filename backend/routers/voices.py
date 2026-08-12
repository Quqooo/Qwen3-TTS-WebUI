"""
音色文件管理 API 路由

提供音色文件的列表、上传、删除接口。
音色文件操作由 voices/manager.py 处理，与具体后端分支无关。
各分支只需兼容 voices/manager.py 导出的 VoiceClonePromptItem 格式。
"""
import json
import os
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

from ..branches.base import NotSupportedError
from ..cache import get_cache_manager
from ..config import require_qwen, resolve_model_path, settings
from ..errors import APIError, raise_error
from ..voices import manager as voice_manager

router = APIRouter(prefix="/api", tags=["voices"], dependencies=[Depends(require_qwen)])


def _get_base_models_by_spk_dim(spk_dim: int) -> List[str]:
    """返回说话人嵌入维度匹配的所有 Base 模型 ID。"""
    model_dir = settings.model_dir
    if not model_dir and settings.project_dir:
        model_dir = os.path.join(settings.project_dir, "models")
    if not model_dir or not os.path.isdir(model_dir) or spk_dim <= 0:
        return []

    matches: List[str] = []
    for name in sorted(os.listdir(model_dir)):
        try:
            path = resolve_model_path(name)
        except ValueError:
            continue
        cfg_path = os.path.join(path, "config.json")
        if not os.path.isfile(cfg_path):
            continue
        try:
            with open(cfg_path, encoding="utf-8") as f:
                config = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        if str(config.get("tts_model_type", "")).strip().lower() != "base":
            continue
        speaker_config = config.get("speaker_encoder_config")
        if not isinstance(speaker_config, dict):
            continue
        try:
            model_spk_dim = int(speaker_config.get("enc_dim", 0))
        except (TypeError, ValueError):
            continue
        if model_spk_dim == spk_dim:
            matches.append(name)
    return matches


@router.get("/voices")
async def list_voices():
    """列出所有已保存的音色文件（仅名称）"""
    files = voice_manager.list_voice_files()
    return {"voices": [os.path.splitext(vf)[0] for vf in files]}


class VoiceNameRequest(BaseModel):
    name: str


@router.post("/voices")
async def get_voice(body: VoiceNameRequest):
    """获取单个音色文件的详细元数据"""
    name = body.name
    full_path = voice_manager.resolve_voice_file(name)
    if not full_path:
        raise_error(status_code=404, detail=f"Voice not found: {name}")

    try:
        branch = get_cache_manager().branch
        meta = await branch.voice_load_meta(full_path)
    except NotSupportedError as e:
        raise_error(status_code=400, detail="Operation not supported", debug=str(e))
    except Exception as exc:
        raise_error(
            status_code=503,
            detail="QwenTTS Worker 不可用",
            debug=str(exc),
        )

    if not meta:
        raise_error(status_code=422, detail=f"Failed to parse voice metadata: {name}")

    try:
        spk_dim = int(meta.get("_spk_dim", 0))
    except (TypeError, ValueError):
        spk_dim = 0
    meta["model"] = _get_base_models_by_spk_dim(spk_dim)
    return meta


class VoiceAudioPreviewRequest(BaseModel):
    name: str
    load: bool = False


def _get_base_model_by_spk_dim(spk_dim: int) -> str:
    """返回首个兼容 Base 模型 ID，供需要单个模型的内部流程使用。"""
    models = _get_base_models_by_spk_dim(spk_dim)
    return models[0] if models else ""


def _find_first_base_model_id() -> str:
    """在模型目录中查找第一个 Base 模型，返回模型 ID"""
    model_dir = settings.model_dir
    if not model_dir and settings.project_dir:
        model_dir = os.path.join(settings.project_dir, "models")
    if not model_dir or not os.path.isdir(model_dir):
        return ""
    for name in sorted(os.listdir(model_dir)):
        if "Qwen3-TTS" not in name and "qwen3-tts" not in name.lower():
            continue
        lower = name.lower().replace("-", "").replace("_", "")
        if "customvoice" in lower or "voicedesign" in lower or "tokenizer" in lower:
            continue
        return name
    return ""


@router.post("/voices/audio")
async def preview_voice_audio(body: VoiceAudioPreviewRequest):
    """解码音色文件的参考音频预览

    优先使用空闲的 Base 模型实例（空闲 GPU 上的实例优先）；
    load=true 时仅在无已加载 Base 模型的情况下才新加载。
    """
    name = body.name
    full_path = voice_manager.resolve_voice_file(name)
    if not full_path:
        raise_error(status_code=404, detail=f"Voice not found: {name}")

    cm = get_cache_manager()
    picked = await cm.pick_loaded_instance("base")
    model_id = picked[0] if picked else ""
    gpu = picked[1] if picked else None

    if not model_id:
        if body.load:
            model_id = _find_first_base_model_id()
            if not model_id:
                raise_error(status_code=400, detail="No Base model available")
            await cm.load_model(model_id, "base")
            picked = await cm.pick_loaded_instance("base")
            gpu = picked[1] if picked else None
        else:
            return {"ok": True}

    model_path = resolve_model_path(model_id)
    try:
        result = await cm.branch.decode_voice_preview(full_path, model_path, gpu_id=gpu)
    except NotSupportedError as e:
        raise_error(status_code=400, detail="Operation not supported", debug=str(e))
    except RuntimeError as e:
        raise_error(status_code=500, detail="Audio decoding failed", debug=str(e))
    await cm.touch_model(model_id, gpu)
    if result and result.get("ok"):
        return result
    raise_error(status_code=500, detail="Audio decoding failed")


class VoiceUploadRequest(BaseModel):
    """音色上传请求体"""
    audio: str
    name: Optional[str] = None
    model: str
    text: Optional[str] = None
    x_vector_only: Optional[bool] = None


@router.post("/voices/upload")
async def upload_voice(body: VoiceUploadRequest):
    """上传并创建音色文件"""
    from ..audio import download_audio

    raw_name = (body.name or "").strip() or "default"

    has_text = bool(body.text and body.text.strip())
    has_xvec = body.x_vector_only is True
    if has_text and has_xvec:
        raise_error(status_code=400, detail="ref_text and x_vector_only are mutually exclusive")

    is_icl = body.x_vector_only is False or (body.x_vector_only is None and has_text)
    if is_icl and not has_text:
        raise_error(status_code=400, detail="ref_text is required when x_vector_only is false (ICL mode)")

    is_xvec = not is_icl
    ref_text = body.text.strip() if has_text else None
    final_name = voice_manager.auto_increment_name(raw_name)

    try:
        model_path = resolve_model_path(body.model)
        cache = get_cache_manager()
        branch = cache.branch

        await cache.load_model(body.model, "base")

        wav, sr = download_audio(body.audio)

        items = await branch.create_voice_clone_prompt(
            model_path=model_path,
            ref_audio=(wav, sr),
            ref_text=ref_text,
            x_vector_only=is_xvec,
        )

        out_path = await branch.voice_save(
            items=items,
            custom_name=final_name,
        )

        await cache.touch_model(body.model)

        return {"path": out_path}

    except (HTTPException, APIError):
        raise
    except ValueError as e:
        raise_error(status_code=400, detail="Invalid voice input", debug=str(e))
    except NotSupportedError as e:
        raise_error(status_code=400, detail="Operation not supported", debug=str(e))
    except Exception as e:
        raise_error(status_code=500, detail="Voice save failed", debug=str(e))


class VoiceEditRequest(BaseModel):
    """音色编辑请求体"""
    name: str
    new_name: Optional[str] = None
    text: Optional[str] = None
    audio: Optional[str] = None
    model: Optional[str] = None
    x_vector_only: Optional[bool] = None


@router.post("/voices/edit")
async def edit_voice(body: VoiceEditRequest):
    """编辑音色文件"""
    full_path = voice_manager.resolve_voice_file(body.name)
    if not full_path:
        raise_error(status_code=404, detail=f"Voice not found: {body.name}")

    cache = get_cache_manager()
    branch = cache.branch

    try:
        meta = await branch.voice_load_meta(full_path) or {}
    except NotSupportedError as e:
        raise_error(status_code=400, detail="Operation not supported", debug=str(e))

    if body.text is not None and body.text.strip() and body.x_vector_only is True:
        raise_error(status_code=400, detail="ref_text and x_vector_only are mutually exclusive")

    if body.audio:
        spk_dim = meta.get("_spk_dim", 0)
        resolved = _get_base_model_by_spk_dim(spk_dim) if spk_dim else ""
        model_id = body.model or resolved
        if not model_id:
            raise_error(status_code=400, detail="No model available for audio update")

        try:
            model_path = resolve_model_path(model_id)
        except ValueError as e:
            raise_error(status_code=400, detail="Invalid model ID", debug=str(e))

        from ..audio import download_audio

        await cache.load_model(model_id, "base")
        wav, sr = download_audio(body.audio)

        ref_text = body.text if body.text is not None else meta.get("text", "")
        use_xvec = body.x_vector_only if body.x_vector_only is not None else meta.get("x_vector_only", False)

        try:
            new_items = await branch.create_voice_clone_prompt(
                model_path=model_path,
                ref_audio=(wav, sr),
                ref_text=ref_text.strip() if ref_text else None,
                x_vector_only=use_xvec,
            )

            current_name = os.path.splitext(os.path.basename(full_path))[0]
            out_path = await branch.voice_save(
                items=new_items,
                custom_name=body.new_name or current_name,
            )
        except NotSupportedError as e:
            raise_error(status_code=400, detail="Operation not supported", debug=str(e))
        await cache.touch_model(model_id)
        if body.new_name and full_path != out_path:
            try:
                os.remove(full_path)
            except OSError:
                pass
        return {"status": "updated", "path": out_path}

    item_updates: Dict[int, Dict[str, Any]] = {}
    has_changes = False

    if body.text is not None:
        item_updates[0] = {"ref_text": body.text}
        has_changes = True

    if body.x_vector_only is not None:
        item_updates[0] = {
            **item_updates.get(0, {}),
            "x_vector_only_mode": body.x_vector_only,
            "icl_mode": not body.x_vector_only,
        }
        has_changes = True

    name_changed = body.new_name is not None

    if not has_changes and not name_changed:
        return {"status": "no_change", "path": full_path}

    if has_changes:
        try:
            await branch.voice_update_meta(full_path, item_updates=item_updates)
        except NotSupportedError as e:
            raise_error(status_code=400, detail="Operation not supported", debug=str(e))

    out_path = full_path
    if name_changed:
        safe_name = voice_manager.sanitize_voice_path(body.new_name)
        safe = voice_manager._safe_join_name(safe_name)
        if safe is None:
            raise_error(status_code=400, detail=f"Invalid voice name: {body.new_name}")
        out_path = str(safe)
        if full_path != out_path:
            import shutil
            shutil.move(full_path, out_path)

    return {"status": "updated", "path": out_path}


class VoiceDeleteRequest(BaseModel):
    name: str


@router.post("/voices/delete")
async def delete_voice(body: VoiceDeleteRequest):
    """删除指定音色文件"""
    if voice_manager.delete_voice(body.name):
        return {"status": "deleted"}
    raise_error(status_code=404, detail=f"Voice not found: {body.name}")

"""设置管理 API 路由"""
import asyncio
import logging
from pathlib import Path
from fastapi import APIRouter
from pydantic import BaseModel, Field, StrictInt
from ..config import parse_gpu_devices, settings, save_settings
from ..branches import discover_branches
from ..errors import raise_error

_logger = logging.getLogger("qwen-webui.settings")

router = APIRouter(tags=["settings"])

_MIN_CONCURRENT = 1
_MAX_CONCURRENT_MODELS = 16
_MIN_IDLE_UNLOAD = 0
_MAX_IDLE_UNLOAD = 86400
_MIN_MAX_SEQ_LEN = 1
_MAX_MAX_SEQ_LEN = 32767


def _validate_dir_path(value: str, field_name: str, must_exist: bool = True) -> Path:
    if not value:
        return Path("")
    if ".." in Path(value).parts:
        raise_error(
            status_code=400,
            detail=f"{field_name}: path must not contain ..",
            debug=f"input: {value}",
        )
    resolved = Path(value).resolve()
    if must_exist:
        if not resolved.is_dir():
            raise_error(
                status_code=400,
                detail=f"{field_name}: directory not found",
                debug=str(resolved),
            )
    else:
        if not resolved.exists() and not resolved.parent.is_dir():
            raise_error(
                status_code=400,
                detail=f"{field_name}: parent directory not found",
                debug=str(resolved.parent),
            )
    return resolved


def _validate_branch(value: str) -> str:
    available = discover_branches()
    if not value or not value.strip():
        raise_error(status_code=400, detail="backend_branch is required")
    if value not in available:
        raise_error(
            status_code=400,
            detail=f"Unsupported branch: {value}",
            debug=f"available: {list(available.keys())}",
        )
    return value.strip()


class SettingsUpdate(BaseModel):
    """设置更新请求体"""
    gpu_devices: str | None = None
    max_concurrent_models: int | None = Field(None, ge=_MIN_CONCURRENT, le=_MAX_CONCURRENT_MODELS)
    idle_unload_seconds: int | None = Field(None, ge=_MIN_IDLE_UNLOAD, le=_MAX_IDLE_UNLOAD)
    worker_idle_unload_seconds: int | None = Field(None, ge=_MIN_IDLE_UNLOAD, le=_MAX_IDLE_UNLOAD)
    backend_branch: str | None = None
    project_dir: str | None = None
    env_dir: str | None = None
    model_dir: str | None = None
    voice_dir: str | None = None
    max_seq_len: StrictInt | None = Field(None, ge=_MIN_MAX_SEQ_LEN, le=_MAX_MAX_SEQ_LEN)


@router.get("/api/settings")
async def get_settings():
    """获取当前服务端配置"""
    return {
        **settings.to_dict(),
        "backend_branch_options": list(discover_branches().keys()),
    }


@router.put("/api/settings")
async def update_settings(data: SettingsUpdate):
    """更新服务端配置"""
    data_dict = data.model_dump(exclude_none=True)

    if "gpu_devices" in data_dict:
        try:
            parse_gpu_devices(data_dict["gpu_devices"])
        except ValueError as e:
            raise_error(status_code=400, detail="Invalid gpu_devices format", debug=str(e))
    if "backend_branch" in data_dict:
        _validate_branch(data_dict["backend_branch"])
    if "project_dir" in data_dict:
        _validate_dir_path(data_dict["project_dir"], "project_dir", must_exist=True)
    if "env_dir" in data_dict:
        _validate_dir_path(data_dict["env_dir"], "env_dir", must_exist=True)
    if "model_dir" in data_dict:
        _validate_dir_path(data_dict["model_dir"], "model_dir", must_exist=True)
    if "voice_dir" in data_dict:
        _validate_dir_path(data_dict["voice_dir"], "voice_dir", must_exist=False)

    old_branch = settings.backend_branch
    old_project_dir = settings.project_dir
    old_max_seq_len = settings.max_seq_len
    old_max_concurrent = settings.max_concurrent_models
    settings.update(data_dict)
    save_settings()

    branch_changed = data.backend_branch is not None and data.backend_branch != old_branch
    project_changed = data.project_dir is not None and data.project_dir != old_project_dir
    max_seq_len_changed = data.max_seq_len is not None and data.max_seq_len != old_max_seq_len
    max_concurrent_changed = (
        data.max_concurrent_models is not None and data.max_concurrent_models != old_max_concurrent
    )

    if branch_changed or project_changed or max_seq_len_changed:
        from ..cache import get_cache_manager
        cm = get_cache_manager()
        await cm.worker_stop(stop_all=True)
        cm._branch = None
        from ..branches import clear_branch_cache
        clear_branch_cache()
        from .ws import broadcast_backend_status, broadcast_cache_status, broadcast_worker_status
        asyncio.create_task(broadcast_cache_status())
        asyncio.create_task(broadcast_worker_status())
        if branch_changed:
            asyncio.create_task(broadcast_backend_status())

    if max_concurrent_changed and data.max_concurrent_models < old_max_concurrent:
        # 调低并发上限后，若当前缓存实例数超出新上限，
        # 按 LRU 淘汰超出部分（忙碌实例由缓存管理器在推理完成后卸载）。
        from ..cache import get_cache_manager
        cm = get_cache_manager()
        evicted = await cm.enforce_max_concurrent()
        if evicted:
            from .ws import broadcast_cache_status
            asyncio.create_task(broadcast_cache_status())
            _logger.info("Evicted %d instances after lowering max_concurrent_models", len(evicted))

    return {
        **settings.to_dict(),
        "backend_branch_options": list(discover_branches().keys()),
    }

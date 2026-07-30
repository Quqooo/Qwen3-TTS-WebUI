"""
音色文件管理模块

负责 QwenTTS 音色文件（.pt 格式）的 CRUD 操作。
仅包含不依赖 torch 的路径操作（列表、解析、删除）；
涉及 .pt 文件内数据读取和写入的操作（加载元数据、加载提示项、保存）
交由后端分支（branches）通过 QwenTTS Worker 子进程处理。
"""
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import settings


def _voice_dir() -> str:
    """获取音色文件目录"""
    if settings.voice_dir:
        return settings.voice_dir
    if settings.project_dir:
        return os.path.join(settings.project_dir, "voice")
    return ""


def _voice_dir_resolved() -> Optional[Path]:
    vd = _voice_dir()
    if not vd:
        return None
    return Path(vd).resolve()


def _safe_path(relative_path: str) -> Optional[Path]:
    """将相对路径与 voice_dir 拼接后解析，验证未越界"""
    vd_resolved = _voice_dir_resolved()
    if vd_resolved is None:
        return None
    if os.path.isabs(relative_path):
        return None
    parts = Path(relative_path).parts
    if ".." in parts:
        return None
    candidate = (vd_resolved / relative_path).resolve()
    try:
        candidate.relative_to(vd_resolved)
    except ValueError:
        return None
    return candidate


def _safe_join_name(name: str, ext: str = ".pt") -> Optional[Path]:
    """将音色名称安全拼接到 voice_dir，返回解析后的 Path 或 None"""
    vd_resolved = _voice_dir_resolved()
    if vd_resolved is None:
        return None
    candidate = (vd_resolved / (name + ext)).resolve()
    try:
        candidate.relative_to(vd_resolved)
    except ValueError:
        return None
    candidate.parent.mkdir(parents=True, exist_ok=True)
    return candidate


def _ensure_voice_dir() -> str:
    """确保音色目录存在并返回路径"""
    vd = _voice_dir()
    if vd:
        os.makedirs(vd, exist_ok=True)
    return vd


def list_voice_files() -> List[str]:
    """列出所有音色文件（.pt），返回相对于音色目录的路径列表"""
    vd = _voice_dir()
    if not vd or not os.path.isdir(vd):
        return []
    result = []
    for root, _dirs, files in os.walk(vd):
        for f in files:
            if f.endswith(".pt"):
                rel = os.path.relpath(os.path.join(root, f), vd)
                result.append(rel.replace("\\", "/"))
    return sorted(result)


def resolve_voice_file(voice: str) -> Optional[str]:
    """根据音色名称查找音色文件，仅在 voice_dir 内匹配"""
    vd = _voice_dir()
    if not vd:
        return None
    if os.path.isabs(voice):
        vd_resolved = _voice_dir_resolved()
        if vd_resolved is not None:
            try:
                candidate = Path(voice).resolve()
                candidate.relative_to(vd_resolved)
                if candidate.exists():
                    return str(candidate)
            except ValueError:
                pass
        return None
    if ".." in Path(voice).parts:
        return None

    available = list_voice_files()
    for vf in available:
        if vf == voice or vf == voice + ".pt" or os.path.splitext(vf)[0] == voice:
            full = _safe_path(vf)
            return str(full) if full else None
    return None


def sanitize_voice_name(name: str) -> str:
    """清理音色名称，去除文件系统不安全字符及路径遍历字符"""
    safe = "".join(c for c in name.strip() if c not in '\\/:*?"<>|')
    safe = safe.strip(".") or "untitled"
    replaced = safe.replace("..", "_")
    return replaced.strip("_") or "untitled"


def sanitize_voice_path(name: str) -> str:
    """清理音色路径名，允许 / 但禁止 .. 和绝对路径"""
    safe = "".join(c for c in name.strip() if c not in '\\:*?"<>|')
    safe = safe.strip() or "untitled"
    safe = safe.replace("\\", "/")
    parts = [p for p in safe.split("/") if p and p != "." and p != ".."]
    if not parts:
        return "untitled"
    return "/".join(parts)


def auto_increment_name(name: str) -> str:
    """如果名称已存在则自动递增序号"""
    safe = sanitize_voice_name(name)
    available = list_voice_files()
    existing_names = {os.path.splitext(vf)[0] for vf in available}
    if safe not in existing_names:
        return safe
    idx = 1
    while f"{safe}_{idx}" in existing_names:
        idx += 1
    return f"{safe}_{idx}"


def delete_voice(name: str) -> bool:
    """删除指定名称的音色文件"""
    vd_resolved = _voice_dir_resolved()
    if vd_resolved is None:
        return False

    available = list_voice_files()
    for vf in available:
        vf_name = os.path.splitext(vf)[0]
        if vf_name == name:
            candidate = _safe_path(vf)
            if candidate and candidate.exists():
                candidate.unlink()
                return True
    return False

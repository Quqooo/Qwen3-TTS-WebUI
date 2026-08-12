"""
后端分支加载器

根据配置中的 backend_branch 值，延迟加载对应的 TTSBranch 实现。
各分支存放在 branches/ 目录下各自的子目录中，仅在首次调用 get_branch()
时导入，避免在 Web 后端启动时加载 QwenTTS 依赖。

分支发现方式：扫描 branches/<子目录>/__init__.py 文件中声明的 branch_names
列表来建立 分支名 → 模块路径 的映射。
"""
import importlib
import logging
import os
from typing import Dict, Optional

from .base import TTSBranch
from ..config import settings

_logger = logging.getLogger("qwen-webui.branches")

_branch_instance: Optional[TTSBranch] = None

# 分支名 → 模块路径（如 ".qwenlm"）的映射，由 discover_branches() 构建
_BRANCH_MODULES: Dict[str, str] = {}
_discovered = False


def _discover_branches() -> Dict[str, str]:
    """扫描 branches/<subdir>/__init__.py，提取每个子目录声明的 branch_names

    返回: {分支名: 模块路径}
    """
    result: Dict[str, str] = {}
    branches_dir = os.path.dirname(__file__)

    for entry in sorted(os.listdir(branches_dir)):
        init_path = os.path.join(branches_dir, entry, "__init__.py")
        if not os.path.isfile(init_path):
            continue
        if not os.path.isdir(os.path.join(branches_dir, entry)):
            continue

        try:
            module = importlib.import_module(f".{entry}", package=__package__)
            names = getattr(module, "branch_names", None)
            if not names or not isinstance(names, list):
                continue
            for name in names:
                if not isinstance(name, str):
                    continue
                if name in result:
                    _logger.warning(
                        "Duplicate branch name %s: %s and %s", name, result[name], f".{entry}"
                    )
                result[name] = f".{entry}"
        except Exception as e:
            _logger.warning("Failed to load branch module %s: %s", entry, e)

    return result


def discover_branches() -> Dict[str, str]:
    """公开接口：返回 {分支名: 模块路径} 映射"""
    return _discover_branches()


def get_branch() -> TTSBranch:
    """获取当前配置分支的 TTSBranch 实例"""
    global _branch_instance, _BRANCH_MODULES, _discovered

    if _branch_instance is not None:
        return _branch_instance

    if not _discovered:
        _BRANCH_MODULES = _discover_branches()
        _discovered = True

    branch_name = settings.backend_branch
    module_path = _BRANCH_MODULES.get(branch_name)

    if not module_path:
        available = list(_BRANCH_MODULES.keys())
        raise RuntimeError(
            f"Unsupported backend branch: {branch_name}. "
            f"Available: {available}"
        )

    _logger.info("Loading backend branch: %s (module: %s)", branch_name, module_path)
    module = importlib.import_module(module_path, package=__package__)

    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if isinstance(attr, type) and issubclass(attr, TTSBranch) and attr is not TTSBranch:
            _branch_instance = attr()
            _logger.info("Backend branch loaded: %s", branch_name)
            return _branch_instance

    raise RuntimeError(f"No TTSBranch implementation found in module {module_path}")


def clear_branch_cache() -> None:
    """清除分支实例缓存"""
    global _branch_instance
    _branch_instance = None

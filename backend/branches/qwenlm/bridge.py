"""
QwenLM/Qwen3-TTS 官方分支桥接模块

官方推理实现，不支持流式生成。
推理管道由 PooledWorkerBranch 实现（每 GPU 一个 Worker 子进程）。
"""
import logging
import os
from typing import Any, Dict

from ..pooled_branch import PooledWorkerBranch
from ...config import settings

_logger = logging.getLogger("qwen-webui.branch.official")

_PROVIDER_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "worker_provider.py"))


class QwenBranch(PooledWorkerBranch):
    """QwenLM/Qwen3-TTS 官方分支实现（Worker 池，无流式）"""

    _streaming_supported = False

    @property
    def name(self) -> str:
        return "QwenLM/Qwen3-TTS"

    def __init__(self):
        super().__init__(_PROVIDER_FILE, _logger)

    def _load_provider_options(self) -> Dict[str, Any]:
        return dict(settings.qwenlm)

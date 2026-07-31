"""
dffdeeq/Qwen3-TTS-streaming 分支桥接模块

使用相同的 Qwen3-TTS 模型架构与流式推理实现。
推理管道由 PooledWorkerBranch 实现（每 GPU 一个 Worker 子进程）。
"""
import logging
import os
from typing import Any, Dict

from ..pooled_branch import PooledWorkerBranch

_logger = logging.getLogger("qwen-webui.branch.streaming")

_PROVIDER_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "worker_provider.py"))


class StreamingBranch(PooledWorkerBranch):
    """dffdeeq/Qwen3-TTS-streaming 分支实现（Worker 池，流式推理）"""

    @property
    def name(self) -> str:
        return "dffdeeq/Qwen3-TTS-streaming"

    def __init__(self):
        super().__init__(_PROVIDER_FILE, _logger)

    def _load_provider_options(self) -> Dict[str, Any]:
        return {
            "use_compile": True,
            "use_cuda_graphs": False,
            "compile_mode": "reduce-overhead",
            "use_fast_codebook": True,
            "compile_codebook_predictor": True,
            "compile_talker": True,
        }

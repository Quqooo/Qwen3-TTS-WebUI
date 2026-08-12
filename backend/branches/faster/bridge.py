"""
andimarafioti/faster-qwen3-tts 分支桥接模块

使用 FasterQwen3TTS (CUDA graph) 实现 6-10x 推理加速。
推理管道由 PooledWorkerBranch 实现（每 GPU 一个 Worker 子进程）。
"""
import logging
import os
from typing import Any, Dict

from ...config import settings
from ..pooled_branch import PooledWorkerBranch

_logger = logging.getLogger("qwen-webui.branch.faster")

_PROVIDER_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "worker_provider.py"))


class FasterBranch(PooledWorkerBranch):
    """andimarafioti/faster-qwen3-tts 分支实现（Worker 池 + CUDA graph 加速）

    支持流式和非流式生成。使用 chunk_size 控制流式输出粒度。
    """

    @property
    def name(self) -> str:
        return "andimarafioti/faster-qwen3-tts"

    def __init__(self):
        super().__init__(_PROVIDER_FILE, _logger)

    def _load_provider_options(self) -> Dict[str, Any]:
        config = settings.andimarafioti
        max_seq_len = int(config["max_seq_len"])
        return {
            "backend": "torch",
            "max_seq_len": max_seq_len,
            "warmup_prefill_len": min(100, max_seq_len - 1),
            "predictor_graph": dict(config["predictor_graph"]),
        }

    def _generation_runtime_params(self) -> Dict[str, Any]:
        return {
            "provider_runtime": {
                "predictor_graph": dict(settings.andimarafioti["predictor_graph"]),
            },
        }

    def _stream_params(
        self,
        dffdeeq: Any = None,
        andimarafioti: Any = None,
    ) -> Dict[str, Any]:
        return {
            "andimarafioti": dict(andimarafioti or {}),
            "dffdeeq": dict(dffdeeq or {}),
        }

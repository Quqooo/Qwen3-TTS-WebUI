# QwenLM/Qwen3-TTS 官方分支适配器
# 基于 Qwen 官方发布的模型权重，不支持流式推理。
branch_names = [
    "QwenLM/Qwen3-TTS",
]

from .bridge import QwenBranch

__all__ = ["QwenBranch", "branch_names"]

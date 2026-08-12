# dffdeeq/Qwen3-TTS-streaming 分支适配器
# 基于 Qwen3-TTS 的社区分支，额外支持流式推理优化。
branch_names = [
    "dffdeeq/Qwen3-TTS-streaming",
]

from .bridge import StreamingBranch

__all__ = ["StreamingBranch", "branch_names"]

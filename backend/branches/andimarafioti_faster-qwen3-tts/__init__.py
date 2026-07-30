# andimarafioti/faster-qwen3-tts branch adapter
# CUDA graph-based TTS with 6-10x inference speedup.
branch_names = [
    "andimarafioti/faster-qwen3-tts",
]

from .bridge import FasterBranch

__all__ = ["FasterBranch", "branch_names"]

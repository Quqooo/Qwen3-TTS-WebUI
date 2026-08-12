"""
TTS 后端分支基类

所有 QwenTTS 后端分支模块必须实现此类定义的方法。
分支模块通过 `branches/__init__.py` 中的 get_branch() 函数延迟加载，
避免在 Web 后端启动时导入 QwenTTS 依赖。
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Generator, List, Optional, Tuple

import numpy as np


class NotSupportedError(RuntimeError):
    """该后端分支不支持此功能

    当分支子类未覆盖某方法时，默认实现抛出此异常。
    路由层通过捕获 NotSupportedError 向客户端返回 400 提示。
    """
    ...


class TTSBranch(ABC):
    """后端分支抽象基类

    定义了模型生命周期管理和三种模型类型生成接口。
    实现类应延迟导入具体的 QwenTTS 包。

    各分支的支持功能可能不一致（如官方分支不支持流式推理）。
    对于可选功能，基类提供默认 raise NotSupportedError 的实现，
    分支只需覆盖它支持的方法即可。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """分支名称，与配置中的 backend_branch 值对应"""
        ...

    # ── 模型生命周期管理 ────────────────────────────────────────

    @abstractmethod
    def load_model(self, model_path: str, model_kind: str, load_kwargs: Optional[Dict[str, Any]] = None,
                   gpu_id: Optional[str] = None) -> None:
        """加载模型；gpu_id 指定目标 GPU（None 时由实现按优先级选择）"""
        ...

    @abstractmethod
    def unload_model(self, model_path: str, gpu_id: Optional[str] = None) -> None:
        """卸载模型；gpu_id 指定卸载单个实例，None 卸载全部实例"""
        ...

    @abstractmethod
    def unload_idle_models(self, max_idle_seconds: float) -> List[str]:
        ...

    @abstractmethod
    def cached_models(self) -> Dict[str, Dict[str, Any]]:
        ...

    @abstractmethod
    def get_supported_options(self, model_path: str) -> Dict[str, Any]:
        ...

    async def wait_model_stoppable(self, model_path: str, gpu_id: Optional[str] = None) -> None:
        """Wait until the current model operation reaches a safe stop point.

        In-process implementations may override this when their inference engine
        has an explicit non-interruptible phase. Worker-based implementations
        use the worker model lock as the safety boundary.
        gpu_id 指定等待单个实例，None 等待全部实例。
        """

    # ── Worker 生命周期管理 ─────────────────────────────────────

    @abstractmethod
    def worker_start(self, gpu_id: Optional[str] = None) -> None:
        """启动 Worker 子进程；gpu_id 指定 GPU，None 按优先级启动第一个未运行的"""
        ...

    @abstractmethod
    def worker_stop(self, gpu_id: Optional[str] = None, stop_all: bool = False) -> None:
        """等待不可中断操作到达安全边界后停止 Worker 子进程。"""
        ...

    @abstractmethod
    def worker_force_stop(self, gpu_id: Optional[str] = None, stop_all: bool = False) -> None:
        """立即终止 Worker 子进程，不等待推理到达安全边界。"""
        ...

    @abstractmethod
    def worker_status(self) -> Dict[str, Any]:
        """返回 Worker 运行状态（含各 GPU 的 workers 数组）"""
        ...

    # ── 生成接口 ────────────────────────────────────────────────

    @abstractmethod
    def generate_voice_clone(
        self,
        model_path: str,
        text: str,
        language: str = "Auto",
        ref_audio: Optional[Any] = None,
        ref_text: Optional[str] = None,
        x_vector_only: bool = False,
        voice_file: Optional[str] = None,
        generation_params: Optional[Dict[str, Any]] = None,
        instruct: Optional[str] = None,
    ) -> Tuple[List[np.ndarray], int]:
        """Base 模型：语音克隆生成

        model_path: 模型路径
        text: 合成文本
        language: 语言
        ref_audio: 参考音频 (np.ndarray, sr) 或 URL 或路径
        ref_text: 参考文本
        x_vector_only: 是否仅使用说话人嵌入（不使用 ICL）
        voice_file: 音色文件路径（与 ref_audio/ref_text 互斥）
        instruct: 可选生成指令（由支持 Base instruct 的后端使用）
        generation_params: 生成参数（do_sample, top_k, top_p, temperature、seed 等）

        返回: (音频列表, 采样率)
        """
        ...

    def generate_custom_voice(
        self,
        model_path: str,
        text: str,
        speaker: str,
        language: str = "Auto",
        instruct: Optional[str] = None,
        generation_params: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[np.ndarray], int]:
        """CustomVoice 模型：固定说话人语音合成

        model_path: 模型路径
        text: 合成文本
        speaker: 说话人名称
        language: 语言
        instruct: 指令文本（控制语气/风格等）
        generation_params: 生成参数

        返回: (音频列表, 采样率)
        默认抛出 NotSupportedError，分支覆盖此方法以支持固定说话人合成。
        """
        raise NotSupportedError(f"{self.name} does not support custom voice")

    def generate_voice_design(
        self,
        model_path: str,
        text: str,
        instruct: str,
        language: str = "Auto",
        generation_params: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[np.ndarray], int]:
        """VoiceDesign 模型：自然语言音色设计语音合成

        model_path: 模型路径
        text: 合成文本
        instruct: 音色描述指令
        language: 语言
        generation_params: 生成参数

        返回: (音频列表, 采样率)
        默认抛出 NotSupportedError，分支覆盖此方法以支持音色设计合成。
        """
        raise NotSupportedError(f"{self.name} does not support voice design")

    def stream_generate_voice_clone(
        self,
        model_path: str,
        text: str,
        language: str = "Auto",
        ref_audio: Optional[Any] = None,
        ref_text: Optional[str] = None,
        x_vector_only: bool = False,
        voice_file: Optional[str] = None,
        emit_every_frames: int = 8,
        decode_window_frames: int = 80,
        overlap_samples: int = 0,
        chunk_size: int = 12,
        max_frames: int = 10000,
        generation_params: Optional[Dict[str, Any]] = None,
        instruct: Optional[str] = None,
    ) -> Generator[Tuple[np.ndarray, int], None, None]:
        """Base 模型：流式语音克隆生成

        参数同 generate_voice_clone，额外支持流式控制参数。
        chunk_size 仅 Faster 分支生效（每块 codec 步数，12 ≈ 1 秒）。
        以生成器方式逐个返回音频块。
        默认抛出 NotSupportedError，分支覆盖此方法以支持流式。
        """
        raise NotSupportedError(f"{self.name} does not support streaming inference")

    def stream_generate_custom_voice(
        self,
        model_path: str,
        text: str,
        speaker: str,
        language: str = "Auto",
        instruct: Optional[str] = None,
        emit_every_frames: int = 8,
        decode_window_frames: int = 80,
        overlap_samples: int = 0,
        chunk_size: int = 12,
        max_frames: int = 10000,
        generation_params: Optional[Dict[str, Any]] = None,
    ) -> Generator[Tuple[np.ndarray, int], None, None]:
        """CustomVoice 模型：流式固定说话人语音合成

        参数同 generate_custom_voice，额外支持流式控制参数。
        chunk_size 仅 Faster 分支生效（每块 codec 步数，12 ≈ 1 秒）。
        以生成器方式逐个返回音频块。
        默认抛出 NotSupportedError，分支覆盖此方法以支持流式。
        """
        raise NotSupportedError(f"{self.name} does not support streaming inference")

    def stream_generate_voice_design(
        self,
        model_path: str,
        text: str,
        instruct: str,
        language: str = "Auto",
        emit_every_frames: int = 8,
        decode_window_frames: int = 80,
        overlap_samples: int = 0,
        chunk_size: int = 12,
        max_frames: int = 10000,
        generation_params: Optional[Dict[str, Any]] = None,
    ) -> Generator[Tuple[np.ndarray, int], None, None]:
        """VoiceDesign 模型：流式自然语言音色设计语音合成

        参数同 generate_voice_design，额外支持流式控制参数。
        chunk_size 仅 Faster 分支生效（每块 codec 步数，12 ≈ 1 秒）。
        以生成器方式逐个返回音频块。
        默认抛出 NotSupportedError，分支覆盖此方法以支持流式。
        """
        raise NotSupportedError(f"{self.name} does not support streaming inference")

    def create_voice_clone_prompt(
        self,
        model_path: str,
        ref_audio: Any,
        ref_text: Optional[str] = None,
        x_vector_only: bool = False,
    ) -> List[dict]:
        """Base 模型：创建语音克隆提示项

        用于将参考音频处理为提示项，可保存为音色文件。
        返回序列化后的 dict 列表（可直接发送给 Worker 保存）。
        默认抛出 NotSupportedError，分支覆盖此方法以支持音色文件创建。
        """
        raise NotSupportedError(f"{self.name} does not support base prompt creation")

    # ── 音色文件 I/O（通过 Worker 子进程处理 .pt 文件） ────────

    def voice_load_meta(self, voice_file_path: str) -> Optional[Dict[str, Any]]:
        """读取音色文件的元数据

        voice_file_path: resolve_voice_file() 返回的完整路径
        返回: {"customName", "text", "x_vector_only", "_spk_dim"} 或 None
        默认抛出 NotSupportedError，分支覆盖此方法以支持音色元数据读取。
        """
        raise NotSupportedError(f"{self.name} does not support voice metadata loading")

    async def voice_save(
        self,
        items: List[dict],
        custom_name: str,
    ) -> str:
        """保存音色提示项到 .pt 文件

        items: 从 create_voice_clone_prompt() 返回的序列化 dict 列表
        custom_name: 用户自定义音色名称（即文件名）

        返回保存的文件路径。
        默认抛出 NotSupportedError，分支覆盖此方法以支持音色保存。
        """
        raise NotSupportedError(f"{self.name} does not support voice saving")

    async def decode_voice_preview(
        self,
        voice_file_path: str,
        model_path: str,
    ) -> Optional[Dict[str, Any]]:
        """从音色文件解码参考音频预览

        voice_file_path: .pt 文件的完整路径
        model_path: 用于解码的 Base 模型路径
        返回: {audio: base64, sr: int, duration: float} 或 None
        默认抛出 NotSupportedError，分支覆盖此方法以支持音色预览。
        """
        raise NotSupportedError(f"{self.name} does not support voice preview")

    async def voice_update_meta(
        self,
        voice_file_path: str,
        item_updates: Optional[Dict[int, Dict[str, Any]]] = None,
    ) -> str:
        """原地更新 .pt 音色文件的 items 字段

        voice_file_path: .pt 文件的完整路径
        item_updates: {items索引: 要合并的字段字典}
        返回: 保存后的文件路径
        默认抛出 NotSupportedError，分支覆盖此方法以支持音色元数据更新。
        """
        raise NotSupportedError(f"{self.name} does not support voice metadata update")

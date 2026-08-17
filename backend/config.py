"""
配置管理模块

负责 WebUI 服务端配置的加载、保存和运行时访问。
配置持久化存储于数据目录（见 resolve_data_dir）中的 settings.json。
"""
import json
import os
import re
import sys
from pathlib import Path
from typing import List

from fastapi import HTTPException


def resolve_data_dir() -> str:
    """返回 WebUI 可写数据目录（settings.json 持久化位置）。"""
    env_override = os.environ.get("QWEN3_WEBUI_DATA")
    if env_override:
        return os.path.abspath(env_override)
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "webui-data")
    return str(Path(__file__).parent)


def settings_path() -> Path:
    """settings.json 的持久化路径。"""
    return Path(resolve_data_dir()) / "settings.json"


def parse_gpu_devices(value: str) -> List[str]:
    """解析推理设备列表配置，返回按优先级排序的设备槽位列表。

    语法：以空白或逗号分隔的设备项，每项为单个编号（"2"）、区间（"3-5"）
    或单槽 token "cpu" / "mps"（大小写不敏感，分别为 CPU 与 Apple MPS
    推理槽位）。单槽不可写区间，且全列表仅允许出现一次。
    例如 "2 0 3-5 cpu" → ["2", "0", "3", "4", "5", "cpu"]，优先级按书写顺序。
    留空时默认 ["0"]。重复设备仅保留第一次出现的位置。
    """
    if not value or not value.strip():
        return ["0"]
    devices: List[str] = []
    single_slots = ("cpu", "mps")
    for token in re.split(r"[\s,]+", value.strip()):
        if not token:
            continue
        lowered = token.lower()
        if lowered in single_slots:
            if lowered not in devices:
                devices.append(lowered)
            continue
        m = re.fullmatch(r"(\d+)(?:-(\d+))?", token)
        if not m:
            raise ValueError(f"Invalid GPU device token: {token!r}")
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) is not None else start
        if end < start:
            raise ValueError(f"Invalid GPU device range: {token!r}")
        if end - start > 64:
            raise ValueError(f"GPU device range too large: {token!r}")
        for dev in range(start, end + 1):
            dev_id = str(dev)
            if dev_id not in devices:
                devices.append(dev_id)
    if not devices:
        return ["0"]
    return devices


class AppSettings:
    """服务端全局配置"""

    def __init__(self):
        # 模型缓存相关
        self.gpu_devices: str = ""             # 推理设备槽位，如 "2 0 3-5 cpu mps"，留空使用 0
        self.dtype: str = "auto"               # 推理精度：auto | bf16 | fp16 | float32
        self.max_concurrent_models: int = 1    # 每 GPU 最多加载的不同模型数
        self.idle_unload_seconds: int = 600    # 模型空闲卸载时间（秒）
        self.worker_idle_unload_seconds: int = 600  # Worker 空闲停止时间（秒）

        # QwenTTS 后端路径配置
        self.backend_branch: str = "QwenLM/Qwen3-TTS"  # 后端仓库分支
        self.project_dir: str = ""      # QwenTTS 项目所在目录
        self.env_dir: str = ""          # Python 环境目录（可选，留空则自动搜索）
        self.model_dir: str = ""        # 模型存放目录（可选，留空则使用 project_dir/models）
        self.voice_dir: str = ""        # 音色文件目录（可选，留空则使用 project_dir/voice）

        # andimarafioti/faster-qwen3-tts 分支专属配置
        self.faster: dict = {
            "max_seq_len": 2048,
            "predictor_graph": {
                "do_sample": True,
                "top_k": 50,
                "top_p": 1.0,
                "temperature": 0.9,
            },
        }

        # dffdeeq/Qwen3-TTS-streaming 分支专属配置
        self.streaming: dict = {
            "use_compile": True,
            "use_cuda_graphs": False,
            "compile_mode": "reduce-overhead",
            "use_fast_codebook": True,
            "compile_codebook_predictor": True,
            "compile_talker": True,
            "attn_implementation": "auto",
        }

        # QwenLM/Qwen3-TTS 官方分支专属配置
        self.qwenlm: dict = {
            "attn_implementation": "auto",
        }

        # 批量合成限制
        self.batch_composer: dict = {
            "max_segments": 1000,
            "max_output_samples": 100000000,
            "max_decoded_samples": 100000000,
            "max_total_decoded_samples": 100000000,
            "max_time_stretch_rate": 16.0,
            "max_audio_mib": 32,
            "max_total_audio_mib": 256,
            "min_sample_rate": 8000,
            "max_sample_rate": 192000,
        }

    @property
    def qwen_configured(self) -> bool:
        """QwenTTS 是否已配置"""
        return bool(self.project_dir)

    @property
    def max_seq_len(self) -> int:
        """兼容旧调用点的 Faster 静态 KV Cache 长度。"""
        return int(self.faster["max_seq_len"])

    def gpu_list(self) -> List[str]:
        """按优先级排序的可用 GPU 设备 ID 列表"""
        return parse_gpu_devices(self.gpu_devices)

    def to_dict(self) -> dict:
        """将当前配置序列化为字典，用于 API 响应和 JSON 持久化"""
        return {
            "gpu_devices": self.gpu_devices,
            "dtype": self.dtype,
            "max_concurrent_models": self.max_concurrent_models,
            "idle_unload_seconds": self.idle_unload_seconds,
            "worker_idle_unload_seconds": self.worker_idle_unload_seconds,
            "backend_branch": self.backend_branch,
            "project_dir": self.project_dir,
            "env_dir": self.env_dir,
            "model_dir": self.model_dir,
            "voice_dir": self.voice_dir,
            "faster": self.faster,
            "qwenlm": self.qwenlm,
            "streaming": self.streaming,
            "batch_composer": self.batch_composer,
        }

    def update(self, data: dict) -> None:
        """用传入的字典更新配置，仅更新字典中存在的键"""
        for key in (
            "dtype",
            "gpu_devices",
            "max_concurrent_models",
            "idle_unload_seconds",
            "worker_idle_unload_seconds",
            "backend_branch",
            "project_dir",
            "env_dir",
            "model_dir",
            "voice_dir",
        ):
            if key in data:
                setattr(self, key, data[key])

        faster = data.get("faster")
        if isinstance(faster, dict):
            predictor_graph = faster.get("predictor_graph")
            merged = {**self.faster, **faster}
            # 注意力实现固定为 SDPA（其他模式与 CUDA Graphs 不兼容），
            # 丢弃旧版 settings.json 中遗留的配置项。
            merged.pop("attn_implementation", None)
            if isinstance(predictor_graph, dict):
                merged["predictor_graph"] = {
                    **self.faster["predictor_graph"],
                    **predictor_graph,
                }
            self.faster = merged
        elif "max_seq_len" in data:
            # 兼容旧版 settings.json；下次保存时自动迁移到嵌套结构。
            self.faster["max_seq_len"] = data["max_seq_len"]

        if "streaming" in data and isinstance(data["streaming"], dict):
            self.streaming = {**self.streaming, **data["streaming"]}

        if "qwenlm" in data and isinstance(data["qwenlm"], dict):
            self.qwenlm = {**self.qwenlm, **data["qwenlm"]}

        if "batch_composer" in data and isinstance(data["batch_composer"], dict):
            self.batch_composer = {**self.batch_composer, **data["batch_composer"]}


settings = AppSettings()


def require_qwen() -> None:
    """QwenTTS 可用性校验依赖项"""
    if not settings.qwen_configured:
        raise HTTPException(
            status_code=503,
            detail="QwenTTS not configured. Please set project directory in settings.",
        )


def load_settings() -> None:
    """从 JSON 文件加载配置"""
    path = settings_path()
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        settings.update(data)
    else:
        save_settings()


def save_settings() -> None:
    """将当前配置持久化到 JSON 文件"""
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings.to_dict(), f, indent=2, ensure_ascii=False)


# ── 模型路径解析 ─────────────────────────────────────────────────


def validate_model_id(model_id: str) -> str:
    """校验 API 模型标识，仅允许 models 目录下的单级目录名。"""
    if not isinstance(model_id, str) or not model_id:
        raise ValueError("Model ID must be a non-empty string")
    if model_id != model_id.strip():
        raise ValueError("Model ID must not contain leading or trailing whitespace")
    if model_id in (".", "..") or "/" in model_id or "\\" in model_id:
        raise ValueError("Model must be an ID, not a filesystem path")
    if os.path.isabs(model_id) or os.path.splitdrive(model_id)[0] or "\x00" in model_id:
        raise ValueError("Model must be an ID, not a filesystem path")
    return model_id


def resolve_model_path(model_id: str) -> str:
    """将模型 ID 解析为 model_dir 内的绝对目录路径。"""
    validate_model_id(model_id)
    model_dir = settings.model_dir
    if not model_dir and settings.project_dir:
        model_dir = os.path.join(settings.project_dir, "models")
    if not model_dir:
        raise ValueError(f"model_dir not configured, cannot resolve model id: {model_id}")

    root = Path(model_dir).resolve()
    full = (root / model_id).resolve()
    try:
        full.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Model ID escapes model_dir: {model_id}") from exc
    if not full.is_dir():
        raise ValueError(f"Model not found: {model_id} (resolved: {full})")
    return str(full)


# ── 虚拟环境检测 ─────────────────────────────────────────────────


def detect_env_type(env_dir: str) -> str:
    """检测指定目录的虚拟环境类型，返回类型标识

    返回值:
      - "venv":   PEP 405 标准虚拟环境（由 venv/pyvenv/virtualenv 创建）
      - "conda":  Conda 环境
      - "python": 通用 Python 环境（目录中包含 python 可执行文件但无以上标志）
      - "":       无法识别
    """
    if not env_dir or not os.path.isdir(env_dir):
        return ""

    # PEP 405 标准虚拟环境标志文件
    if os.path.isfile(os.path.join(env_dir, "pyvenv.cfg")):
        return "venv"

    # Conda 环境标志文件
    if os.path.isfile(os.path.join(env_dir, "conda-meta", "history")):
        return "conda"

    # 通用 Python 环境：检查是否存在 python 可执行文件
    python_exe = os.path.join(env_dir, "Scripts", "python.exe")  # Windows
    if os.path.isfile(python_exe):
        return "python"
    python_bin = os.path.join(env_dir, "bin", "python")  # Unix/macOS
    if os.path.isfile(python_bin):
        return "python"
    if os.path.isfile(os.path.join(env_dir, "bin", "python3")):
        return "python"

    return ""


def resolve_env_python(env_dir: str) -> str:
    """返回指定虚拟环境目录中的 Python 可执行文件路径"""
    if not env_dir or not os.path.isdir(env_dir):
        return ""

    # 检查标准位置（Windows）
    exe = os.path.join(env_dir, "Scripts", "python.exe")
    if os.path.isfile(exe):
        return exe

    # Conda 环境（Windows）：python.exe 在环境根目录
    exe = os.path.join(env_dir, "python.exe")
    if os.path.isfile(exe):
        return exe

    # 检查标准位置（Unix/macOS）
    exe = os.path.join(env_dir, "bin", "python")
    if os.path.isfile(exe):
        return exe
    exe = os.path.join(env_dir, "bin", "python3")
    if os.path.isfile(exe):
        return exe

    # Conda 环境（Unix/macOS）：python3 在环境根目录
    exe = os.path.join(env_dir, "python3")
    if os.path.isfile(exe):
        return exe

    return ""

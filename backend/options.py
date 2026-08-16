"""设置页下拉枚举的单一注册表。

下拉可选项是只读元数据，不随 settings.json 持久化；GET/PUT 响应与
PUT 校验共用同一来源，避免多处手工构造导致漂移。
"""
from typing import Callable, Dict, List

from .branches import discover_branches

_DTYPES = ("auto", "bf16", "fp16", "float32")
_ATTN_IMPLEMENTATIONS = ("sdpa", "eager", "flash_attention_2", "flash_attention_3", "auto")
_COMPILE_MODES = ("default", "reduce-overhead", "max-autotune")

# 选项名 → 枚举构造器。静态枚举直接返回常量；backend_branch 动态扫描 branches/。
_OPTION_BUILDERS: Dict[str, Callable[[], List[str]]] = {
    "dtype": lambda: list(_DTYPES),
    "attn_implementation": lambda: list(_ATTN_IMPLEMENTATIONS),
    "compile_mode": lambda: list(_COMPILE_MODES),
    "backend_branch": lambda: list(discover_branches().keys()),
}


def options_payload() -> Dict[str, List[str]]:
    """生成 options 元数据载荷，供 GET/PUT 响应与 WS 后端消息复用。"""
    return {name: build() for name, build in _OPTION_BUILDERS.items()}


def option_allows(name: str, value: str) -> bool:
    """校验值是否属于指定枚举（PUT 校验用）。"""
    if name not in _OPTION_BUILDERS:
        raise ValueError(f"Unknown option name: {name}")
    return value in _OPTION_BUILDERS[name]()

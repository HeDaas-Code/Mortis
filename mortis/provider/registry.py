"""Provider 注册表 — 按名称注册/查找 provider 工厂函数 (issue #45)。

把 provider 选择从硬编码 if/elif 改为注册表模式:
- ``register_provider(name, factory)`` 注册新 provider 工厂
- ``get_provider(name, **kwargs)`` 按名称实例化 provider
- ``list_providers()`` 列出已注册名称
- ``make_provider(kind)`` 保留向后兼容的工厂入口 (内部走注册表)

注册表是模块级全局变量, 内置 mock / minimax 在
``mortis.provider.__init__`` 导入时自动注册。
"""

from __future__ import annotations

import os
from typing import Callable

from .base import LLMProviderProtocol

# 全局注册表: provider 名称 → 工厂函数 (调用后返回 LLMProviderProtocol 实例)
_registry: dict[str, Callable[..., LLMProviderProtocol]] = {}


def register_provider(name: str, factory: Callable[..., LLMProviderProtocol]) -> None:
    """注册一个 provider 工厂函数。

    Args:
        name: provider 名称 (如 "mock" / "minimax")。
        factory: 工厂函数, 调用 ``factory(**kwargs)`` 返回 provider 实例。
            重复注册同名 provider 会覆盖旧的。
    """
    _registry[name] = factory


def get_provider(name: str, **kwargs) -> LLMProviderProtocol:
    """按名称获取 provider 实例。

    Args:
        name: 已注册的 provider 名称。
        **kwargs: 透传给工厂函数。

    Returns:
        provider 实例。

    Raises:
        ValueError: 名称未注册。
    """
    if name not in _registry:
        raise ValueError(
            f"unknown provider: {name}, available: {list(_registry.keys())}"
        )
    return _registry[name](**kwargs)


def list_providers() -> list[str]:
    """列出已注册的 provider 名称 (按字母序)。"""
    return sorted(_registry.keys())


def make_provider(kind: str = "auto") -> LLMProviderProtocol:
    """工厂函数 — 根据 kind 返回合适的 provider (向后兼容)。

    内部走注册表, 因此新通过 ``register_provider`` 注册的 provider
    也能用 ``make_provider("<name>")`` 取到。

    Args:
        kind:
            "auto" = 有 ``MINIMAX_API_KEY`` 就用 minimax，否则 mock
            "minimax" = 强制 minimax (无 key 时调用报错)
            "mock" = 强制 mock
            其他 = 按注册表名称查找

    Raises:
        ValueError: kind 既非 "auto" 也未在注册表中注册。
    """
    if kind == "auto":
        name = "minimax" if os.environ.get("MINIMAX_API_KEY") else "mock"
        return get_provider(name)
    return get_provider(kind)

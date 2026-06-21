"""Mortis provider registry — provider 工厂。"""

from __future__ import annotations

from .base import LLMProviderProtocol
from .mock import MockProvider
from .minimax import MinimaxProvider


def make_provider(kind: str = "auto") -> LLMProviderProtocol:
    """工厂函数 — 根据 kind 返回合适的 provider。

    Args:
        kind:
            "auto" = 有 MINIMAX_API_KEY 就用 MinimaxProvider，否则 MockProvider
            "minimax" = 强制 MinimaxProvider（无 key 报错）
            "mock" = 强制 MockProvider
    """
    if kind == "mock":
        return MockProvider()
    if kind == "minimax":
        return MinimaxProvider()
    if kind == "auto":
        import os
        if os.environ.get("MINIMAX_API_KEY"):
            return MinimaxProvider()
        return MockProvider()
    raise ValueError(f"unknown provider kind: {kind!r}")

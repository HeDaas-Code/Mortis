"""Mortis LLM provider — 支持 mock / minimax。"""

from __future__ import annotations

from mortis.tools.base import ToolResult

from .base import (
    LLMProviderProtocol,
    Message,
    ToolCall,
    run_in_executor,
)
from .minimax import MinimaxAPIError, MinimaxAuthError, MinimaxProvider
from .mock import MockProvider
from .registry import make_provider

__all__ = [
    "LLMProviderProtocol",
    "Message",
    "ToolCall",
    "ToolResult",
    "MockProvider",
    "MinimaxProvider",
    "MinimaxAPIError",
    "MinimaxAuthError",
    "make_provider",
    "run_in_executor",
]

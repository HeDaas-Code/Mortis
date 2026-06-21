"""Mortis LLM provider — 支持 mock / minimax。"""

from __future__ import annotations

from .base import (
    LLMProviderProtocol,
    Message,
    ToolCall,
)
from .mock import MockProvider
from .minimax import MinimaxProvider, MinimaxAPIError, MinimaxAuthError
from .registry import make_provider
from mortis.tools.base import ToolResult

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
]

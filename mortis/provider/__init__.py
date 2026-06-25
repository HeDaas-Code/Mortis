"""Mortis LLM provider — 支持 mock / minimax + 注册表扩展 (issue #45) + async (issue #46) + 韧性层。"""

from __future__ import annotations

from mortis.tools.base import ToolResult

from .base import (
    LLMProviderProtocol,
    Message,
    StreamChunk,
    ToolCall,
    run_in_executor,
)
from .minimax import MinimaxAPIError, MinimaxAuthError, MinimaxProvider
from .mock import MockProvider
from .registry import (
    get_provider,
    list_providers,
    make_provider,
    register_provider,
)
from .resilience import (
    CircuitBreakerProvider,
    CircuitOpenError,
    CircuitState,
    FallbackProvider,
    RetryProvider,
    build_resilient_provider,
)
from .router import configure_routing, get_provider_for_task

# issue #45: 自动注册内置 provider 工厂 — 注册表模式, 便于按名称扩展新 provider
register_provider("mock", MockProvider)
register_provider("minimax", MinimaxProvider)

__all__ = [
    "LLMProviderProtocol",
    "Message",
    "StreamChunk",
    "ToolCall",
    "ToolResult",
    "MockProvider",
    "MinimaxProvider",
    "MinimaxAPIError",
    "MinimaxAuthError",
    # 注册表 (issue #45)
    "make_provider",
    "register_provider",
    "get_provider",
    "list_providers",
    # 任务路由 (issue #45)
    "configure_routing",
    "get_provider_for_task",
    # 异步 (issue #46)
    "run_in_executor",
    # 韧性层 (重试 / 熔断 / 降级)
    "RetryProvider",
    "CircuitBreakerProvider",
    "CircuitState",
    "CircuitOpenError",
    "FallbackProvider",
    "build_resilient_provider",
]

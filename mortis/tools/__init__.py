"""Mortis tools — 工具系统。

issue #64: ToolAgent 已注册为 ToolProtocol，由 LLM 通过 tool calling 自发调用。
"""

from __future__ import annotations

from .base import ToolProtocol, ToolResult
from .registry import ToolRegistry, make_default_registry
from .vault_tool import VaultReadTool, VaultListTool, VaultWriteTool, VaultExistsTool
from .agent_tool import (
    VaultReadToolAgent,
    VaultSearchToolAgent,
    VaultStatsToolAgent,
    MarkdownRenderToolAgent,
    ClockToolAgent,
)

__all__ = [
    "ToolProtocol",
    "ToolResult",
    "ToolRegistry",
    "make_default_registry",
    "VaultReadTool",
    "VaultListTool",
    "VaultWriteTool",
    "VaultExistsTool",
    # ToolAgent 包装器 (issue #64)
    "VaultReadToolAgent",
    "VaultSearchToolAgent",
    "VaultStatsToolAgent",
    "MarkdownRenderToolAgent",
    "ClockToolAgent",
]

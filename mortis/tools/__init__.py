"""Mortis tools — 工具系统。"""

from __future__ import annotations

from .base import ToolProtocol, ToolResult
from .registry import ToolRegistry, make_default_registry
from .vault_tool import VaultReadTool, VaultListTool, VaultWriteTool, VaultExistsTool

__all__ = [
    "ToolProtocol",
    "ToolResult",
    "ToolRegistry",
    "make_default_registry",
    "VaultReadTool",
    "VaultListTool",
    "VaultWriteTool",
    "VaultExistsTool",
]

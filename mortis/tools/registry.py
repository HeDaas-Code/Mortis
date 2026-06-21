"""Mortis tools registry — 工具注册表。"""

from __future__ import annotations

from typing import Any

from .base import ToolProtocol, ToolResult


class ToolRegistry:
    """工具注册表 — 白名单来源，工具分发器。"""

    def __init__(self) -> None:
        self._tools: dict[str, ToolProtocol] = {}

    def register(self, tool: ToolProtocol) -> None:
        """注册一个工具。"""
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name!r}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolProtocol | None:
        """按名字获取工具。"""
        return self._tools.get(name)

    def names(self) -> list[str]:
        """所有已注册工具的名字。"""
        return sorted(self._tools.keys())

    def execute(self, name: str, kwargs: dict[str, Any]) -> ToolResult:
        """执行工具（不存在返回错误结果）。"""
        tool = self._tools.get(name)
        if not tool:
            return ToolResult.err(name, f"unknown tool: {name!r}")
        try:
            return tool.execute(**kwargs)
        except TypeError as e:
            return ToolResult.err(name, f"invalid arguments: {e}")
        except Exception as e:
            return ToolResult.err(name, str(e))

    def tool_schemas(self) -> list[dict[str, Any]]:
        """生成给 LLM 看的工具 schema 列表。"""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.input_schema,
                },
            }
            for t in self._tools.values()
        ]


# 全局默认注册表生成器（工具实例来自 vault/runtime，需要外部组装）
def make_default_registry(vault: "Vault | None" = None) -> ToolRegistry:
    """生成默认工具注册表。vault 有值时注册 vault 工具。"""
    from mortis.vault import Vault as VaultClass
    registry = ToolRegistry()
    if vault is not None:
        from .vault_tool import VaultReadTool, VaultListTool, VaultWriteTool, VaultExistsTool
        registry.register(VaultReadTool(vault))
        registry.register(VaultListTool(vault))
        registry.register(VaultWriteTool(vault))
        registry.register(VaultExistsTool(vault))
    return registry

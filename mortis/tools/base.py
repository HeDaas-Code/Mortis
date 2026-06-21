"""Mortis tools base — 工具抽象协议与类型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class ToolResult:
    """工具执行结果。"""
    name: str
    success: bool
    content: str
    error: str | None = None

    @classmethod
    def ok(cls, name: str, content: str) -> "ToolResult":
        return cls(name=name, success=True, content=content)

    @classmethod
    def err(cls, name: str, error: str) -> "ToolResult":
        return cls(name=name, success=False, content="", error=error)


class ToolProtocol(Protocol):
    """工具协议。任何实现此接口的类都能注册到 ToolRegistry。"""

    @property
    def name(self) -> str:
        """工具名称（必须是唯一标识符，格式：namespace:action）。"""
        ...

    @property
    def description(self) -> str:
        """工具描述（给 LLM 看的）。"""
        ...

    @property
    def input_schema(self) -> dict[str, Any]:
        """输入参数 schema（JSON Schema）。"""
        ...

    def execute(self, **kwargs: Any) -> ToolResult:
        """执行工具。"""
        ...

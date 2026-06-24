"""Mortis tools base — 工具抽象协议与类型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ToolResult:
    """工具执行结果 (统一类型, issue #88)。

    合并了原两套重复定义:
    - ``mortis.tools.ToolResult`` (ToolProtocol 层): name / content / error + ok/err 工厂
    - ``mortis.toolagent.ToolResult`` (ToolAgent 层): success / data / error

    统一后单一类型同时携带两套字段, 由各层按需使用:
    - ToolProtocol 层 (vault_tool / agent_tool / registry): 用 ok/err 工厂,
      产出 name + content (面向 LLM 的文本), data 留空。
    - ToolAgent 层 (vault_read / vault_search 等): 直接构造 success + data
      (结构化载荷), name/content 留空。

    frozen=True: 不可变 (沿用原 toolagent 层 ToolResult 的 frozen 语义,
    原 tools 层无任何代码 mutate 实例, 冻结不破坏现有行为)。
    """

    name: str = ""
    success: bool = False
    content: str = ""
    error: str | None = None
    data: Any = None

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

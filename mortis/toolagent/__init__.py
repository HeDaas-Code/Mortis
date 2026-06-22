"""Mortis toolagent — 无人格工具执行体层 (issue #25)。

ToolAgent 是**无人格**执行体 — 不调 LLM、不写 vault、不读 seed。
只是把输入 dict 透传给底层 tool 或固定实现,返回 ToolResult。

设计要点:
- 与 mortis.tools 并存 (RFC §13.3 决定): Tool 是 LLM 可调用接口,
  ToolAgent 是无人格执行体,接口面向 router / registry
- 5 个内置 Agent:
  - VaultReadAgent / VaultSearchAgent / VaultStatsAgent (vault 只读)
  - MarkdownRenderAgent (复用 obsidian 解析层,无 vault 权限)
  - ClockAgent (当前时间 + 上次 dream,只读 steiner/)
- ToolRouter 增加工具关键词检测 (读 / 搜索 / 统计 / 解析 / 现在几点)

不在 #25 范围:
- 不实现 ToolAgent 的 LLM 调用 (ToolAgent 是无人格的)
- 不修改 mortis.tools (ToolAgent 只包 ToolProtocol,不重写)
- 不实现完整的 owner 通知通道 (drift 报警只标记 needs_notify)
"""

from __future__ import annotations

from mortis.toolagent.base import (
    ToolAgent,
    ToolAgentProtocol,
    ToolResult,
)
from mortis.toolagent.vault_read import VaultReadAgent
from mortis.toolagent.vault_search import VaultSearchAgent
from mortis.toolagent.vault_stats import VaultStatsAgent
from mortis.toolagent.markdown_render import MarkdownRenderAgent
from mortis.toolagent.clock import ClockAgent
from mortis.toolagent.router import TaskRouter, RouteDecision


__all__ = [
    # base
    "ToolAgent",
    "ToolAgentProtocol",
    "ToolResult",
    # 5 内置 Agent
    "VaultReadAgent",
    "VaultSearchAgent",
    "VaultStatsAgent",
    "MarkdownRenderAgent",
    "ClockAgent",
    # router
    "TaskRouter",
    "RouteDecision",
]  # noqa: F822 — TYPE_CHECKING import for mypy

"""Mortis toolagent — 无人格工具执行体层 (issue #25)。

ToolAgent 是**无人格**执行体 — 不走 seed / identity / 人格 prompt, 不写 vault,
不读 seed。可以调 LLM 做工具性任务 (摘要/分类/语义搜索), 但 LLM 调用
不带人格上下文。

issue #63: 已完成 provider 注入重构:
   - VaultSearchAgent: 新增语义搜索能力
   - VaultStatsAgent: 新增 LLM 分析能力
   - VaultReadAgent: 新增摘要能力

issue #64: 已完成 ToolProtocol 注册:
   - 5 个内置 Agent 已包装为 ToolProtocol
   - 通过 ToolRegistry 注册,由 LLM 通过 tool calling 自发调用
   - TaskRouter 关键词路由已废弃

设计要点:
- 与 mortis.tools 并存 (RFC §13.3 决定): Tool 是 LLM 可调用接口,
  ToolAgent 是无人格执行体,接口面向 router / registry
- 5 个内置 Agent:
  - VaultReadAgent / VaultSearchAgent / VaultStatsAgent (vault 只读 + LLM 能力)
  - MarkdownRenderAgent (复用 obsidian 解析层,无 vault 权限)
  - ClockAgent (当前时间 + 上次 dream,只读 steiner/)
- TaskRouter 已废弃,建议使用 ToolRegistry + LLM tool calling
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

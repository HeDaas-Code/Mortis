"""Mortis toolagent — TaskRouter: 任务路由决策。

issue #64: 关键词路由已废弃。ToolAgent 现已注册为 ToolProtocol,
由 LLM 通过 tool calling 自发调用。

本模块保留用于向后兼容，但建议使用 ToolRegistry 进行工具调用。

原关键词检测逻辑 (已废弃):
    读 / 读取        → VaultReadAgent
    搜索 / 查找       → VaultSearchAgent
    统计 / 计数       → VaultStatsAgent
    解析 / 渲染       → MarkdownRenderAgent
    现在几点 / 当前时间 → ClockAgent
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


# 关键词 → agent_id 映射
TOOL_KEYWORDS: dict[str, str] = {
    # vault:read — 中文
    "读 vault": "vault:read",
    "读取 vault": "vault:read",
    "读文件": "vault:read",
    "读取文件": "vault:read",
    "读一下": "vault:read",
    "读取一下": "vault:read",
    # vault:read — 英文
    "read vault": "vault:read",
    "read file": "vault:read",
    # vault:search — 中文
    "搜索 vault": "vault:search",
    "查找 vault": "vault:search",
    "搜索 growth": "vault:search",
    "搜索": "vault:search",
    "查找": "vault:search",
    # vault:search — 英文
    "search vault": "vault:search",
    "search": "vault:search",
    "find": "vault:search",
    # vault:stats
    "统计 vault": "vault:stats",
    "统计 growth": "vault:stats",
    "统计": "vault:stats",
    "计数": "vault:stats",
    "stats": "vault:stats",
    "count": "vault:stats",
    # markdown:render
    "解析 markdown": "markdown:render",
    "渲染 markdown": "markdown:render",
    "解析 obsidian": "markdown:render",
    "渲染 obsidian": "markdown:render",
    "解析": "markdown:render",
    "渲染": "markdown:render",
    "parse": "markdown:render",
    "render": "markdown:render",
    # clock
    "现在几点": "clock",
    "当前时间": "clock",
    "上次 dream": "clock",
    "逻辑时钟": "clock",
}


@dataclass(frozen=True)
class RouteDecision:
    """路由决策结果。"""
    agent_id: str | None          # None = 走非 ToolAgent 路径
    input: dict[str, Any]         # 喂给 ToolAgent 的 input dict
    reason: str                   # 决策原因(调试/审计)


class TaskRouter:
    """TaskRouter — 把 task 字符串路由到 ToolAgent 或其他路径。

    用法:
        router = TaskRouter()
        decision = router.route("读一下 mortis-growth/identity/x.md")
        if decision.agent_id:
            agent = registry.get(decision.agent_id)
            result = agent.execute(decision.input)
    """

    def __init__(self, keywords: dict[str, str] | None = None) -> None:
        self.keywords = keywords if keywords is not None else dict(TOOL_KEYWORDS)

    def route(self, task: str) -> RouteDecision:
        """路由一个 task 字符串。

        策略: 在 task 里找第一个匹配 keywords 中 key 的 → agent_id = value。
        没匹配 → agent_id = None (走 LLM / sub / 主人格等其他路径)。

        简化处理:输入透传 task 原文(input dict 由调用方按 agent_id 决定具体 schema)。
        """
        task_lower = task.lower()
        # 排序:长 key 优先(避免 "读" 抢 "读取 vault")
        sorted_keys = sorted(self.keywords.keys(), key=len, reverse=True)
        for kw in sorted_keys:
            if kw in task_lower:
                return RouteDecision(
                    agent_id=self.keywords[kw],
                    input={"task": task},
                    reason=f"matched keyword {kw!r}",
                )
        return RouteDecision(
            agent_id=None,
            input={"task": task},
            reason="no tool keyword matched; route to LLM/sub/master",
        )


__all__ = ["TaskRouter", "RouteDecision", "TOOL_KEYWORDS"]

"""Mortis pipeline router — 任务路由：简单任务直接做，复杂任务委派 sub。"""

from __future__ import annotations

from dataclasses import dataclass

from mortis.provider import LLMProviderProtocol, Message
from mortis.runtime import RuntimeContext


@dataclass
class RouteDecision:
    """路由决策。"""
    route: str  # "simple" | "complex"
    reason: str
    should_delegate: bool  # 是否需要派 sub


class TaskRouter:
    """任务路由器 — 决定任务走哪条路径。"""

    def __init__(self, ctx: RuntimeContext) -> None:
        self.ctx = ctx

    def route(self) -> RouteDecision:
        """分析任务，决定路由。"""
        provider = self.ctx.provider
        messages = self.ctx.messages_for_provider()
        messages.append(Message(
            role="user",
            content=(
                f"分析以下任务，决定是否需要派 sub 智能体：\n\n{self.ctx.thread.task}\n\n"
                "判断标准：\n"
                "- 需要查多个 vault 文件 → 派 sub\n"
                "- 需要多步骤执行 → 派 sub\n"
                "- 简单回复性问题 → 自己直接做\n"
                "回复格式（只需一行）：\n"
                "simple: <理由>  或  complex: <理由>"
            ),
        ))
        resp = provider.generate(messages)

        content = resp.content.strip().lower()
        if content.startswith("simple"):
            return RouteDecision(
                route="simple",
                reason=resp.content,
                should_delegate=False,
            )
        return RouteDecision(
            route="complex",
            reason=resp.content,
            should_delegate=True,
        )

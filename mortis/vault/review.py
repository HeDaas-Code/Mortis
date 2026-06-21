"""Mortis vault review — sub 产出审阅门。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ReviewDecision(str, Enum):
    """主人格对 sub 产出的审阅决定。"""
    ADOPT = "adopt"
    DISCARD = "discard"
    MERGE = "merge"
    EDIT = "edit"


@dataclass(frozen=True)
class ReviewResult:
    """审阅结果。"""
    decision: ReviewDecision
    reason: str
    target_rel: str | None = None


class ReviewGate:
    """审阅门 — 主人在 sub 产出合并到正式 vault 前必须决策。"""

    @staticmethod
    def review(content: str, rel_path: str) -> ReviewResult:
        """对 sub 产出做审阅决策。

        当前实现（M1）：根据文件名后缀做粗略判断。
        后续可接 LLM / owner override。
        """
        if rel_path.endswith(".tmp") or "DRAFT" in content[:200]:
            return ReviewResult(
                decision=ReviewDecision.DISCARD,
                reason="标记为草稿或临时文件",
            )
        return ReviewResult(
            decision=ReviewDecision.ADOPT,
            reason="内容看起来是正式产出",
        )
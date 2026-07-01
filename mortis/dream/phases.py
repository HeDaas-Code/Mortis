"""Mortis dream — phase / level 枚举与执行顺序。

issue #22: RFC-001 §三（梦境分级）+ §四 Phase 1-4（浅梦完整 4 phase）。

DreamPhase: 7 阶段流水线 (Light 跑前 4,Medium/Deep 跑后 3)。
DreamLevel: 3 档梦境深度。
"""

from __future__ import annotations

from enum import Enum


class DreamPhase(str, Enum):
    """梦境流水线阶段(RFC-001 §四 + §十 + issue #94)。

    顺序: RECALL → ASSOCIATE → SIMULATE → CRYSTALLIZE → RECONCILE → ERODE → SEED_CHECK → EXPRESSION_DISTILL
    - Light: RECALL → ASSOCIATE → CRYSTALLIZE → RECONCILE → EXPRESSION_DISTILL
      注: issue #22 Light 简化为 RECALL → ASSOCIATE → CRYSTALLIZE → RECONCILE (跳过 SIMULATE);
      issue #94 追加 EXPRESSION_DISTILL (从对话统计提炼表达模式 → tone growth)。
    - Medium: 跑 1-5 (含 RECONCILE)
    - Deep: 跑 1-7 (全跑)
    """

    RECALL = "recall"
    ASSOCIATE = "associate"
    SIMULATE = "simulate"
    CRYSTALLIZE = "crystallize"
    RECONCILE = "reconcile"
    ERODE = "erode"
    SEED_CHECK = "seed_check"
    # issue #94: 表达方式学习 — 从对话统计提炼 tone growth
    EXPRESSION_DISTILL = "expression_distill"


class DreamLevel(str, Enum):
    """梦境分级(RFC-001 §三)。"""

    LIGHT = "light"      # 每日,产出 confidence=0.3 候选
    MEDIUM = "medium"    # 每周
    DEEP = "deep"        # 每月


# 每个 level 跑的 phase 顺序(Light 5 phase,Medium 5 phase,Deep 7 phase)
PHASES_BY_LEVEL: dict[DreamLevel, list[DreamPhase]] = {
    # issue #94: Light 追加 EXPRESSION_DISTILL (从对话统计提炼表达模式 → tone growth)
    DreamLevel.LIGHT: [
        DreamPhase.RECALL,
        DreamPhase.ASSOCIATE,
        DreamPhase.CRYSTALLIZE,
        DreamPhase.RECONCILE,
        DreamPhase.EXPRESSION_DISTILL,
    ],
    DreamLevel.MEDIUM: [
        DreamPhase.RECALL,
        DreamPhase.ASSOCIATE,
        DreamPhase.SIMULATE,
        DreamPhase.CRYSTALLIZE,
        DreamPhase.RECONCILE,
    ],
    DreamLevel.DEEP: [
        DreamPhase.RECALL,
        DreamPhase.ASSOCIATE,
        DreamPhase.SIMULATE,
        DreamPhase.CRYSTALLIZE,
        DreamPhase.RECONCILE,
        DreamPhase.ERODE,
        DreamPhase.SEED_CHECK,
    ],
}
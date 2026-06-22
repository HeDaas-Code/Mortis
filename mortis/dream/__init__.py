"""Mortis dream — 梦境子系统 (RFC-001 §三 + §四 + §十)。

issue #22: LightDreamer(浅梦 4 phase)。

子模块:
- phases: DreamPhase / DreamLevel 枚举 + level→phases 映射
- recall: emotion_weighted_sample 纯函数
- associate: LLM 找多条 session 共同模式
- crystallize: Growth 候选生成 + dimension 推断 + id 自增
- pipeline: DreamPipeline 基类 + DreamResult / PhaseTrace
- light: LightDreamer (浅梦完整实现)

**不在 #22 范围**:#23 MediumDreamer / DeepDreamer / DreamLog / ERODE / SEED_CHECK。
"""

from __future__ import annotations

from mortis.dream.phases import (
    PHASES_BY_LEVEL,
    DreamLevel,
    DreamPhase,
)
from mortis.dream.recall import (
    compute_weight,
    emotion_weighted_sample,
)
from mortis.dream.crystallize import (
    average_emotion,
    infer_dimension,
    make_candidate,
    reset_counter,
)
from mortis.dream.associate import associate
from mortis.dream.pipeline import (
    DreamPipeline,
    DreamResult,
    PhaseTrace,
)
from mortis.dream.light import (
    Conflict,
    LightDreamer,
)


__all__ = [
    # phases
    "PHASES_BY_LEVEL",
    "DreamLevel",
    "DreamPhase",
    # recall
    "compute_weight",
    "emotion_weighted_sample",
    # crystallize
    "average_emotion",
    "infer_dimension",
    "make_candidate",
    "reset_counter",
    # associate
    "associate",
    # pipeline
    "DreamPipeline",
    "DreamResult",
    "PhaseTrace",
    # light
    "Conflict",
    "LightDreamer",
]
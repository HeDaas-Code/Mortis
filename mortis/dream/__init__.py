"""Mortis dream — 梦境子系统 (RFC-001 §三 + §四 + §十)。

issue #22 (#22 PR #30): LightDreamer(浅梦 4 phase) — 已落地
issue #23 (当前): MediumDreamer / DeepDreamer / 侵蚀 / seed-check / dream-log

子模块:
- phases: DreamPhase / DreamLevel enum + level→phases 映射
- recall: emotion_weighted_sample 纯函数
- associate: LLM 找多条 session 共同模式
- crystallize: Growth 候选生成 + dimension 推断 + id 自增
- pipeline: DreamPipeline 基类 + DreamResult / PhaseTrace
- light: LightDreamer (浅梦 4 phase)
- medium: MediumDreamer (中梦 5 phase + 置信度提升 + 冲突处理)
- deep: DeepDreamer (深梦 7 phase + erode + seed_check)
- erode: confidence 衰减 + archive
- seed_check: drift 计算 (LLM 自评)
- dream_log: 梦境日志写盘
- triggers: Medium/Deep 触发条件

**不在范围**:#26 逻辑时钟 (与 Light/Medium/Deep 集成)。
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
from mortis.dream.medium import MediumDreamer
from mortis.dream.deep import DeepDreamer
from mortis.dream.erode import (
    THIRTY_DAYS_DAMPING,
    NINETY_DAYS_DAMPING,
    ARCHIVE_THRESHOLD,
    erode_growths,
    days_since_validated,
)
from mortis.dream.seed_check import (
    DEFAULT_DRIFT_THRESHOLD,
    PER_DIM_ALERT_THRESHOLD,
    DriftReport,
    seed_check,
)
from mortis.dream.dream_log import (
    DREAM_LOG_DIR,
    DreamLog,
    dream_log_rel,
    write_dream_log,
)
from mortis.dream.triggers import (
    MEDIUM_INTERVAL_DAYS,
    DEEP_INTERVAL_DAYS,
    PENDING_REFLECTIONS_THRESHOLD,
    TriggerDecision,
    should_medium_dream,
    should_deep_dream,
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
    # medium
    "MediumDreamer",
    # deep
    "DeepDreamer",
    # erode
    "THIRTY_DAYS_DAMPING",
    "NINETY_DAYS_DAMPING",
    "ARCHIVE_THRESHOLD",
    "erode_growths",
    "days_since_validated",
    # seed_check
    "DEFAULT_DRIFT_THRESHOLD",
    "PER_DIM_ALERT_THRESHOLD",
    "DriftReport",
    "seed_check",
    # dream_log
    "DREAM_LOG_DIR",
    "DreamLog",
    "dream_log_rel",
    "write_dream_log",
    # triggers
    "MEDIUM_INTERVAL_DAYS",
    "DEEP_INTERVAL_DAYS",
    "PENDING_REFLECTIONS_THRESHOLD",
    "TriggerDecision",
    "should_medium_dream",
    "should_deep_dream",
]

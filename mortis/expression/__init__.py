"""Mortis expression — 表达方式学习模块 (issue #94)。

从对话中提取说话风格, 让 tone 随交互演化:

第一步: 对话统计记录 (``stats.py``)
    每次 ChatService.send/stream 后, 提取 user / mortis 双侧的句长 / 标点 /
    语气词 / 高频词统计, 写入 ``vault/mortis-journal/expression-stats/<date>.json``。

第二步: Dream 提炼表达模式 (``distill.py``)
    Dream pipeline 的 EXPRESSION_DISTILL phase 读近期 stats, 调 LLM 提炼表达
    模式描述, 产出写入 ``mortis-growth/tone/expression-<date>.md``。

第三步: System prompt 注入 (``runtime.context``)
    ``messages_for_provider`` 在 seed tone 之后注入 ``## Expression Patterns (learned)``
    段, 让 Mortis 回复风格随用户偏好演化。
"""

from __future__ import annotations

from .stats import (
    SideStats,
    TurnStats,
    extract_side_stats,
    build_turn_stats,
    record_turn_stats,
    load_recent_stats,
    format_stats_for_prompt,
)
from .distill import (
    distill_expression_patterns,
    expression_growth_id,
    is_expression_growth,
    EXPRESSION_ID_PREFIX,
    DEFAULT_DISTILL_DAYS,
)

__all__ = [
    "SideStats",
    "TurnStats",
    "extract_side_stats",
    "build_turn_stats",
    "record_turn_stats",
    "load_recent_stats",
    "format_stats_for_prompt",
    "distill_expression_patterns",
    "expression_growth_id",
    "is_expression_growth",
    "EXPRESSION_ID_PREFIX",
    "DEFAULT_DISTILL_DAYS",
]

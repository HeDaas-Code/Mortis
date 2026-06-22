"""Mortis growth — 长期记忆条目（人格生长）。

issue #18: Growth 数据模型。Phase 1 只建数据形状 + 读写入口，
不实现写入逻辑（reflect/dream/owner edit 写 growth 是 #21-#24 的事）。

字段对应 RFC-001 §七 frontmatter + body。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from mortis.seed.schema import SEVEN_DIMENSIONS


class Dimension(str, Enum):
    """七维度（人格生长的分类轴）。

    值必须与 mortis.seed.schema.SEVEN_DIMENSIONS 完全一致 —
    单测保证不漂移（issue #18 prompt 约束 #4）。
    """

    IDENTITY = "identity"
    VALUES = "values"
    TONE = "tone"
    AGENCY = "agency"
    RELATIONS = "relations"
    CREATIVITY = "creativity"
    MORTALITY = "mortality"


class DreamLevel(str, Enum):
    """梦境分级（RFC-001 §三）。

    None = REFLECT 写（不是 dream 产物）。
    """

    LIGHT = "light"
    MEDIUM = "medium"
    DEEP = "deep"


@dataclass(frozen=True)
class Growth:
    """长期记忆条目（人格生长的一笔）。

    frozen: 不可变 — 任何更新走 dataclasses.replace() 返回新对象
    （RFC §八 "growth 可被推翻" = 用新对象替换，不改原对象）。

    body: 纯文本。Obsidian 语法解析（双链/注释/折叠）是 #19 的事。
    """

    id: str
    dimension: Dimension
    confidence: float  # 0.0 ~ 1.0
    created_at: str  # ISO8601
    last_validated: str  # ISO8601
    source_sessions: tuple[str, ...]
    dream_level: DreamLevel | None  # None = REFLECT 写
    emotional_valence: float  # -1.0 ~ 1.0
    emotional_arousal: float  # 0.0 ~ 1.0
    tags: tuple[str, ...]
    body: str


def assert_dimension_consistency() -> None:
    """单测用 — 保证 Dimension enum 与 SEVEN_DIMENSIONS 不漂移。"""
    assert tuple(d.value for d in Dimension) == SEVEN_DIMENSIONS, (
        f"Dimension enum drifted from SEVEN_DIMENSIONS: "
        f"{tuple(d.value for d in Dimension)} != {SEVEN_DIMENSIONS}"
    )

"""Test growth model — Growth dataclass + Dimension/DreamLevel enum。

issue #18: Growth 数据模型测试。
- frozen 行为（不可改）
- dataclasses.replace 更新（RFC §八 "growth 可被推翻"）
- Dimension 与 SEVEN_DIMENSIONS 一致性
"""
from __future__ import annotations

import dataclasses

import pytest

from mortis.growth import (
    Dimension,
    DreamLevel,
    Growth,
    assert_dimension_consistency,
)
from mortis.seed.schema import SEVEN_DIMENSIONS


def _make_growth(**overrides) -> Growth:
    """构造一个合法的 Growth 实例，可覆盖任意字段。"""
    defaults = dict(
        id="growth-2026-06-21-001",
        dimension=Dimension.TONE,
        confidence=0.6,
        created_at="2026-06-21T23:30:00+00:00",
        last_validated="2026-07-01T23:30:00+00:00",
        source_sessions=("session-abc", "session-def"),
        dream_level=DreamLevel.MEDIUM,
        emotional_valence=0.7,
        emotional_arousal=0.5,
        tags=("沟通策略", "已验证"),
        body="技术讨论中先给结论再解释，比先解释再给结论更有效。",
    )
    defaults.update(overrides)
    return Growth(**defaults)


class TestGrowthDataclass:
    """Growth frozen dataclass 基础行为。"""

    def test_construct_with_all_fields(self) -> None:
        """所有字段可正常赋值。"""
        g = _make_growth()
        assert g.id == "growth-2026-06-21-001"
        assert g.dimension == Dimension.TONE
        assert g.confidence == 0.6
        assert g.source_sessions == ("session-abc", "session-def")
        assert g.dream_level == DreamLevel.MEDIUM
        assert g.emotional_valence == 0.7
        assert g.emotional_arousal == 0.5
        assert g.tags == ("沟通策略", "已验证")
        assert "技术讨论" in g.body

    def test_frozen_rejects_mutation(self) -> None:
        """frozen dataclass 不允许原地修改字段。"""
        g = _make_growth()
        with pytest.raises(dataclasses.FrozenInstanceError):
            g.confidence = 0.9  # type: ignore[misc]

    def test_dataclasses_replace_updates_confidence(self) -> None:
        """dataclasses.replace() 更新字段返回新对象，原对象不变（RFC §八）。"""
        g = _make_growth(confidence=0.6)
        g2 = dataclasses.replace(g, confidence=0.9, last_validated="2026-07-15T00:00:00+00:00")
        # 原对象不变
        assert g.confidence == 0.6
        assert g.last_validated == "2026-07-01T23:30:00+00:00"
        # 新对象已更新
        assert g2.confidence == 0.9
        assert g2.last_validated == "2026-07-15T00:00:00+00:00"
        # 其他字段保持
        assert g2.id == g.id
        assert g2.dimension == g.dimension

    def test_dream_level_can_be_none(self) -> None:
        """REFLECT 写时 dream_level 为 None（issue body 约定）。"""
        g = _make_growth(dream_level=None)
        assert g.dream_level is None

    def test_tuple_fields_are_immutable(self) -> None:
        """tags / source_sessions 是 tuple — 不可原地改。"""
        g = _make_growth()
        with pytest.raises(TypeError):
            g.tags[0] = "其他"  # type: ignore[index]


class TestDimensionEnum:
    """Dimension 枚举 + SEVEN_DIMENSIONS 一致性。"""

    def test_seven_dimensions(self) -> None:
        """必须 7 个维度。"""
        assert len(Dimension) == 7

    def test_dimension_values_match_seven_dimensions(self) -> None:
        """Dimension 值与 SEVEN_DIMENSIONS 完全一致（顺序也一致）。"""
        assert tuple(d.value for d in Dimension) == SEVEN_DIMENSIONS

    def test_assert_dimension_consistency_passes(self) -> None:
        """assert_dimension_consistency() 在当前状态不抛错。"""
        assert_dimension_consistency()  # 不抛错 = 通过

    def test_each_dimension_is_string_enum(self) -> None:
        """Dimension 继承 str — 可直接当字符串用。"""
        assert Dimension.IDENTITY == "identity"
        assert Dimension.MORTALITY.value == "mortality"


class TestDreamLevelEnum:
    """DreamLevel 枚举（含 None）。"""

    def test_three_levels(self) -> None:
        """LIGHT / MEDIUM / DEEP 三个梦境级。"""
        assert {l.value for l in DreamLevel} == {"light", "medium", "deep"}

    def test_dream_level_none_via_growth_field(self) -> None:
        """dream_level 字段类型允许 None（REFLECT 写时）。"""
        g = _make_growth(dream_level=None)
        assert g.dream_level is None

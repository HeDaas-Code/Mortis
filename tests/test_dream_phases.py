"""Mortis dream — phases 测试。issue #22 验收 #1。"""

from __future__ import annotations

from mortis.dream.phases import (
    PHASES_BY_LEVEL,
    DreamLevel,
    DreamPhase,
)


class TestDreamPhase:
    """DreamPhase 枚举 + 顺序。"""

    def test_all_phases_exist(self):
        # issue #94: 追加 expression_distill (8 phase)
        assert {p.value for p in DreamPhase} == {
            "recall", "associate", "simulate", "crystallize",
            "reconcile", "erode", "seed_check", "expression_distill",
        }

    def test_phase_order_matches_rfc(self):
        # RFC §四: RECALL → ASSOCIATE → SIMULATE → CRYSTALLIZE → RECONCILE → ERODE → SEED_CHECK
        # issue #94: 追加 EXPRESSION_DISTILL (表达方式学习, Light level 专属)
        order = [p.value for p in DreamPhase]
        assert order == [
            "recall", "associate", "simulate", "crystallize",
            "reconcile", "erode", "seed_check", "expression_distill",
        ]


class TestDreamLevel:
    def test_three_levels(self):
        assert {l.value for l in DreamLevel} == {"light", "medium", "deep"}


class TestPhasesByLevel:
    """level → phase 顺序映射。"""

    def test_light_runs_five_phases(self):
        # issue #94: Light 追加 EXPRESSION_DISTILL (5 phase)
        phases = PHASES_BY_LEVEL[DreamLevel.LIGHT]
        assert [p.value for p in phases] == [
            "recall", "associate", "crystallize", "reconcile", "expression_distill",
        ]

    def test_medium_runs_five_phases(self):
        phases = PHASES_BY_LEVEL[DreamLevel.MEDIUM]
        assert len(phases) == 5
        assert "simulate" in [p.value for p in phases]

    def test_deep_runs_all_seven(self):
        phases = PHASES_BY_LEVEL[DreamLevel.DEEP]
        assert len(phases) == 7
        assert "erode" in [p.value for p in phases]
        assert "seed_check" in [p.value for p in phases]

    def test_all_levels_covered(self):
        for level in DreamLevel:
            assert level in PHASES_BY_LEVEL
            assert len(PHASES_BY_LEVEL[level]) >= 4
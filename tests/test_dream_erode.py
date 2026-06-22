"""Test mortis.dream.erode — confidence 衰减 + archive。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from mortis.dream.erode import (
    ARCHIVE_THRESHOLD,
    NINETY_DAYS_DAMPING,
    THIRTY_DAYS_DAMPING,
    days_since_validated,
    erode_growths,
)
from mortis.growth.model import Dimension, DreamLevel, Growth


def _make_growth(confidence: float, days_ago: int, id: str = "g") -> Growth:
    now = datetime.now(tz=timezone.utc)
    last_validated = (now - timedelta(days=days_ago)).isoformat()
    return Growth(
        id=f"{id}-{days_ago}",
        dimension=Dimension.IDENTITY,
        confidence=confidence,
        created_at=last_validated,
        last_validated=last_validated,
        source_sessions=(),
        dream_level=DreamLevel.LIGHT,
        emotional_valence=0.0,
        emotional_arousal=0.0,
        tags=(),
        body="test",
    )


class TestDaysSinceValidated:
    def test_zero_days(self):
        g = _make_growth(0.5, 0)
        d = days_since_validated(g)
        assert d < 1.0

    def test_thirty_days(self):
        g = _make_growth(0.5, 30)
        d = days_since_validated(g)
        assert 29.0 <= d <= 31.0


class TestErodeDecay:
    def test_no_decay_within_30_days(self):
        g = _make_growth(0.5, 10)
        survived, archived = erode_growths([g])
        assert len(survived) == 1
        assert survived[0].confidence == 0.5  # 不衰减
        assert archived == []

    def test_decay_at_30_days(self):
        g = _make_growth(1.0, 35)
        survived, archived = erode_growths([g])
        assert len(survived) == 1
        assert abs(survived[0].confidence - 0.8) < 0.01  # × 0.8

    def test_decay_at_90_days(self):
        g = _make_growth(1.0, 100)
        survived, archived = erode_growths([g])
        assert len(survived) == 1
        assert abs(survived[0].confidence - 0.5) < 0.01  # × 0.5

    def test_archive_below_threshold(self):
        g = _make_growth(0.15, 100)  # 0.15 × 0.5 = 0.075 < 0.1
        survived, archived = erode_growths([g])
        assert survived == []
        assert len(archived) == 1
        assert archived[0].confidence == pytest.approx(0.075, abs=0.01)

    def test_boundary_at_threshold(self):
        """confidence == threshold 时不算 archive (用 < 不是 <=)。"""
        g = _make_growth(0.2, 100)  # 0.2 × 0.5 = 0.1 == threshold
        survived, archived = erode_growths([g])
        assert len(survived) == 1
        assert archived == []

    def test_constants(self):
        assert THIRTY_DAYS_DAMPING == 0.8
        assert NINETY_DAYS_DAMPING == 0.5
        assert ARCHIVE_THRESHOLD == 0.1

    def test_empty_input(self):
        survived, archived = erode_growths([])
        assert survived == []
        assert archived == []

    def test_mixed(self):
        gs = [
            _make_growth(0.8, 5),    # 不衰减
            _make_growth(0.8, 50),   # × 0.8
            _make_growth(0.5, 100),  # × 0.5 = 0.25 (留)
            _make_growth(0.1, 100),  # × 0.5 = 0.05 (archive)
        ]
        survived, archived = erode_growths(gs)
        assert len(survived) == 3
        assert len(archived) == 1

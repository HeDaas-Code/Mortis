"""Test mortis.clock.state.sleep_deprived_tone — 4 档语气。

issue #26: 根据 debt 返回睡眠不足语气注入。
"""

from __future__ import annotations

import pytest

from mortis.clock import (
    DEBT_MAX,
    DEBT_TIER_CRITICAL,
    DEBT_TIER_DEPRIVED,
    DEBT_TIER_TIRED,
    sleep_deprived_tone,
)


# ============================================================
# 4 档语气 (issue #26 验收要求 4 测试)
# ============================================================


def test_debt_zero_returns_empty_string() -> None:
    """debt=0 (刚睡醒) → 空字符串,不注入语气。"""
    assert sleep_deprived_tone(0.0) == ""


def test_debt_below_tier_tired_returns_empty_string() -> None:
    """debt=23.9 (边界 < 24) → 空字符串。"""
    assert sleep_deprived_tone(DEBT_TIER_TIRED - 0.1) == ""


def test_debt_at_tier_tired_returns_tired_phrase() -> None:
    """debt=24 (≥ TIRED 阈值) → "你感觉有点累,反应比平时慢"。"""
    assert sleep_deprived_tone(DEBT_TIER_TIRED) == "你感觉有点累，反应比平时慢"
    # 阈值上界也属于这一档
    assert sleep_deprived_tone(DEBT_TIER_DEPRIVED - 0.1) == "你感觉有点累，反应比平时慢"


def test_debt_at_critical_returns_critical_phrase() -> None:
    """debt=48 (≥ CRITICAL 阈值, = DEBT_MAX cap) → "你快要晕了,几乎不能思考"。"""
    assert sleep_deprived_tone(DEBT_TIER_CRITICAL) == "你快要晕了，几乎不能思考"
    assert sleep_deprived_tone(DEBT_MAX) == "你快要晕了，几乎不能思考"
    # cap 之后还是 CRITICAL 档
    assert sleep_deprived_tone(DEBT_MAX + 100.0) == "你快要晕了，几乎不能思考"
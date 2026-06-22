"""Test mortis.reflect.triggers — REFLECT 触发条件。

issue #21 acceptance:
- 条件 1: owner_said_goodnight → True (无条件)
- 条件 2: session_count_today >= 3 AND 距上次 REFLECT > 4h
- 条件 3 不实现
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from mortis.reflect.triggers import (
    MIN_HOURS_BETWEEN,
    SESSION_THRESHOLD,
    hours_since,
    should_reflect,
)


# 基准时间:固定用 2026-06-22 14:00 UTC,避免 now() 漂移
_BASE = datetime(2026, 6, 22, 14, 0, tzinfo=timezone.utc)


class TestShouldReflectCondition1:
    """条件 1: owner 主动说晚安 → 无条件触发。"""

    def test_owner_goodnight_triggers(self) -> None:
        """owner_said_goodnight=True → True(无视其他参数)。"""
        assert should_reflect(
            now=_BASE,
            last_reflection=None,
            session_count_today=0,
            owner_said_goodnight=True,
        ) is True

    def test_owner_goodnight_overrides_low_sessions(self) -> None:
        """即使今天 0 session,owner 收工也触发。"""
        assert should_reflect(
            now=_BASE,
            last_reflection=_BASE,
            session_count_today=0,
            owner_said_goodnight=True,
        ) is True


class TestShouldReflectCondition2:
    """条件 2: 阈值 + 间隔。"""

    def test_below_threshold_no_trigger(self) -> None:
        """今天 2 个 session < 阈值 3 → False。"""
        assert should_reflect(
            now=_BASE,
            last_reflection=None,
            session_count_today=SESSION_THRESHOLD - 1,
            owner_said_goodnight=False,
        ) is False

    def test_at_threshold_no_last_reflection_triggers(self) -> None:
        """达到阈值 + 从未反思过 → True。"""
        assert should_reflect(
            now=_BASE,
            last_reflection=None,
            session_count_today=SESSION_THRESHOLD,
            owner_said_goodnight=False,
        ) is True

    def test_at_threshold_recent_reflection_blocks(self) -> None:
        """达到阈值 + 距上次 2h(< 4h) → False。"""
        last = _BASE - timedelta(hours=2)
        assert should_reflect(
            now=_BASE,
            last_reflection=last,
            session_count_today=SESSION_THRESHOLD,
            owner_said_goodnight=False,
        ) is False

    def test_at_threshold_after_interval_triggers(self) -> None:
        """达到阈值 + 距上次 5h(> 4h) → True。"""
        last = _BASE - timedelta(hours=5)
        assert should_reflect(
            now=_BASE,
            last_reflection=last,
            session_count_today=SESSION_THRESHOLD,
            owner_said_goodnight=False,
        ) is True

    def test_exactly_at_interval_boundary_no_trigger(self) -> None:
        """边界: 距上次恰好 4h → False(>, 不是 >=)。"""
        last = _BASE - timedelta(hours=MIN_HOURS_BETWEEN)
        assert should_reflect(
            now=_BASE,
            last_reflection=last,
            session_count_today=SESSION_THRESHOLD,
            owner_said_goodnight=False,
        ) is False


class TestShouldReflectDefaults:
    """默认 / 边界。"""

    def test_no_trigger_when_all_conditions_clear(self) -> None:
        """全清状态 → False。"""
        assert should_reflect(
            now=_BASE,
            last_reflection=None,
            session_count_today=0,
            owner_said_goodnight=False,
        ) is False

    def test_high_session_count_below_threshold_no_trigger(self) -> None:
        """session_count 接近但未到阈值 → False。"""
        assert should_reflect(
            now=_BASE,
            last_reflection=None,
            session_count_today=2,
            owner_said_goodnight=False,
        ) is False


class TestHoursSince:
    """hours_since 辅助函数。"""

    def test_hours_since_basic(self) -> None:
        a = datetime(2026, 6, 22, 10, 0, tzinfo=timezone.utc)
        b = datetime(2026, 6, 22, 14, 0, tzinfo=timezone.utc)
        assert hours_since(a, b) == 4.0

    def test_hours_since_fractional(self) -> None:
        a = datetime(2026, 6, 22, 10, 0, tzinfo=timezone.utc)
        b = datetime(2026, 6, 22, 10, 30, tzinfo=timezone.utc)
        assert hours_since(a, b) == 0.5

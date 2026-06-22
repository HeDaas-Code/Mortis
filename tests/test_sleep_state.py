"""Test mortis.clock.state — SleepState + debt 累积/衰减 + 阈值常量。

issue #26: 8 测试。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from mortis.clock import (
    DEBT_MAX,
    DEBT_TIER_CRITICAL,
    DEBT_TIER_DEPRIVED,
    DEBT_TIER_TIRED,
    SleepState,
    update_sleep_state,
)


@pytest.fixture
def base_now() -> datetime:
    return datetime(2026, 6, 22, 10, 0, tzinfo=timezone.utc)


# ============================================================
# fresh() 初始值
# ============================================================


def test_fresh_initial_state(base_now: datetime) -> None:
    """fresh(now): wake_since=now, hours_awake=0, debt=0。"""
    s = SleepState.fresh(base_now)
    assert s.wake_since == base_now
    assert s.hours_awake == 0.0
    assert s.debt == 0.0


# ============================================================
# awake 累积 (slept=False)
# ============================================================


def test_update_awake_accumulates_hours_and_debt(base_now: datetime) -> None:
    """update_sleep_state(slept=False) 累积 hours_awake + debt 同步增长。"""
    s0 = SleepState.fresh(base_now)
    now = base_now + timedelta(hours=4)
    s1 = update_sleep_state(s0, now, slept=False)
    assert s1.hours_awake == pytest.approx(4.0)
    assert s1.debt == pytest.approx(4.0)
    assert s1.wake_since == base_now  # 未睡,wake_since 不变


def test_update_awake_multiple_calls_accumulates(base_now: datetime) -> None:
    """连续 awake tick: hours_awake 累积(wake_since 不变,从单点持续累加)。"""
    s = SleepState.fresh(base_now)  # wake_since=base, hours=0
    s = update_sleep_state(s, base_now + timedelta(hours=2), slept=False)
    # delta from base = 2h → hours = 0+2 = 2
    assert s.hours_awake == pytest.approx(2.0)
    assert s.debt == pytest.approx(2.0)
    s = update_sleep_state(s, base_now + timedelta(hours=5), slept=False)
    # delta from base (wake_since 不变) = 5h → hours = 2+5 = 7
    assert s.hours_awake == pytest.approx(7.0)
    assert s.debt == pytest.approx(7.0)
    # wake_since 不动(测试 sleep_state 字段语义)
    assert s.wake_since == base_now


# ============================================================
# slept=True 重置/衰减
# ============================================================


def test_update_slept_resets_hours_awake(base_now: datetime) -> None:
    """slept=True → hours_awake=0。"""
    s0 = SleepState.fresh(base_now)
    s1 = update_sleep_state(s0, base_now + timedelta(hours=8), slept=False)
    s2 = update_sleep_state(s1, base_now + timedelta(hours=10), slept=True)
    assert s2.hours_awake == 0.0


def test_update_slept_decays_debt(base_now: datetime) -> None:
    """slept=True → debt × 0.5。"""
    s0 = SleepState.fresh(base_now)
    s1 = update_sleep_state(s0, base_now + timedelta(hours=20), slept=False)
    assert s1.debt == pytest.approx(20.0)
    s2 = update_sleep_state(s1, base_now + timedelta(hours=22), slept=True)
    assert s2.debt == pytest.approx(10.0)


# ============================================================
# debt 上限
# ============================================================


def test_debt_caps_at_max(base_now: datetime) -> None:
    """debt 不能超过 DEBT_MAX=48。"""
    s0 = SleepState.fresh(base_now)
    s1 = update_sleep_state(s0, base_now + timedelta(hours=100), slept=False)
    assert s1.debt == pytest.approx(DEBT_MAX)
    assert s1.hours_awake == pytest.approx(100.0)  # hours_awake 不 cap


# ============================================================
# 阈值常量 sanity
# ============================================================


def test_debt_tier_constants_sanity() -> None:
    """DEBT_TIER_TIRED < DEPRIVED < CRITICAL ≤ DEBT_MAX。"""
    assert DEBT_TIER_TIRED < DEBT_TIER_DEPRIVED
    assert DEBT_TIER_DEPRIVED < DEBT_TIER_CRITICAL
    assert DEBT_TIER_CRITICAL <= DEBT_MAX


# ============================================================
# slept=True wake_since 重置
# ============================================================


def test_slept_resets_wake_since(base_now: datetime) -> None:
    """slept=True → wake_since 重置为 now 参数。"""
    s0 = SleepState.fresh(base_now)
    wake_time = base_now + timedelta(hours=8)
    s1 = update_sleep_state(s0, wake_time, slept=True)
    assert s1.wake_since == wake_time
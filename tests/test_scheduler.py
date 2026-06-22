"""Test mortis.clock.schedule — Scheduler + TickResult + detect_goodnight。

issue #26: REFLECT/DREAM 触发 4 场景 + 参数化 inactivity + sleep_state 集成。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from mortis.clock import (
    Scheduler,
    SleepState,
    update_sleep_state,
)


def _now(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 6, 22, hour, minute, tzinfo=timezone.utc)


# ============================================================
# Scheduler.tick 4 场景 (issue #26 验收要求)
# ============================================================


def test_goodnight_triggers_reflect_immediately() -> None:
    """owner 说"晚安" → REFLECT 立即触发 (无论时段)。"""
    sched = Scheduler()
    # AWAKE 时段 (10:00) + goodnight
    r = sched.tick(owner_message="晚安", now=_now(10, 0))
    assert r.should_trigger_reflect is True
    assert r.should_trigger_dream_light is False
    assert r.should_trigger_dream_deep is False


def test_reflect_period_inactive_triggers_reflect() -> None:
    """REFLECT 时段 (22:30) + owner 不活跃 ≥ 30min → REFLECT。"""
    sched = Scheduler()
    now = _now(22, 30)
    last_active = now - timedelta(minutes=45)
    r = sched.tick(owner_last_active=last_active, now=now)
    assert r.state.value == "reflect"
    assert r.should_trigger_reflect is True
    assert "REFLECT" in r.reason


def test_reflect_period_active_no_trigger() -> None:
    """REFLECT 时段 + owner 刚刚活跃 (< 30min) → 不触发。"""
    sched = Scheduler()
    now = _now(22, 30)
    last_active = now - timedelta(minutes=5)
    r = sched.tick(owner_last_active=last_active, now=now)
    assert r.state.value == "reflect"
    assert r.should_trigger_reflect is False


def test_dream_light_period_triggers_light_dream() -> None:
    """DREAM_LIGHT 时段 (23:30) + 无 goodnight → dream_light trigger。"""
    sched = Scheduler()
    r = sched.tick(now=_now(23, 30))
    assert r.state.value == "dream_light"
    assert r.should_trigger_dream_light is True
    assert r.should_trigger_reflect is False
    assert r.should_trigger_dream_deep is False


def test_dream_deep_period_triggers_deep_dream() -> None:
    """DREAM_DEEP 时段 (03:30) → dream_deep trigger。"""
    sched = Scheduler()
    r = sched.tick(now=_now(3, 30))
    assert r.state.value == "dream_deep"
    assert r.should_trigger_dream_deep is True
    assert r.should_trigger_dream_light is False
    assert r.should_trigger_reflect is False


def test_awake_period_no_triggers() -> None:
    """AWAKE 时段 (14:00) → 无任何 trigger。"""
    sched = Scheduler()
    r = sched.tick(now=_now(14, 0))
    assert r.state.value == "awake"
    assert r.should_trigger_reflect is False
    assert r.should_trigger_dream_light is False
    assert r.should_trigger_dream_deep is False


# ============================================================
# sleep_state 集成
# ============================================================


def test_tick_includes_sleep_deprived_tone() -> None:
    """sleep_state 传入 → TickResult.sleep_deprived_tone 注入。"""
    sched = Scheduler()
    # 累积 30h debt → 触发 tired 语气
    base = _now(6, 0)
    sleep_state = update_sleep_state(
        SleepState.fresh(base), base + timedelta(hours=30), slept=False
    )
    r = sched.tick(now=base + timedelta(hours=30), sleep_state=sleep_state)
    assert r.sleep_deprived_tone != ""


# ============================================================
# inactivity_minutes 参数化
# ============================================================


def test_custom_inactivity_minutes_changes_threshold() -> None:
    """inactivity_minutes=5 → 5 分钟不活跃即触发 REFLECT。"""
    sched = Scheduler(inactivity_minutes=5)
    now = _now(22, 30)
    last_active = now - timedelta(minutes=10)
    r = sched.tick(owner_last_active=last_active, now=now)
    assert r.should_trigger_reflect is True


# ============================================================
# 时区 (issue #37)
# ============================================================


def test_scheduler_timezone_shift() -> None:
    """tz=Asia/Shanghai(+08) → 22:00 CST = 14:00 UTC → REFLECT 时段。

    默认 tz=UTC 时 14:00 是 AWAKE, 加 tz 后应是 REFLECT。
    """
    from datetime import timezone, timedelta as _td

    cst = timezone(_td(hours=8))
    sched = Scheduler(tz=cst)
    # 14:00 UTC = 22:00 CST → REFLECT
    now_utc = datetime(2026, 6, 22, 14, 0, tzinfo=timezone.utc)
    r = sched.tick(now=now_utc)
    assert r.state.value == "reflect"
    assert r.should_trigger_reflect is True


def test_logical_clock_timezone() -> None:
    """LogicalClock(tz=CST) — 同一 UTC 时刻, 不同时区 → 不同时段。"""
    from datetime import timezone, timedelta as _td

    from mortis.clock.logical import LogicalClock

    cst = timezone(_td(hours=8))
    utc_clock = LogicalClock()
    cst_clock = LogicalClock(tz=cst)
    # 14:00 UTC
    now_utc = datetime(2026, 6, 22, 14, 0, tzinfo=timezone.utc)
    # UTC clock: 14:00 → AWAKE
    assert utc_clock.state(now_utc).value == "awake"
    # CST clock: 14:00 UTC = 22:00 CST → REFLECT
    assert cst_clock.state(now_utc).value == "reflect"
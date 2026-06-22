"""Mortis clock — SleepState + 睡眠不足表现。

issue #26: 跟踪清醒时长 + 累积 debt + 衰减。

设计要点:
- wake_since: 上次"睡醒"时间(默认 now)
- hours_awake: 累积清醒小时
- debt: 睡眠债务 (> 24h 触发"有点累"语气)
- update_sleep_state: 每次 awake / 睡了 调用
- sleep_deprived_tone: 4 档语气
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone


# 阈值常量 (小时)
DEBT_TIER_TIRED = 24.0        # debt > 24: "有点累"
DEBT_TIER_DEPRIVED = 36.0      # debt > 36: "明显睡眠不足"
DEBT_TIER_CRITICAL = 48.0      # debt > 48: "快要晕了"
DEBT_MAX = 48.0                # debt cap
DEBT_DECAY = 0.5               # 睡了 debt × 0.5


@dataclass(frozen=True)
class SleepState:
    """睡眠状态 — 跟踪清醒时长与债务。"""
    wake_since: datetime      # 上次"睡醒"
    hours_awake: float        # 累积清醒
    debt: float               # 债务

    @classmethod
    def fresh(cls, now: datetime | None = None) -> "SleepState":
        """新一天的睡眠状态 (刚睡醒)。"""
        ts = now or datetime.now(tz=timezone.utc)
        return cls(wake_since=ts, hours_awake=0.0, debt=0.0)


def update_sleep_state(
    state: SleepState,
    now: datetime,
    *,
    slept: bool,
) -> SleepState:
    """更新睡眠状态。

    Args:
        state: 当前 SleepState。
        now: 当前时间。
        slept: True = owner 刚睡过(从 REFLECT/DREAM 醒来),
               False = owner 还在 awake 时段累积时长。

    Returns:
        新 SleepState (frozen, replace)。
    """
    if slept:
        # 睡了 → reset hours_awake, debt 衰减
        return replace(
            state,
            wake_since=now,
            hours_awake=0.0,
            debt=min(DEBT_MAX, state.debt * DEBT_DECAY),
        )
    # awake 时段 → 累积 hours_awake, debt 同步增。
    # wake_since 保持不变:hours_awake 是"距上次醒来的总时长"快照,
    # 任何时刻调用 update 都能从 wake_since 单点重算增量。
    delta_h = (now - state.wake_since).total_seconds() / 3600.0
    new_hours = state.hours_awake + max(0.0, delta_h)
    new_debt = min(DEBT_MAX, state.debt + max(0.0, delta_h))
    return replace(
        state,
        hours_awake=new_hours,
        debt=new_debt,
    )


def sleep_deprived_tone(debt: float) -> str:
    """根据 debt 返回睡眠不足语气注入。

    tier:
        < 24:  "" (无注入)
        24-36: "你感觉有点累，反应比平时慢"
        36-48: "你明显睡眠不足，话语简短"
        >= 48: "你快要晕了，几乎不能思考"
    """
    if debt >= DEBT_TIER_CRITICAL:
        return "你快要晕了，几乎不能思考"
    if debt >= DEBT_TIER_DEPRIVED:
        return "你明显睡眠不足，话语简短"
    if debt >= DEBT_TIER_TIRED:
        return "你感觉有点累，反应比平时慢"
    return ""


__all__ = [
    "SleepState",
    "update_sleep_state",
    "sleep_deprived_tone",
    "DEBT_TIER_TIRED",
    "DEBT_TIER_DEPRIVED",
    "DEBT_TIER_CRITICAL",
    "DEBT_MAX",
]

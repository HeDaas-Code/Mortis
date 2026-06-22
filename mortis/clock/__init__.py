"""Mortis clock — 逻辑时钟 + 昼夜节律 + 时差 + 睡眠不足。

issue #26: 收尾模块。包含:
- logical: LogicalClock + ConsciousnessState 枚举
- state: SleepState + update_sleep_state + sleep_deprived_tone
- schedule: Scheduler (整合 REFLECT/DREAM 触发)

不在范围: 与 owner 活跃度检测的真实集成(留 master runtime #26 后续)。
"""

from __future__ import annotations

from mortis.clock.logical import ConsciousnessState, LogicalClock
from mortis.clock.state import (
    DEBT_MAX,
    DEBT_TIER_CRITICAL,
    DEBT_TIER_DEPRIVED,
    DEBT_TIER_TIRED,
    SleepState,
    sleep_deprived_tone,
    update_sleep_state,
)
from mortis.clock.schedule import (
    OWNER_GOODNIGHT_KEYWORDS,
    OWNER_INACTIVITY_MINUTES,
    Scheduler,
    TickResult,
    detect_goodnight,
)


__all__ = [
    # logical
    "ConsciousnessState",
    "LogicalClock",
    # state
    "SleepState",
    "update_sleep_state",
    "sleep_deprived_tone",
    "DEBT_TIER_TIRED",
    "DEBT_TIER_DEPRIVED",
    "DEBT_TIER_CRITICAL",
    "DEBT_MAX",
    # schedule
    "OWNER_INACTIVITY_MINUTES",
    "OWNER_GOODNIGHT_KEYWORDS",
    "Scheduler",
    "TickResult",
    "detect_goodnight",
]

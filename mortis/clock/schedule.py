"""Mortis clock — Scheduler: 调度 REFLECT/DREAM 触发。

issue #26: 整合 LogicalClock + SleepState + owner 不活跃检测。

逻辑:
  1. LogicalClock 进入 REFLECT 时段 → 检查 owner 不活跃 30 分钟
  2. Owner 说"晚安" → 立即进入 REFLECT(无论时段)
  3. DREAM 触发后 → LogicalClock 进入对应 DREAM 时段
  4. ERODE → 时段结束自动醒
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from mortis.clock.logical import ConsciousnessState, LogicalClock
from mortis.clock.state import SleepState, update_sleep_state


_logger = logging.getLogger(__name__)


OWNER_INACTIVITY_MINUTES = 30
OWNER_GOODNIGHT_KEYWORDS = ("晚安", "goodnight", "good night", "再见", "bye")


@dataclass(frozen=True)
class TickResult:
    """Scheduler 单次 tick 结果。"""
    state: ConsciousnessState           # 当前 ConsciousnessState
    should_trigger_reflect: bool        # 是否该跑 REFLECT
    should_trigger_dream_light: bool    # 是否该跑 DREAM_LIGHT
    should_trigger_dream_deep: bool     # 是否该跑 DREAM_DEEP
    reason: str                          # 触发原因
    sleep_deprived_tone: str             # 注入语气(可能为空)


def detect_goodnight(message: str) -> bool:
    """检测 owner 是否说"晚安"等告别语。"""
    if not message:
        return False
    msg_lower = message.lower()
    return any(kw in msg_lower for kw in OWNER_GOODNIGHT_KEYWORDS)


class Scheduler:
    """调度 REFLECT/DREAM 触发。"""

    def __init__(
        self,
        clock: LogicalClock | None = None,
        *,
        inactivity_minutes: int = OWNER_INACTIVITY_MINUTES,
        tz: timezone = timezone.utc,
    ) -> None:
        self.clock = clock or LogicalClock(tz=tz)
        self.inactivity_minutes = inactivity_minutes
        self._tz = tz

    def tick(
        self,
        *,
        owner_last_active: datetime | None = None,
        owner_message: str | None = None,
        sleep_state: SleepState | None = None,
        now: datetime | None = None,
    ) -> TickResult:
        """单次 tick。

        Args:
            owner_last_active: owner 上次活跃时间(默认 now)。
            owner_message: owner 最新消息(用于检测"晚安")。
            sleep_state: 当前睡眠状态(可选,用于生成 sleep_deprived_tone)。
            now: 当前时间(测试注入)。

        Returns:
            TickResult — 含当前 state + 各触发标志 + 原因 + 睡眠不足语气。
        """
        ts = now if now is not None else datetime.now(tz=self._tz)
        current_state = self.clock.state(ts)

        should_reflect = False
        should_dream_light = False
        should_dream_deep = False
        reason = ""

        # 规则 1: owner 说"晚安" → 立即进入 REFLECT
        if owner_message and detect_goodnight(owner_message):
            should_reflect = True
            reason = f"owner said goodnight: {owner_message[:30]!r}"

        # 规则 2: REFLECT 时段 + owner 不活跃 30 分钟
        elif current_state == ConsciousnessState.REFLECT:
            if owner_last_active is None:
                should_reflect = True
                reason = "REFLECT period + no owner activity tracked"
            else:
                inactive_min = (ts - owner_last_active).total_seconds() / 60.0
                if inactive_min >= self.inactivity_minutes:
                    should_reflect = True
                    reason = f"REFLECT period + owner inactive {inactive_min:.0f} min"

        # 规则 3: DREAM_LIGHT 时段 + 没有最近 dream
        if current_state == ConsciousnessState.DREAM_LIGHT and not should_reflect:
            should_dream_light = True
            reason = "DREAM_LIGHT period entered"

        # 规则 4: DREAM_DEEP 时段 + 没有最近 deep dream
        if current_state == ConsciousnessState.DREAM_DEEP and not should_reflect:
            should_dream_deep = True
            reason = "DREAM_DEEP period entered"

        # 睡眠不足语气
        sleep_tone = ""
        if sleep_state is not None:
            from mortis.clock.state import sleep_deprived_tone
            sleep_tone = sleep_deprived_tone(sleep_state.debt)

        return TickResult(
            state=current_state,
            should_trigger_reflect=should_reflect,
            should_trigger_dream_light=should_dream_light,
            should_trigger_dream_deep=should_dream_deep,
            reason=reason,
            sleep_deprived_tone=sleep_tone,
        )


__all__ = [
    "OWNER_INACTIVITY_MINUTES",
    "OWNER_GOODNIGHT_KEYWORDS",
    "TickResult",
    "Scheduler",
    "detect_goodnight",
]

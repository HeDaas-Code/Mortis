"""Mortis clock — LogicalClock 逻辑时钟 + 6 时段。

issue #26: 逻辑时钟(不是真实时钟)判断当前 ConsciousnessState。

6 时段 (RFC §二):
  06:00-22:00: AWAKE
  22:00-23:00: REFLECT (owner 还在对话则推迟)
  23:00-02:00: DREAM_LIGHT
  02:00-04:00: DREAM_DEEP
  04:00-06:00: ERODE

设计要点:
- 纯计算 + datetime — 无 IO, 时段切换 < 1ms
- 时段用 hour-only 比较 (分钟/秒忽略)
- next_transition 返回 (datetime, state) — 下一时段切换时间 + 目标 state
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from enum import Enum


class ConsciousnessState(str, Enum):
    """意识状态机(RFC §二)。"""
    AWAKE = "awake"
    REFLECT = "reflect"
    DREAM_LIGHT = "dream_light"
    DREAM_MEDIUM = "dream_medium"   # 扩展(#23 medium dream 触发)
    DREAM_DEEP = "dream_deep"
    ERODE = "erode"


# ============================================================
# 时段表 (start_hour, end_hour, state)
# 注: end_hour 用严格 < 比较, 跨午夜用 (start, 24) + (0, end)
# ============================================================

_TIME_BLOCKS: list[tuple[int, int, ConsciousnessState]] = [
    (6, 22, ConsciousnessState.AWAKE),
    (22, 23, ConsciousnessState.REFLECT),
    (23, 24, ConsciousnessState.DREAM_LIGHT),    # 23:00-24:00 light
    (0, 2, ConsciousnessState.DREAM_LIGHT),      # 00:00-02:00 light
    (2, 4, ConsciousnessState.DREAM_DEEP),
    (4, 6, ConsciousnessState.ERODE),
]


def _state_for_hour(hour: int) -> ConsciousnessState:
    """纯 hour → state 映射。"""
    for start, end, state in _TIME_BLOCKS:
        if start <= end:
            if start <= hour < end:
                return state
        else:
            # 跨午夜 (0, 2)
            if hour >= start or hour < end:
                return state
    # 默认 fallback — 实际表覆盖 0-23 全部, 不应到这
    return ConsciousnessState.AWAKE


# ============================================================
# LogicalClock
# ============================================================


class LogicalClock:
    """逻辑时钟 — 判断当前时段 + 计算下一时段切换。"""

    def __init__(self, *, now: datetime | None = None) -> None:
        """构造 LogicalClock。可选注入 now (测试用)。"""
        self._now_override = now

    def now(self, real_now: datetime | None = None) -> datetime:
        """返回当前时间(测试时可注入,否则 datetime.now)。"""
        if self._now_override is not None:
            return self._now_override
        if real_now is not None:
            return real_now
        return datetime.now()

    def state(self, at: datetime | None = None) -> ConsciousnessState:
        """判断 at 时刻的 ConsciousnessState。"""
        ts = at if at is not None else self.now()
        return _state_for_hour(ts.hour)

    def next_transition(
        self, at: datetime | None = None
    ) -> tuple[datetime, ConsciousnessState]:
        """返回下一时段切换时间 + 目标 state。

        算法: 从 at.hour 起, 找到下一时段边界 (start_hour / end_hour),
        构造下一天的边界 datetime。
        """
        ts = at if at is not None else self.now()
        current_state = self.state(ts)
        current_hour = ts.hour

        # 候选边界: 同一 day 还没到的所有 start_hour + 下一 day 全部 start_hour
        candidates: list[tuple[int, ConsciousnessState]] = []
        for start, _end, state in _TIME_BLOCKS:
            candidates.append((start, state))

        # 找下一个 start_hour > current_hour (同日)
        next_day_candidates = [
            (24 + start, state) for start, state in candidates
        ]  # 24-30 表示次日

        all_candidates = sorted(candidates + next_day_candidates)

        for hour_abs, state in all_candidates:
            if hour_abs > current_hour:
                # 构造 datetime
                if hour_abs < 24:
                    target = ts.replace(
                        hour=hour_abs, minute=0, second=0, microsecond=0
                    )
                else:
                    # 次日
                    days_later = hour_abs // 24
                    target_hour = hour_abs % 24
                    target = (ts + timedelta(days=days_later)).replace(
                        hour=target_hour, minute=0, second=0, microsecond=0
                    )
                # 跳过状态相同的"边界" (e.g. 22:00 进入 REFLECT 但 current=AWAKE)
                if state != current_state:
                    return (target, state)

        # 不应到达这里 — 24h 周期总会切
        return (ts + timedelta(hours=1), ConsciousnessState.AWAKE)


__all__ = ["ConsciousnessState", "LogicalClock"]

"""Mortis reflect — REFLECT 触发条件。

issue #21: 判定当前是否该跑 REFLECT。

三种触发条件(本期实现 1 + 2,条件 3 是 #26 的事):
1. owner 主动说晚安/收工 → 无条件触发
2. 今日 session 数 >= 阈值 AND 距上次 REFLECT > 4 小时
3. owner 不活跃 > 30 分钟 (#26 逻辑时钟,本期不实现)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


# 当日 session 数触发阈值 (issue #21 acceptance)
SESSION_THRESHOLD: int = 3

# 两次 REFLECT 之间最短间隔(小时)
MIN_HOURS_BETWEEN: float = 4.0


def should_reflect(
    now: datetime,
    last_reflection: Optional[datetime],
    session_count_today: int,
    owner_said_goodnight: bool,
) -> bool:
    """判定当前是否该跑 REFLECT。

    Args:
        now: 当前时间(传参便于测试)。
        last_reflection: 上次 REFLECT 的时间。None = 从未反思过。
        session_count_today: 今天已开过的 session 数。
        owner_said_goodnight: owner 是否主动说晚安/收工。

    Returns:
        True = 该反思,False = 暂不。

    触发逻辑:
        条件 1: owner_said_goodnight → True
        条件 2: session_count_today >= SESSION_THRESHOLD
                AND (last_reflection is None OR 距 last_reflection > 4h)
                → True
        其余 → False
    """
    # 条件 1: owner 主动收工
    if owner_said_goodnight:
        return True

    # 条件 2: 阈值 + 间隔
    if session_count_today >= SESSION_THRESHOLD:
        if last_reflection is None:
            return True
        delta = (now - last_reflection).total_seconds()
        if delta > MIN_HOURS_BETWEEN * 3600:
            return True
        return False

    return False


def hours_since(last: datetime, now: datetime) -> float:
    """辅助:两时间相差多少小时 — 供调用方做更细的间隔判定。

    公开为独立函数以方便单测。
    """
    return (now - last).total_seconds() / 3600.0


def _ensure_aware(dt: datetime) -> datetime:
    """内部:datetime 没带 tz 就当 UTC — 避免 mixed tz 算 delta 出错。"""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

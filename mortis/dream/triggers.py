"""Mortis dream — Medium/Deep 触发条件。

issue #23: 决定何时跑中梦/深梦。

MEDIUM 触发条件 (任一):
- 距上次 medium dream ≥ 7 天
- pending reflections ≥ 10 条
- 手动触发 (manual=True)

DEEP 触发条件 (任一):
- 距上次 deep dream ≥ 30 天
- 总 drift 超过阈值 (默认 0.7)
- 手动触发 (manual=True)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from mortis.dream.phases import DreamLevel
from mortis.vault import Vault


_logger = logging.getLogger(__name__)


MEDIUM_INTERVAL_DAYS = 7
DEEP_INTERVAL_DAYS = 30
PENDING_REFLECTIONS_THRESHOLD = 10
DEFAULT_DRIFT_THRESHOLD = 0.7


@dataclass(frozen=True)
class TriggerDecision:
    """触发判断结果。"""
    should_run: bool
    level: DreamLevel
    reason: str
    days_since_last: float | None = None
    pending_count: int | None = None
    drift_total: float | None = None


def _days_since(iso_ts: str | None, now: datetime) -> float | None:
    if not iso_ts:
        return None
    ts = datetime.fromisoformat(iso_ts)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (now - ts).total_seconds() / 86400.0


def _find_last_dream_mtime(vault: Vault, level: DreamLevel) -> datetime | None:
    """扫描 mortis-dream-log/<level>/ 取最近 mtime。"""
    log_root = Path(vault.root) / "mortis-dream-log" / level.value
    if not log_root.exists():
        return None
    latest_mtime: float = 0.0
    for md in log_root.glob("*.md"):
        mt = md.stat().st_mtime
        if mt > latest_mtime:
            latest_mtime = mt
    if latest_mtime == 0.0:
        return None
    return datetime.fromtimestamp(latest_mtime, tz=timezone.utc)


def _count_pending_reflections(vault: Vault) -> int:
    """数 mortis-subconscious/pending-reflections/ 下的 .md。"""
    pending = Path(vault.root) / "mortis-subconscious" / "pending-reflections"
    if not pending.exists():
        return 0
    return sum(1 for _ in pending.glob("*.md"))


def should_medium_dream(
    vault: Vault,
    *,
    now: datetime | None = None,
    pending_reflections: list[str] | None = None,
    manual: bool = False,
    interval_days: int = MEDIUM_INTERVAL_DAYS,
    pending_threshold: int = PENDING_REFLECTIONS_THRESHOLD,
) -> TriggerDecision:
    """判断是否该跑中梦。

    Args:
        vault: vault 根。
        now: 当前时间(测试注入)。
        pending_reflections: 可选直接传 pending paths(测试用,避免扫盘)。
        manual: 手动触发总是 True。
        interval_days: 间隔阈值(默认 7)。
        pending_threshold: pending 数量阈值(默认 10)。

    Returns:
        TriggerDecision。
    """
    if manual:
        return TriggerDecision(should_run=True, level=DreamLevel.MEDIUM, reason="manual trigger")

    now = now or datetime.now(tz=timezone.utc)
    last = _find_last_dream_mtime(vault, DreamLevel.MEDIUM)
    days = _days_since(last.isoformat() if last else None, now)

    pending_count: int
    if pending_reflections is not None:
        pending_count = len(pending_reflections)
    else:
        pending_count = _count_pending_reflections(vault)

    # 条件 1: 间隔
    if days is None or days >= interval_days:
        return TriggerDecision(
            should_run=True,
            level=DreamLevel.MEDIUM,
            reason=f"interval >= {interval_days} days (days={days})",
            days_since_last=days,
            pending_count=pending_count,
        )

    # 条件 2: pending 数量
    if pending_count >= pending_threshold:
        return TriggerDecision(
            should_run=True,
            level=DreamLevel.MEDIUM,
            reason=f"pending reflections >= {pending_threshold}",
            days_since_last=days,
            pending_count=pending_count,
        )

    return TriggerDecision(
        should_run=False,
        level=DreamLevel.MEDIUM,
        reason=f"interval not met and pending {pending_count} < {pending_threshold}",
        days_since_last=days,
        pending_count=pending_count,
    )


def should_deep_dream(
    vault: Vault,
    *,
    now: datetime | None = None,
    drift_total: float | None = None,
    manual: bool = False,
    interval_days: int = DEEP_INTERVAL_DAYS,
    drift_threshold: float = DEFAULT_DRIFT_THRESHOLD,
) -> TriggerDecision:
    """判断是否该跑深梦。"""
    if manual:
        return TriggerDecision(
            should_run=True, level=DreamLevel.DEEP, reason="manual trigger",
            drift_total=drift_total,
        )

    now = now or datetime.now(tz=timezone.utc)
    last = _find_last_dream_mtime(vault, DreamLevel.DEEP)
    days = _days_since(last.isoformat() if last else None, now)

    # 条件 1: 间隔
    if days is None or days >= interval_days:
        return TriggerDecision(
            should_run=True,
            level=DreamLevel.DEEP,
            reason=f"interval >= {interval_days} days (days={days})",
            days_since_last=days,
            drift_total=drift_total,
        )

    # 条件 2: drift 超阈值
    if drift_total is not None and drift_total > drift_threshold:
        return TriggerDecision(
            should_run=True,
            level=DreamLevel.DEEP,
            reason=f"drift {drift_total:.2f} > threshold {drift_threshold}",
            days_since_last=days,
            drift_total=drift_total,
        )

    return TriggerDecision(
        should_run=False,
        level=DreamLevel.DEEP,
        reason=f"interval not met and drift not high",
        days_since_last=days,
        drift_total=drift_total,
    )


__all__ = [
    "MEDIUM_INTERVAL_DAYS",
    "DEEP_INTERVAL_DAYS",
    "PENDING_REFLECTIONS_THRESHOLD",
    "DEFAULT_DRIFT_THRESHOLD",
    "TriggerDecision",
    "should_medium_dream",
    "should_deep_dream",
]

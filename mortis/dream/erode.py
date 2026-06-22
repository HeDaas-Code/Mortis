"""Mortis dream — ERODE phase: 衰减 + archive。

issue #23: 跨维度侵蚀。规则:
- last_validated > 30 天: confidence × 0.8
- last_validated > 90 天: confidence × 0.5
- confidence < 0.1: 移到 mortis-growth/archive/ (不删)
- archive/ 里的条目不再影响行为

设计要点:
- 纯函数 erode_growths() 返回 (survived: list[Growth], to_archive: list[Growth])
- 调用方负责 archive 写盘(vault.write_growth + 删除原文件)
- 时间用 datetime.now(timezone.utc) 一致化
- archive 后 confidence 保持低值(不归零)— 让 owner 知道曾存在
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Iterable

from mortis.growth.model import Growth


# ============================================================
# 常量
# ============================================================

THIRTY_DAYS_DAMPING = 0.8    # 30 天未验证 × 0.8
NINETY_DAYS_DAMPING = 0.5    # 90 天未验证 × 0.5
ARCHIVE_THRESHOLD = 0.1      # confidence 低于此值 → archive


# ============================================================
# 内部工具
# ============================================================


def _days_since(iso_ts: str, now: datetime) -> float:
    """ISO8601 字符串 → 距 now 的天数 (浮点)。"""
    ts = datetime.fromisoformat(iso_ts)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (now - ts).total_seconds() / 86400.0


def _decay_factor(days_since_validated: float) -> float:
    """根据天数返回 confidence 乘子。

    规则:
        days < 30:   × 1.0 (不衰减)
        30 <= days < 90: × 0.8
        days >= 90:  × 0.5
    """
    if days_since_validated < 30.0:
        return 1.0
    if days_since_validated < 90.0:
        return THIRTY_DAYS_DAMPING
    return NINETY_DAYS_DAMPING


# ============================================================
# 主 API
# ============================================================


def erode_growths(
    growths: Iterable[Growth],
    now: datetime | None = None,
) -> tuple[list[Growth], list[Growth]]:
    """对 growth 列表应用侵蚀规则。

    Args:
        growths: 待侵蚀的 growth 列表。
        now: 当前时间 (测试用注入;默认 datetime.now(timezone.utc))。

    Returns:
        (survived, to_archive) — 两份都是新 Growth 对象 (frozen replace)。
        survived: 留在 mortis-growth/ 里的(可能 confidence 已下降)。
        to_archive: confidence < 0.1 的,调用方负责移到 mortis-growth/archive/。
    """
    if now is None:
        now = datetime.now(tz=timezone.utc)

    survived: list[Growth] = []
    to_archive: list[Growth] = []

    for g in growths:
        days = _days_since(g.last_validated, now)
        factor = _decay_factor(days)
        new_conf = g.confidence * factor

        if new_conf < ARCHIVE_THRESHOLD:
            # archive 但保留 confidence (标记)
            to_archive.append(replace(g, confidence=new_conf))
        else:
            if factor < 1.0:
                survived.append(replace(g, confidence=new_conf))
            else:
                survived.append(g)

    return survived, to_archive


# ============================================================
# helpers
# ============================================================


def days_since_validated(g: Growth, now: datetime | None = None) -> float:
    """helper: 距 last_validated 天数。供 trigger / 测试复用。"""
    if now is None:
        now = datetime.now(tz=timezone.utc)
    return _days_since(g.last_validated, now)


__all__ = [
    "THIRTY_DAYS_DAMPING",
    "NINETY_DAYS_DAMPING",
    "ARCHIVE_THRESHOLD",
    "erode_growths",
    "days_since_validated",
]
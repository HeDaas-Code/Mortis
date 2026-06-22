"""Mortis steiner — drift 报警。

issue #24: 任意维度的不安值 ≥ 0.75 → 通知 owner。
对应 RFC §5.4 第 7 次编辑触发"drift 报警"。

设计要点:
- 纯函数 — 不依赖 vault / IO,只接 UneaseState
- **不在 #24 范围**:实际通知通道(邮件 / 桌面通知 / CLI 输出)
  — issue #24 契约明确"不实现 owner 通知通道"。
  通知实现在后续 issue 由 Hermes 接力。
"""

from __future__ import annotations

from .unease import UneaseState


# drift 报警阈值(对应 RFC §5.4:7 次编辑 → 1.0)
DRIFT_THRESHOLD: float = 0.75


def should_notify_owner(unease: UneaseState) -> bool:
    """任意维度的不安值 ≥ 0.75 → True。

    Args:
        unease: 当前 UneaseState。

    Returns:
        True = 建议通知 owner;False = 暂不通知。
    """
    return any(v >= DRIFT_THRESHOLD for v in unease.per_dimension.values())

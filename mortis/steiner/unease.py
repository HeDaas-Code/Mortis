"""Mortis steiner — UneaseState 管理。

issue #24: `mortis-steiner/unease.json` 存每个 7 维度的不安值。

JSON 形状:
    {
        "per_dimension": {"identity": 0.15, "values": 0.0, ...},
        "last_decay": "2026-06-22T10:00:00+00:00"
    }

设计要点:
- frozen dataclass — 任何修改走 dataclasses.replace 返回新对象（与 Growth 一致）
- accumulate 是纯函数:per_dimension[dim] += delta, cap 1.0
- decay 是纯函数:基于 last_decay 距 now 的天数,每个维度乘 0.85**days
- 低于 0.01 的维度置 0（避免浮点残留）
- vault 路径白名单 None（steiner 不在 GROWTH_WHITELIST 内）
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from mortis.growth.model import Dimension

if TYPE_CHECKING:
    from mortis.vault.local import Vault


# 每天衰减系数（RFC §5.5: 每天 ×0.85）
DECAY_PER_DAY: float = 0.85

# owner 每次编辑默认累积量
DEFAULT_ACCUMULATE_DELTA: float = 0.15

# steiner 隐藏层目录名（注意带连字符,vault 内实际子目录名）
STEINER_DIR: str = "mortis-steiner"

# 不安文件相对路径
UNEASE_FILE: str = f"{STEINER_DIR}/unease.json"


def _new_per_dimension() -> dict[Dimension, float]:
    """生成 7 维度全 0 的 per_dimension dict。"""
    return {d: 0.0 for d in Dimension}


def _now_iso() -> str:
    """当前 UTC 时间的 ISO8601 字符串。"""
    return datetime.now(tz=timezone.utc).isoformat()


def _parse_iso(s: str) -> datetime:
    """解析 ISO8601 字符串 → datetime(允许各种 UTC 偏移格式)。"""
    # Python 3.11+ 的 fromisoformat 已能处理 'Z' 后缀和偏移
    return datetime.fromisoformat(s)


@dataclass(frozen=True)
class UneaseState:
    """Mortis 的不安状态 — 每个维度一个 0.0~1.0 的不安值。

    frozen: 不可变 — 任何更新走 dataclasses.replace() 返回新对象。
    per_dimension: 7 维各自的不安值,key 必须覆盖 Dimension 枚举的全部 7 项。
    last_decay: 上次衰减时间(ISO8601)。首次创建为 now。
    """

    per_dimension: dict[Dimension, float] = field(default_factory=_new_per_dimension)
    last_decay: str = field(default_factory=_now_iso)

    def max_unease(self) -> float:
        """返回 7 维度中最大的不安值(0.0~1.0)。无维度时返回 0.0。"""
        if not self.per_dimension:
            return 0.0
        return max(self.per_dimension.values())

    def dim_unease(self, dim: Dimension) -> float:
        """单个维度的不安值(默认 0.0)。"""
        return self.per_dimension.get(dim, 0.0)


def load_unease(vault: "Vault") -> UneaseState:
    """从 vault 读 une.json → UneaseState。

    文件不存在 → 返回全 0 + last_decay=now 的新状态。
    文件存在但 JSON 损坏 → 返回全 0 + last_decay=now（不抛错,
    steiner 是隐藏层,出问题应静默回退,不能干扰主流程）。
    """
    try:
        entry = vault.read(UNEASE_FILE, whitelist=None)
    except FileNotFoundError:
        return UneaseState()
    except Exception:
        return UneaseState()

    try:
        data = json.loads(entry.content)
    except (json.JSONDecodeError, TypeError, ValueError):
        return UneaseState()

    per_dim_raw = data.get("per_dimension", {}) or {}
    per_dim: dict[Dimension, float] = _new_per_dimension()
    if isinstance(per_dim_raw, dict):
        for dim in Dimension:
            value = per_dim_raw.get(dim.value, 0.0)
            try:
                v = float(value)
            except (TypeError, ValueError):
                v = 0.0
            # 钳到 [0.0, 1.0] — 防外部破坏导致越界
            per_dim[dim] = max(0.0, min(1.0, v))

    last_decay = data.get("last_decay")
    if not isinstance(last_decay, str) or not last_decay:
        last_decay = _now_iso()

    return UneaseState(per_dimension=per_dim, last_decay=last_decay)


def save_unease(vault: "Vault", state: UneaseState) -> bool:
    """把 UneaseState 写到 vault.mortis-steiner/unease.json。

    whitelist=None — steiner 不在 GROWTH_WHITELIST 内,需要显式 None
    绕过 _enforce 检查（但走 _safe_path 路径遍历防御）。

    与 load_unease 一致: 出错静默返回 False, 不干扰主流程 (issue #40)。
    """
    import logging
    _logger = logging.getLogger(__name__)

    payload = {
        "per_dimension": {
            dim.value: state.per_dimension.get(dim, 0.0)
            for dim in Dimension
        },
        "last_decay": state.last_decay,
    }
    content = json.dumps(payload, ensure_ascii=False, indent=2)
    try:
        vault.write(UNEASE_FILE, content, whitelist=None)
        return True
    except Exception as e:
        _logger.warning("save_unease: write failed: %s", e)
        return False


def accumulate(
    state: UneaseState,
    dimension: Dimension,
    delta: float = DEFAULT_ACCUMULATE_DELTA,
) -> UneaseState:
    """累积某个维度的不安值,返回新 UneaseState(原对象不变)。

    新值 = old + delta,cap 1.0。
    """
    old = state.per_dimension.get(dimension, 0.0)
    new_val = min(1.0, max(0.0, old + delta))
    new_per = dict(state.per_dimension)
    new_per[dimension] = new_val
    return replace(state, per_dimension=new_per)


def decay(state: UneaseState, now: datetime) -> UneaseState:
    """根据 now - last_decay 的天数,对每个维度做 ×0.85**days 的衰减。

    低于 0.01 的维度置 0(避免浮点残留)。
    last_decay 更新为 now。
    """
    try:
        last = _parse_iso(state.last_decay)
    except (ValueError, TypeError):
        last = now

    # 容错:now 无 tzinfo → 当作 UTC
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)

    delta_seconds = (now - last).total_seconds()
    # 负数时间差(回拨时钟) → 不衰减,只更新 last_decay
    if delta_seconds <= 0:
        return replace(state, last_decay=now.isoformat())

    days = delta_seconds / 86400.0
    factor = DECAY_PER_DAY ** days

    new_per: dict[Dimension, float] = {}
    for dim, val in state.per_dimension.items():
        new_val = val * factor
        if new_val < 0.01:
            new_val = 0.0
        new_per[dim] = new_val

    return replace(state, per_dimension=new_per, last_decay=now.isoformat())

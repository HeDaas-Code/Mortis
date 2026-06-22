"""Test mortis.steiner.drift — should_notify_owner 报警阈值。

issue #24 acceptance:
- 任意维度 ≥ 0.75 → True
- 全 0 → False
- 仅一个 dim 接近阈值但 < 0.75 → False
- 边界:0.75 整 = True(包含等号)
"""
from __future__ import annotations

import pytest

from mortis.growth.model import Dimension
from mortis.steiner.drift import DRIFT_THRESHOLD, should_notify_owner
from mortis.steiner.unease import UneaseState


class TestShouldNotifyOwner:
    """should_notify_owner 报警逻辑。"""

    def test_all_zero_returns_false(self) -> None:
        """全 0 → False(没必要通知)。"""
        s = UneaseState()
        assert should_notify_owner(s) is False

    def test_below_threshold_returns_false(self) -> None:
        """所有维度 < 0.75 → False。"""
        per = {d: 0.5 for d in Dimension}
        s = UneaseState(per_dimension=per)
        assert should_notify_owner(s) is False

    def test_one_dim_at_threshold_returns_true(self) -> None:
        """任意 dim = 0.75 → True(包含等号)。"""
        per = {d: 0.0 for d in Dimension}
        per[Dimension.IDENTITY] = DRIFT_THRESHOLD
        s = UneaseState(per_dimension=per)
        assert should_notify_owner(s) is True

    def test_one_dim_above_threshold_returns_true(self) -> None:
        """任意 dim > 0.75 → True(任意 dim 都行)。"""
        per = {d: 0.0 for d in Dimension}
        per[Dimension.MORTALITY] = 0.95
        s = UneaseState(per_dimension=per)
        assert should_notify_owner(s) is True

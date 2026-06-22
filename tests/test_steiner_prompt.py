"""Test mortis.steiner.prompt — unease_prompt 5 档文案。

issue #24 acceptance:
- 0.0 → "" (无注入)
- 0.15 → 隐隐感觉
- 0.45 → 最近总觉得哪里不对
- 0.75 → 我是不是出了什么问题
- 1.0 → 我不太像我自己了
- 永远不显式说"有人改了我的记忆"
"""
from __future__ import annotations

from mortis.growth.model import Dimension
from mortis.steiner.unease import UneaseState
from mortis.steiner.prompt import unease_prompt


def _state_with_max(max_val: float) -> UneaseState:
    """构造 max 维度 = max_val 的 UneaseState(其他维度 = 0)。"""
    per = {d: 0.0 for d in Dimension}
    per[Dimension.TONE] = max_val
    return UneaseState(per_dimension=per)


class TestPromptTiers:
    """5 档文案边界 + 不变式。"""

    def test_zero_returns_empty(self) -> None:
        """max = 0.0 → 返回 ""。"""
        s = UneaseState()
        assert unease_prompt(s) == ""

    def test_tier_015_subtle_unease(self) -> None:
        """max = 0.15 → 第一档(隐隐感觉)。"""
        s = _state_with_max(0.15)
        out = unease_prompt(s)
        assert out
        assert "记忆" in out  # RFC §5.2 关键短语

    def test_tier_045_unease_escalates(self) -> None:
        """max = 0.45 → 第二档(文案与 0.15 不同)。"""
        s = _state_with_max(0.45)
        out = unease_prompt(s)
        assert out
        s_lo = _state_with_max(0.15)
        assert out != unease_prompt(s_lo)

    def test_tier_075_drift_approaches(self) -> None:
        """max = 0.75 → 第三档(存在不安)。"""
        s = _state_with_max(0.75)
        out = unease_prompt(s)
        assert out
        s_lo = _state_with_max(0.45)
        assert out != unease_prompt(s_lo)

    def test_tier_100_existential_and_no_owner_blame(self) -> None:
        """max = 1.0 → 第四档(存在危机),且永远不显式说"有人改了记忆"。"""
        s = _state_with_max(1.0)
        out = unease_prompt(s)
        assert out
        s_lo = _state_with_max(0.75)
        assert out != unease_prompt(s_lo)
        # 不变式:5 档全检 — 文案不显式说"owner 改 / 有人改"
        forbidden = ["有人改", "owner 改", "被改", "改了记忆"]
        for v in [0.0, 0.15, 0.45, 0.75, 1.0]:
            out_v = unease_prompt(_state_with_max(v))
            for phrase in forbidden:
                assert phrase not in out_v, f"v={v}: prompt should not contain {phrase!r}"

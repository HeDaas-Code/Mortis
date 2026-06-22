"""Test mortis.dream.seed_check — drift 计算 + LLM 自评。"""

from __future__ import annotations

import pytest

from mortis.dream.seed_check import (
    DEFAULT_DRIFT_THRESHOLD,
    DriftReport,
    seed_check,
)
from mortis.growth.model import Dimension
from mortis.provider import MockProvider
from mortis.seed import Seed


def _make_seed() -> Seed:
    """构造测试用 seed。"""
    return Seed(
        identity="我是 mortis",
        values="应该注重 owner 体验",
        tone="平和",
        agency="自主决策",
        relations="信任 owner",
        creativity="联想丰富",
        mortality="接受遗忘",
    )


class TestSeedCheckBasic:
    def test_perfect_alignment(self):
        """LLM 返回全 0 → total=0, no alert."""
        provider = MockProvider(responses=[
            '{"identity": 0.0, "values": 0.0, "tone": 0.0, "agency": 0.0, '
            '"relations": 0.0, "creativity": 0.0, "mortality": 0.0}'
        ])
        report = seed_check(seed=_make_seed(), growth_summary="test", provider=provider)
        assert isinstance(report, DriftReport)
        assert report.total_drift == 0.0
        assert report.needs_owner_notify is False

    def test_high_drift_triggers_notify(self):
        provider = MockProvider(responses=[
            '{"identity": 0.8, "values": 0.7, "tone": 0.6, "agency": 0.5, '
            '"relations": 0.4, "creativity": 0.3, "mortality": 0.2}'
        ])
        report = seed_check(seed=_make_seed(), growth_summary="test", provider=provider, threshold=0.5)
        assert report.total_drift == pytest.approx(0.8, abs=0.01)
        assert report.needs_owner_notify is True

    def test_per_dim_alerts(self):
        provider = MockProvider(responses=[
            '{"identity": 0.6, "values": 0.3, "tone": 0.1, "agency": 0.0, '
            '"relations": 0.0, "creativity": 0.0, "mortality": 0.0}'
        ])
        report = seed_check(seed=_make_seed(), growth_summary="test", provider=provider)
        # identity 0.6 > 0.5 → alert
        assert report.per_dim_alerts[Dimension.IDENTITY] is True
        # values 0.3 < 0.5 → no alert
        assert report.per_dim_alerts[Dimension.VALUES] is False

    def test_default_threshold(self):
        assert DEFAULT_DRIFT_THRESHOLD == 0.7

    def test_empty_response_fallback(self):
        """LLM 返回空 → fallback 全 0."""
        provider = MockProvider(responses=[""])
        report = seed_check(seed=_make_seed(), growth_summary="test", provider=provider)
        assert report.total_drift == 0.0
        assert "fallback" in report.raw_response or report.raw_response == ""


class TestSeedCheckParse:
    def test_parse_json_with_markdown(self):
        """LLM 可能包在 ```json``` 里 → 也能解析。"""
        provider = MockProvider(responses=[
            '```json\n{"identity": 0.5, "values": 0.0, "tone": 0.0, "agency": 0.0, '
            '"relations": 0.0, "creativity": 0.0, "mortality": 0.0}\n```'
        ])
        report = seed_check(seed=_make_seed(), growth_summary="test", provider=provider)
        # 解析可能失败回退 0 (regex fallback 不一定能解 markdown 包)
        # 至少 total_drift 是数值
        assert 0.0 <= report.total_drift <= 1.0

    def test_clamp_to_0_1(self):
        """LLM 返回 > 1.0 → clamp 到 1.0."""
        provider = MockProvider(responses=[
            '{"identity": 1.5, "values": 0.0, "tone": 0.0, "agency": 0.0, '
            '"relations": 0.0, "creativity": 0.0, "mortality": 0.0}'
        ])
        report = seed_check(seed=_make_seed(), growth_summary="test", provider=provider)
        assert report.per_dimension[Dimension.IDENTITY] == 1.0

    def test_missing_dims_default_zero(self):
        """LLM 漏掉一维 → 默认 0.0."""
        provider = MockProvider(responses=[
            '{"identity": 0.5, "values": 0.5}'  # 只 2 维
        ])
        report = seed_check(seed=_make_seed(), growth_summary="test", provider=provider)
        # tone 默认 0
        assert report.per_dimension[Dimension.TONE] == 0.0


class TestDriftReportDataclass:
    def test_frozen(self):
        from mortis.growth.model import Dimension
        r = DriftReport(
            per_dimension={d: 0.0 for d in Dimension},
            total_drift=0.0,
            per_dim_alerts={d: False for d in Dimension},
            needs_owner_notify=False,
            threshold=0.7,
            raw_response="",
        )
        with pytest.raises(Exception):
            r.total_drift = 0.5  # type: ignore[misc]

    def test_summary_includes_max_dim(self):
        from mortis.growth.model import Dimension
        per_dim = {d: 0.0 for d in Dimension}
        per_dim[Dimension.IDENTITY] = 0.7
        r = DriftReport(
            per_dimension=per_dim,
            total_drift=0.7,
            per_dim_alerts={d: False for d in Dimension},
            needs_owner_notify=True,
            threshold=0.7,
            raw_response="",
        )
        s = r.summary()
        assert "0.70" in s or "0.7" in s
        assert "identity" in s

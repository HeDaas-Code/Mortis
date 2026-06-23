"""Test mortis.toolagent.vault_stats — LLM 分析 (#63)。

issue #63 验收: VaultStatsAgent 支持 LLM 分析。
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from mortis.growth.model import Dimension, DreamLevel, Growth
from mortis.toolagent.vault_stats import VaultStatsAgent
from mortis.provider.mock import MockProvider
from mortis.vault import Vault


@pytest.fixture
def vault_dir() -> Path:
    with tempfile.TemporaryDirectory(prefix="mortis-stats-") as td:
        d = Path(td)
        (d / "mortis-journal" / "sub-outputs").mkdir(parents=True)
        (d / "mortis-growth" / "identity").mkdir(parents=True)
        yield d


def _write_growth(vault: Vault, id: str, body: str, dimension: Dimension, confidence: float) -> None:
    now = datetime.now(tz=timezone.utc).isoformat()
    g = Growth(
        id=id, dimension=dimension, confidence=confidence,
        created_at=now, last_validated=now,
        source_sessions=(), dream_level=DreamLevel.LIGHT,
        emotional_valence=0.0, emotional_arousal=0.0,
        tags=(), body=body,
    )
    vault.write_growth(g)


class TestVaultStatsAnalyze:
    """issue #63: LLM 分析功能。"""

    def test_analyze_false_no_llm_call(self, vault_dir: Path):
        """analyze=False 时不调用 LLM。"""
        v = Vault(vault_dir)
        _write_growth(v, "g1", "test", Dimension.IDENTITY, 0.5)
        mock = MockProvider()
        agent = VaultStatsAgent(v, provider=mock)
        r = agent.execute({"analyze": False})
        assert r.success is True
        assert r.data.get("analysis") is None

    def test_analyze_true_without_provider(self, vault_dir: Path):
        """analyze=True 但无 provider 时降级处理。"""
        v = Vault(vault_dir)
        _write_growth(v, "g1", "test", Dimension.IDENTITY, 0.5)
        agent = VaultStatsAgent(v, provider=None)
        r = agent.execute({"analyze": True})
        assert r.success is True
        assert r.data.get("analysis") is None

    def test_analyze_true_with_provider(self, vault_dir: Path):
        """analyze=True 且有 provider 时调用 LLM。"""
        v = Vault(vault_dir)
        _write_growth(v, "g1", "identity content", Dimension.IDENTITY, 0.7)
        _write_growth(v, "g2", "values content", Dimension.VALUES, 0.8)
        mock = MockProvider(responses=["Growth analysis: Strong identity and values."])
        agent = VaultStatsAgent(v, provider=mock)
        r = agent.execute({"analyze": True})
        assert r.success is True
        assert r.data.get("analysis") is not None
        assert "identity" in r.data["analysis"].lower() or "values" in r.data["analysis"].lower()

    def test_analyze_includes_stats_data(self, vault_dir: Path):
        """LLM 分析应基于统计数据。"""
        v = Vault(vault_dir)
        _write_growth(v, "g1", "test", Dimension.IDENTITY, 0.9)
        _write_growth(v, "g2", "test", Dimension.VALUES, 0.3)
        _write_growth(v, "g3", "test", Dimension.TONE, 0.6)
        mock = MockProvider(responses=["Analysis complete."])
        agent = VaultStatsAgent(v, provider=mock)
        r = agent.execute({"analyze": True})
        assert r.success is True
        # 统计数据应该正常返回
        assert r.data["total_files"] == 3
        assert r.data["by_dimension"]["identity"] == 1
        assert r.data["by_dimension"]["values"] == 1

    def test_analyze_exception_returns_none(self, vault_dir: Path):
        """provider 抛异常时 analysis 为 None。"""

        class BadProvider:
            def generate_text(self, prompt, system="", **kwargs):
                raise RuntimeError("analysis failed")

        v = Vault(vault_dir)
        _write_growth(v, "g1", "test", Dimension.IDENTITY, 0.5)
        agent = VaultStatsAgent(v, provider=BadProvider())
        r = agent.execute({"analyze": True})
        assert r.success is True
        assert r.data.get("analysis") is None

    def test_analyze_with_dimension_filter(self, vault_dir: Path):
        """analyze 与 dimension 过滤可组合。"""
        v = Vault(vault_dir)
        _write_growth(v, "g1", "test", Dimension.IDENTITY, 0.9)
        _write_growth(v, "g2", "test", Dimension.VALUES, 0.3)
        mock = MockProvider(responses=["Identity dimension analysis."])
        agent = VaultStatsAgent(v, provider=mock)
        r = agent.execute({"dimension": "identity", "analyze": True})
        assert r.success is True
        assert r.data["total_files"] == 1

    def test_histogram_buckets(self, vault_dir: Path):
        """置信度直方图正确分桶。"""
        v = Vault(vault_dir)
        _write_growth(v, "g1", "test", Dimension.IDENTITY, 0.05)
        _write_growth(v, "g2", "test", Dimension.IDENTITY, 0.55)
        _write_growth(v, "g3", "test", Dimension.IDENTITY, 0.95)
        agent = VaultStatsAgent(v)
        r = agent.execute({})
        assert r.success is True
        histogram = r.data["confidence_histogram"]
        assert len(histogram) == 10
        assert histogram[0] == 1  # 0.05 in 0.0-0.1 bucket
        assert histogram[5] == 1  # 0.55 in 0.5-0.6 bucket
        assert histogram[9] == 1  # 0.95 in 0.9-1.0 bucket


class TestVaultStatsProvider:
    """issue #63: VaultStatsAgent 支持 provider 注入。"""

    def test_provider_field_exists(self, vault_dir: Path):
        """VaultStatsAgent 应该有 provider 字段。"""
        v = Vault(vault_dir)
        agent = VaultStatsAgent(v, provider=None)
        assert hasattr(agent, "provider")
        assert agent.provider is None

    def test_provider_can_be_set(self, vault_dir: Path):
        """provider 可以被传入。"""
        v = Vault(vault_dir)
        mock = MockProvider()
        agent = VaultStatsAgent(v, provider=mock)
        assert agent.provider is mock

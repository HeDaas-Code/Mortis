"""Test mortis.toolagent.vault_stats — VaultStatsAgent。"""

from __future__ import annotations

import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest

from mortis.growth.model import Dimension, DreamLevel, Growth
from mortis.toolagent.vault_stats import VaultStatsAgent
from mortis.vault import Vault
from mortis.vault.local import VaultAccessDenied


@pytest.fixture
def vault_dir() -> Path:
    with tempfile.TemporaryDirectory(prefix="mortis-stats-") as td:
        d = Path(td)
        (d / "mortis-journal" / "sub-outputs").mkdir(parents=True)
        (d / "mortis-journal" / "notes").mkdir(parents=True)
        yield d


def _write_growth(vault: Vault, id: str, body: str, dimension: Dimension = Dimension.IDENTITY, confidence: float = 0.5) -> None:
    now = datetime.now(tz=timezone.utc).isoformat()
    g = Growth(
        id=id, dimension=dimension, confidence=confidence,
        created_at=now, last_validated=now,
        source_sessions=(), dream_level=DreamLevel.LIGHT,
        emotional_valence=0.0, emotional_arousal=0.0,
        tags=(), body=body,
    )
    vault.write_growth(g)


class TestVaultStatsAgent:
    def test_empty_vault(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        agent = VaultStatsAgent(v)
        r = agent.execute({})
        assert r.success is True
        assert r.data["total_files"] == 0
        assert r.data["by_dimension"] == {}
        assert r.data["confidence_histogram"] == [0] * 10

    def test_count_total(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        _write_growth(v, "g1", "x")
        _write_growth(v, "g2", "y")
        _write_growth(v, "g3", "z")
        agent = VaultStatsAgent(v)
        r = agent.execute({})
        assert r.data["total_files"] == 3

    def test_by_dimension(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        _write_growth(v, "g1", "x", dimension=Dimension.IDENTITY)
        _write_growth(v, "g2", "y", dimension=Dimension.IDENTITY)
        _write_growth(v, "g3", "z", dimension=Dimension.VALUES)
        agent = VaultStatsAgent(v)
        r = agent.execute({})
        assert r.data["by_dimension"] == {"identity": 2, "values": 1}

    def test_confidence_histogram(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        _write_growth(v, "g1", "x", confidence=0.05)   # bucket 0
        _write_growth(v, "g2", "y", confidence=0.55)   # bucket 5
        _write_growth(v, "g3", "z", confidence=0.95)   # bucket 9
        agent = VaultStatsAgent(v)
        r = agent.execute({})
        hist = r.data["confidence_histogram"]
        assert hist[0] == 1
        assert hist[5] == 1
        assert hist[9] == 1
        assert sum(hist) == 3


# ============================================================
# issue #71 MEDIUM-D — 路径枚举攻击防护
# ============================================================


class TestVaultStatsAgentExceptionClassification:
    """vault_stats 同样需分类处理 read_growth 异常, VaultAccessDenied 必须 log。"""

    def _build_vault_with_rels(self, rels: list[str]) -> Vault:
        """构造 vault, list_growths 返回指定 rels (Mock 绕过真实 IO)。

        用 `spec=Vault` 让 Mock 知道 Vault 的方法签名, Pyright 可识别属性赋值。
        type: ignore — Pyright 误报 Mock method 属性赋值, 实际运行时正确。
        """
        v: Vault = Mock(spec=Vault)  # type: ignore[assignment]
        v.list_growths.return_value = rels  # type: ignore[attr-defined]
        return v

    def test_vault_access_denied_logs_warning(self, caplog):
        """VaultAccessDenied → log warning 含 'blocked by whitelist' + rel_path。"""
        v = self._build_vault_with_rels(["mortis-journal/sub-outputs/leak.md"])
        v.read_growth.side_effect = VaultAccessDenied("blocked by whitelist")  # type: ignore[attr-defined]
        agent = VaultStatsAgent(v)

        with caplog.at_level(logging.WARNING, logger="mortis.toolagent.vault_stats"):
            r = agent.execute({})

        # 业务正确: stats 仍然 success (只统计能读的)
        assert r.success is True
        # 安全正确: 必须有 WARNING log
        warns = [rec for rec in caplog.records if rec.levelno == logging.WARNING]
        assert len(warns) >= 1, "VaultAccessDenied 必须 log warning, 不能静默"
        assert any("blocked by whitelist" in rec.getMessage() for rec in warns)
        assert any("mortis-journal/sub-outputs/leak.md" in rec.getMessage() for rec in warns)

    def test_file_not_found_silent_skip(self, caplog):
        """FileNotFoundError → 静默 skip, 不 log warning。"""
        v = self._build_vault_with_rels(["deleted.md"])
        v.read_growth.side_effect = FileNotFoundError("no such file")  # type: ignore[attr-defined]
        agent = VaultStatsAgent(v)

        with caplog.at_level(logging.WARNING, logger="mortis.toolagent.vault_stats"):
            r = agent.execute({})

        assert r.success is True
        warns = [rec for rec in caplog.records if rec.levelno == logging.WARNING]
        assert len(warns) == 0

    def test_other_exception_logs_warning_with_type(self, caplog):
        """其他 Exception → log warning 含异常类型。"""
        v = self._build_vault_with_rels(["corrupted.md"])
        v.read_growth.side_effect = RuntimeError("disk full")  # type: ignore[attr-defined]
        agent = VaultStatsAgent(v)

        with caplog.at_level(logging.WARNING, logger="mortis.toolagent.vault_stats"):
            r = agent.execute({})

        assert r.success is True
        warns = [rec for rec in caplog.records if rec.levelno == logging.WARNING]
        assert len(warns) >= 1
        assert any("RuntimeError" in rec.getMessage() for rec in warns)

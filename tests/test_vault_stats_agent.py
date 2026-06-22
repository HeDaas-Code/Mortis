"""Test mortis.toolagent.vault_stats — VaultStatsAgent。"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from mortis.growth.model import Dimension, DreamLevel, Growth
from mortis.toolagent.vault_stats import VaultStatsAgent
from mortis.vault import Vault


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

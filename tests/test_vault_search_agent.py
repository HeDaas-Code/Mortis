"""Test mortis.toolagent.vault_search — VaultSearchAgent。

issue #25 验收: 全文 + 标签 + 双链图遍历。
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from mortis.growth.model import Dimension, DreamLevel, Growth
from mortis.toolagent.vault_search import VaultSearchAgent
from mortis.vault import Vault


@pytest.fixture
def vault_dir() -> Path:
    with tempfile.TemporaryDirectory(prefix="mortis-vsearch-") as td:
        d = Path(td)
        (d / "mortis-journal" / "sub-outputs").mkdir(parents=True)
        (d / "mortis-journal" / "notes").mkdir(parents=True)
        yield d


def _write_growth(vault: Vault, id: str, body: str, tags: tuple[str, ...] = (), dimension: Dimension = Dimension.IDENTITY) -> None:
    now = datetime.now(tz=timezone.utc).isoformat()
    g = Growth(
        id=id, dimension=dimension, confidence=0.5,
        created_at=now, last_validated=now,
        source_sessions=(), dream_level=DreamLevel.LIGHT,
        emotional_valence=0.0, emotional_arousal=0.0,
        tags=tags, body=body,
    )
    vault.write_growth(g)


class TestVaultSearchAgent:
    def test_search_all_no_query(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        _write_growth(v, "g1", "alpha")
        _write_growth(v, "g2", "beta")
        agent = VaultSearchAgent(v)
        r = agent.execute({})
        assert r.success is True
        assert len(r.data["matches"]) == 2

    def test_search_by_query(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        _write_growth(v, "g1", "alpha bravo")
        _write_growth(v, "g2", "charlie")
        agent = VaultSearchAgent(v)
        r = agent.execute({"query": "alpha"})
        assert len(r.data["matches"]) == 1
        assert r.data["matches"][0]["rel_path"].endswith("g1.md")

    def test_search_by_tag(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        _write_growth(v, "g1", "x", tags=("urgent",))
        _write_growth(v, "g2", "y", tags=("low",))
        agent = VaultSearchAgent(v)
        r = agent.execute({"tags": ["urgent"]})
        assert len(r.data["matches"]) == 1

    def test_search_case_insensitive(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        _write_growth(v, "g1", "Hello World")
        agent = VaultSearchAgent(v)
        r = agent.execute({"query": "hello"})
        assert len(r.data["matches"]) == 1

    def test_traverse_links_disabled_by_default(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        _write_growth(v, "g1", "see [[g2]]")
        _write_growth(v, "g2", "linked from g1")
        agent = VaultSearchAgent(v)
        r = agent.execute({})
        assert r.data["graph"] is None

    def test_traverse_links_depth_1(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        _write_growth(v, "g1", "alpha links to [[g2]]")
        _write_growth(v, "g2", "linked from g1")
        agent = VaultSearchAgent(v)
        r = agent.execute({"query": "alpha", "traverse_links": True, "max_depth": 1})
        assert r.data["graph"] is not None
        # g1 → g2 link captured (g1 body contains [[g2]])
        # target may be raw "g2" or resolved rel_path
        assert any("g2" in k for k in r.data["graph"].keys())
        # source rel_path points to g1
        sources = next(iter(r.data["graph"].values()))
        assert any("g1" in s for s in sources)

    def test_traverse_links_depth_2(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        _write_growth(v, "g1", "alpha links to [[g2]]")
        _write_growth(v, "g2", "links to [[g3]]")
        _write_growth(v, "g3", "deep")
        agent = VaultSearchAgent(v)
        r = agent.execute({"query": "alpha", "traverse_links": True, "max_depth": 2})
        # depth 2 should cover g2 (depth 1 from g1) + g3 (depth 2 from g2)
        assert r.data["graph"] is not None
        assert any("g2" in k for k in r.data["graph"].keys())
        assert any("g3" in k for k in r.data["graph"].keys())

    def test_no_matches_empty(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        agent = VaultSearchAgent(v)
        r = agent.execute({"query": "nothing"})
        assert r.success is True
        assert r.data["matches"] == []

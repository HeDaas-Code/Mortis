"""Test mortis.toolagent.vault_search — 语义搜索 (#63)。

issue #63 验收: VaultSearchAgent 支持语义搜索。
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from mortis.growth.model import Dimension, DreamLevel, Growth
from mortis.toolagent.vault_search import VaultSearchAgent
from mortis.provider.mock import MockProvider
from mortis.vault import Vault


@pytest.fixture
def vault_dir() -> Path:
    with tempfile.TemporaryDirectory(prefix="mortis-semantic-") as td:
        d = Path(td)
        (d / "mortis-journal" / "sub-outputs").mkdir(parents=True)
        (d / "mortis-growth" / "identity").mkdir(parents=True)
        yield d


def _write_growth(vault: Vault, id: str, body: str, tags: tuple[str, ...] = ()) -> None:
    now = datetime.now(tz=timezone.utc).isoformat()
    g = Growth(
        id=id, dimension=Dimension.IDENTITY, confidence=0.5,
        created_at=now, last_validated=now,
        source_sessions=(), dream_level=DreamLevel.LIGHT,
        emotional_valence=0.0, emotional_arousal=0.0,
        tags=tags, body=body,
    )
    vault.write_growth(g)


class TestVaultSearchSemantic:
    """issue #63: 语义搜索功能。"""

    def test_semantic_false_no_llm_call(self, vault_dir: Path):
        """semantic=False 时不调用 LLM。"""
        v = Vault(vault_dir)
        _write_growth(v, "g1", "alpha")
        mock = MockProvider()
        agent = VaultSearchAgent(v, provider=mock)
        r = agent.execute({"query": "alpha", "semantic": False})
        assert r.success is True
        assert r.data.get("semantic_summary") is None

    def test_semantic_true_without_provider(self, vault_dir: Path):
        """semantic=True 但无 provider 时降级处理。"""
        v = Vault(vault_dir)
        _write_growth(v, "g1", "alpha")
        agent = VaultSearchAgent(v, provider=None)
        r = agent.execute({"query": "alpha", "semantic": True})
        assert r.success is True
        assert r.data.get("semantic_summary") is None

    def test_semantic_true_with_provider(self, vault_dir: Path):
        """semantic=True 且有 provider 时调用 LLM。"""
        v = Vault(vault_dir)
        _write_growth(v, "g1", "alpha bravo")
        _write_growth(v, "g2", "charlie delta")
        mock = MockProvider(responses=[
            "SCORE: 1 0.95\nSCORE: 2 0.3\nSUMMARY: Alpha bravo is most relevant."
        ])
        agent = VaultSearchAgent(v, provider=mock)
        r = agent.execute({"query": "alpha", "semantic": True})
        assert r.success is True
        assert r.data.get("semantic_summary") is not None
        assert "relevant" in r.data["semantic_summary"].lower()

    def test_semantic_reranks_results(self, vault_dir: Path):
        """语义搜索应按 LLM 返回的分数排序。"""
        v = Vault(vault_dir)
        _write_growth(v, "g1", "python programming")
        _write_growth(v, "g2", "javascript web")
        _write_growth(v, "g3", "rust systems")
        # LLM 认为 g2 最相关
        mock = MockProvider(responses=[
            "SCORE: 2 0.9\nSCORE: 1 0.5\nSCORE: 3 0.2\nSUMMARY: JavaScript is most relevant."
        ])
        agent = VaultSearchAgent(v, provider=mock)
        r = agent.execute({"query": "web", "semantic": True})
        assert r.success is True
        matches = r.data["matches"]
        # g2 应该排在前面 (score 0.9)
        assert "javascript" in matches[0]["title"].lower() or "g2" in matches[0]["rel_path"]

    def test_semantic_without_query(self, vault_dir: Path):
        """无 query 时 semantic 参数无效。"""
        v = Vault(vault_dir)
        _write_growth(v, "g1", "alpha")
        mock = MockProvider()
        agent = VaultSearchAgent(v, provider=mock)
        r = agent.execute({"semantic": True})
        assert r.success is True
        assert r.data.get("semantic_summary") is None

    def test_top_k_limit(self, vault_dir: Path):
        """top_k 限制返回结果数量。"""
        v = Vault(vault_dir)
        for i in range(20):
            _write_growth(v, f"g{i}", f"content {i}")
        agent = VaultSearchAgent(v)
        r = agent.execute({"query": "content", "top_k": 5})
        assert r.success is True
        assert len(r.data["matches"]) == 5

    def test_semantic_top_k_combo(self, vault_dir: Path):
        """语义搜索 + top_k 同时生效。"""
        v = Vault(vault_dir)
        for i in range(10):
            _write_growth(v, f"g{i}", f"test content {i}")
        mock = MockProvider(responses=[
            "\n".join([f"SCORE: {i+1} {1.0 - i*0.1}" for i in range(10)]) + "\nSUMMARY: Done."
        ])
        agent = VaultSearchAgent(v, provider=mock)
        r = agent.execute({"query": "test", "semantic": True, "top_k": 3})
        assert r.success is True
        assert len(r.data["matches"]) == 3

    def test_matches_have_score_field(self, vault_dir: Path):
        """搜索结果应包含 score 字段。"""
        v = Vault(vault_dir)
        _write_growth(v, "g1", "alpha")
        agent = VaultSearchAgent(v)
        r = agent.execute({"query": "alpha"})
        assert r.success is True
        assert "score" in r.data["matches"][0]

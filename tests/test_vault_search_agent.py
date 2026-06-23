"""Test mortis.toolagent.vault_search — VaultSearchAgent。

issue #25 验收: 全文 + 标签 + 双链图遍历。
"""

from __future__ import annotations

import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

from mortis.growth.model import Dimension, DreamLevel, Growth
from mortis.toolagent.vault_search import VaultSearchAgent
from mortis.vault import Vault
from mortis.vault.local import VaultAccessDenied


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


# ============================================================
# issue #71 MEDIUM-D — 路径枚举攻击防护
# ============================================================


class TestVaultSearchAgentExceptionClassification:
    """原 `except Exception: continue` 静默吞错, 攻击者可枚举被拒路径。

    修复后: FileNotFoundError / VaultAccessDenied / 其他 Exception 分类处理,
    VaultAccessDenied 与未知异常必须 log warning (非静默)。
    """

    def _build_vault_with_rels(self, rels: list[str]) -> Vault:
        """构造 vault, list_growths 返回指定 rels (绕过真实 IO)。

        用 `spec=Vault` 让 Mock 知道 Vault 的方法签名, Pyright 可识别属性赋值。
        type: ignore — Pyright 误报 Mock method 属性赋值, 实际运行时正确。
        """
        v: Vault = Mock(spec=Vault)  # type: ignore[assignment]
        v.list_growths.return_value = rels  # type: ignore[attr-defined]
        return v

    def test_vault_access_denied_logs_warning(self, caplog):
        """VaultAccessDenied → log warning 含 'blocked by whitelist' + rel_path。

        关键反断言: log 必须包含, 否则攻击者可通过 matches 差异枚举被拒路径。
        """
        v = self._build_vault_with_rels(["mortis-journal/sub-outputs/leak.md"])
        # read_growth 对该路径抛 VaultAccessDenied
        v.read_growth.side_effect = VaultAccessDenied("blocked by whitelist")  # type: ignore[attr-defined]
        agent = VaultSearchAgent(v)

        with caplog.at_level(logging.WARNING, logger="mortis.toolagent.vault_search"):
            r = agent.execute({"query": "anything"})

        # 业务正确: matches 空 (被拒路径不返回)
        assert r.success is True
        assert r.data["matches"] == []
        # 安全正确: 必须有 WARNING log
        warns = [rec for rec in caplog.records if rec.levelno == logging.WARNING]
        assert len(warns) >= 1, "VaultAccessDenied 必须 log warning, 不能静默"
        assert any("blocked by whitelist" in rec.getMessage() for rec in warns)
        assert any("mortis-journal/sub-outputs/leak.md" in rec.getMessage() for rec in warns)

    def test_file_not_found_silent_skip(self, caplog):
        """FileNotFoundError → 静默 skip, 不 log warning (文件被外部删除是正常的)。

        区别于 VaultAccessDenied: 这里的目的是"文件不在了"而非"被拒访问"。
        """
        v = self._build_vault_with_rels(["deleted.md"])
        v.read_growth.side_effect = FileNotFoundError("no such file")  # type: ignore[attr-defined]
        agent = VaultSearchAgent(v)

        with caplog.at_level(logging.WARNING, logger="mortis.toolagent.vault_search"):
            r = agent.execute({"query": "anything"})

        assert r.success is True
        assert r.data["matches"] == []
        # FileNotFoundError 不应 log warning (否则 noise 大)
        warns = [rec for rec in caplog.records if rec.levelno == logging.WARNING]
        assert len(warns) == 0, (
            "FileNotFoundError 应静默 skip (文件被删是常态), "
            "log warning 等于把 noise 喂给运维"
        )

    def test_other_exception_logs_warning_with_type(self, caplog):
        """其他 Exception → log warning 含异常类型 (便于调试)。"""
        v = self._build_vault_with_rels(["corrupted.md"])
        v.read_growth.side_effect = RuntimeError("disk full")  # type: ignore[attr-defined]
        agent = VaultSearchAgent(v)

        with caplog.at_level(logging.WARNING, logger="mortis.toolagent.vault_search"):
            r = agent.execute({"query": "anything"})

        assert r.success is True
        assert r.data["matches"] == []
        warns = [rec for rec in caplog.records if rec.levelno == logging.WARNING]
        assert len(warns) >= 1
        assert any("RuntimeError" in rec.getMessage() for rec in warns)
        assert any("disk full" in rec.getMessage() for rec in warns)

    def test_bfs_links_vault_access_denied_logs_warning(self, caplog):
        """BFS 双链遍历同样分类处理 — VaultAccessDenied 必须 log。"""
        v = self._build_vault_with_rels(["seed.md"])
        v.read_growth.side_effect = VaultAccessDenied("blocked by whitelist")  # type: ignore[attr-defined]
        agent = VaultSearchAgent(v)

        with caplog.at_level(logging.WARNING, logger="mortis.toolagent.vault_search"):
            r = agent.execute({"query": "anything", "traverse_links": True})

        assert r.success is True
        warns = [rec for rec in caplog.records if rec.levelno == logging.WARNING]
        assert len(warns) >= 1
        # BFS log 与 search log 关键词不同 ("bfs_links" vs "search"),
        # 用于运维区分两条路径的拒绝事件
        assert any(
            "bfs_links" in rec.getMessage() or "search" in rec.getMessage()
            for rec in warns
        )

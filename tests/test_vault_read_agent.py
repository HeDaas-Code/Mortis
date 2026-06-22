"""Test mortis.toolagent.vault_read — VaultReadAgent。

issue #25 验收: 读 vault 文件 + 可选双链解析。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from mortis.toolagent.vault_read import VaultReadAgent
from mortis.vault import Vault


@pytest.fixture
def vault_dir() -> Path:
    with tempfile.TemporaryDirectory(prefix="mortis-vread-") as td:
        d = Path(td)
        (d / "mortis-journal" / "sub-outputs").mkdir(parents=True)
        (d / "mortis-journal" / "notes").mkdir(parents=True)
        yield d


@pytest.fixture
def seeded_vault(vault_dir: Path) -> Vault:
    """写 2 个文件: 一个有双链,一个纯文本。"""
    (vault_dir / "a.md").write_text(
        "链接 [[b]] 和 [[c|alias]]。普通文本。",
        encoding="utf-8",
    )
    (vault_dir / "plain.md").write_text("无链接。", encoding="utf-8")
    return Vault(vault_dir)


class TestVaultReadAgent:
    def test_basic_read(self, seeded_vault: Vault) -> None:
        agent = VaultReadAgent(seeded_vault)
        r = agent.execute({"rel_path": "plain.md"})
        assert r.success is True
        assert r.data["content"] == "无链接。"
        assert r.data["rel_path"] == "plain.md"
        assert r.data["links"] is None  # resolve_links=False

    def test_read_with_links(self, seeded_vault: Vault) -> None:
        agent = VaultReadAgent(seeded_vault)
        r = agent.execute({"rel_path": "a.md", "resolve_links": True})
        assert r.success is True
        assert r.data["links"] == ["b", "c"]

    def test_missing_rel_path(self, seeded_vault: Vault) -> None:
        agent = VaultReadAgent(seeded_vault)
        r = agent.execute({})
        assert r.success is False
        assert "rel_path" in (r.error or "")

    def test_file_not_found(self, seeded_vault: Vault) -> None:
        agent = VaultReadAgent(seeded_vault)
        r = agent.execute({"rel_path": "no-such.md"})
        assert r.success is False
        assert "not found" in (r.error or "").lower()

    def test_agent_id_default(self) -> None:
        agent = VaultReadAgent(Vault(Path("/tmp")))
        assert agent.agent_id == "vault:read"

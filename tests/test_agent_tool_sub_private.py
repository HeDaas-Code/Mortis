"""Test mortis.tools.agent_tool.VaultReadToolAgent sub 私域阻断 (issue #68 Critical-B)。

issue #68 PR #66 审计 Critical-B: vault:read_agent 缺 sub-outputs 白名单,
LLM 可读 mortis-journal/sub-outputs/<sub_id>.md。
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from mortis.tools.agent_tool import VaultReadToolAgent
from mortis.vault import Vault


@pytest.fixture
def vault_dir() -> Path:
    with tempfile.TemporaryDirectory(prefix="mortis-subpriv-") as td:
        d = Path(td)
        # sub-outputs
        (d / "mortis-journal" / "sub-outputs").mkdir(parents=True, exist_ok=True)
        (d / "mortis-journal" / "sub-outputs" / "leak.md").write_text(
            "sub review content", encoding="utf-8"
        )
        (d / "mortis-journal" / "sub-outputs" / "merged").mkdir(exist_ok=True)
        (d / "mortis-journal" / "sub-outputs" / "merged" / "x.md").write_text(
            "merged content", encoding="utf-8"
        )
        # 合法路径
        (d / "mortis-growth" / "identity").mkdir(parents=True, exist_ok=True)
        (d / "mortis-growth" / "identity" / "self.md").write_text(
            "---\nid: identity/self\ndimension: identity\nconfidence: 0.5\n"
            "created_at: 2026-06-23T00:00:00Z\nlast_validated: 2026-06-23T00:00:00Z\n"
            "source_sessions: []\nemotional_valence: 0.0\nemotional_arousal: 0.0\n"
            "dream_level: 0\ntags: []\n---\n# self\npublic content",
            encoding="utf-8",
        )
        yield d


class TestSubOutputBlocked:
    """issue #68 Critical-B: vault:read_agent 必须阻断 sub 私域。"""

    @pytest.mark.parametrize(
        "path",
        [
            "mortis-journal/sub-outputs/leak.md",
            "mortis-journal/sub-outputs/merged/x.md",
            "mortis-journal/sub-outputs/",
            # 路径绕过 (用栈式归一化阻止)
            "mortis-journal/foo/../sub-outputs/leak.md",
            "foo/../mortis-journal/sub-outputs/leak.md",
            "./mortis-journal/sub-outputs/leak.md",
        ],
    )
    def test_sub_outputs_blocked(self, vault_dir: Path, path: str) -> None:
        """所有尝试读 sub-outputs 的路径都必须被拒绝。"""
        v = Vault(vault_dir)
        agent = VaultReadToolAgent(v)
        r = agent.execute(path)
        assert r.success is False, f"路径 {path!r} 应该被拒绝, 但 success=True"
        assert "sub private domain" in (r.error or "").lower() or "access denied" in (r.error or "").lower()

    def test_sub_output_data_not_leaked(self, vault_dir: Path) -> None:
        """阻断后 content 不应包含 sub 私域内容。"""
        v = Vault(vault_dir)
        agent = VaultReadToolAgent(v)
        r = agent.execute("mortis-journal/sub-outputs/leak.md")
        assert r.success is False
        assert r.content is None or "sub review content" not in r.content

    def test_legitimate_path_allowed(self, vault_dir: Path) -> None:
        """合法路径仍可读 (regression)。"""
        v = Vault(vault_dir)
        agent = VaultReadToolAgent(v)
        r = agent.execute("mortis-growth/identity/self.md")
        assert r.success is True
        assert "public content" in (r.content or "")
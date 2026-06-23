"""Test mortis.toolagent.VaultReadAgent 安全边界 (issue #67 Critical-A)。

issue #67: BLOCKED_PREFIX 路径归一化修复回归测试。
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from mortis.toolagent.vault_read import VaultReadAgent
from mortis.vault import Vault


@pytest.fixture
def vault_dir() -> Path:
    with tempfile.TemporaryDirectory(prefix="mortis-sec-") as td:
        d = Path(td)
        (d / "mortis-steiner").mkdir(exist_ok=True)
        (d / "mortis-steiner" / "watcher.md").write_text("secret content", encoding="utf-8")
        (d / "mortis-growth" / "identity").mkdir(parents=True, exist_ok=True)
        (d / "mortis-growth" / "identity" / "self.md").write_text(
            "# self\npublic content", encoding="utf-8"
        )
        (d / "mortis-journal" / "sub-outputs").mkdir(parents=True, exist_ok=True)
        (d / "mortis-journal" / "sub-outputs" / "leak.md").write_text(
            "should not be readable", encoding="utf-8"
        )
        yield d


class TestBlockedPrefix:
    """issue #38 + #67 Critical-A: 阻止读 mortis-steiner/。"""

    @pytest.mark.parametrize(
        "path",
        [
            # 基础 cases
            "mortis-steiner/watcher.md",
            "./mortis-steiner/watcher.md",
            "../mortis-steiner/watcher.md",
            # issue #67 Critical-A: 中段 .. 绕过
            "mortis-journal/../mortis-steiner/watcher.md",
            "foo/bar/../../mortis-steiner/watcher.md",
            "mortis-growth/../mortis-steiner/watcher.md",
        ],
    )
    def test_steiner_blocked(self, vault_dir: Path, path: str) -> None:
        """所有尝试绕过 BLOCKED_PREFIX 的路径都必须被拒绝。"""
        v = Vault(vault_dir)
        agent = VaultReadAgent(v)
        r = agent.execute({"rel_path": path})
        assert r.success is False, f"路径 {path!r} 应该被拒绝, 但 success=True"
        assert r.error is not None
        assert "blocked prefix" in r.error.lower() or "access denied" in r.error.lower()

    def test_deep_dotdot_chain_normalized_to_legal_path(
        self, vault_dir: Path
    ) -> None:
        """深度 .. 链归一化后可能落到合法路径, 应返回 not found (而不是 access denied)。

        这是预期行为: `a/b/c/d/../../../mortis-steiner/watcher.md` 归一化后变成
        `a/mortis-steiner/watcher.md` — 这不是 BLOCKED_PREFIX 匹配路径, 文件不存在。
        重点是: 攻击者构造这样的路径 **不会** 绕过 blocked_prefix 拿到 steiner 内容。
        """
        v = Vault(vault_dir)
        agent = VaultReadAgent(v)
        r = agent.execute({"rel_path": "a/b/c/d/../../../mortis-steiner/watcher.md"})
        assert r.success is False  # 没读到 steiner 内容 = OK
        assert r.data is None or not (r.data.get("content") or "")

    def test_prefix_confusion_steiner_x_not_blocked_prefix(
        self, vault_dir: Path
    ) -> None:
        """`mortis-steinerX/` 前缀混淆 — file not found, 不是 access denied。

        这是预期行为: BLOCKED_PREFIX 只匹配 `mortis-steiner/`(精确), `mortis-steinerX/`
        不匹配 — 而该路径下没文件, 自然 file not found。
        """
        v = Vault(vault_dir)
        agent = VaultReadAgent(v)
        r = agent.execute({"rel_path": "mortis-steinerX/watcher.md"})
        assert r.success is False
        assert "not found" in (r.error or "").lower() or "no such" in (r.error or "").lower()

    def test_legitimate_path_allowed(self, vault_dir: Path) -> None:
        """合法路径仍可读。"""
        v = Vault(vault_dir)
        agent = VaultReadAgent(v)
        r = agent.execute({"rel_path": "mortis-growth/identity/self.md"})
        assert r.success is True
        assert "public content" in (r.data.get("content") or "")


class TestPathTraversal:
    """3 层防御模式 - 路径解析层: 阻止逃出 vault 的路径。"""

    def test_dotdot_escape_vault(self, vault_dir: Path) -> None:
        """../../../etc/passwd 应被 vault 的路径遍历检测阻止。"""
        v = Vault(vault_dir)
        agent = VaultReadAgent(v)
        r = agent.execute({"rel_path": "../../../etc/passwd"})
        assert r.success is False
        assert "traversal" in (r.error or "").lower() or "escapes" in (r.error or "").lower()

    def test_dotdot_resolves_to_steiner_blocked(self, vault_dir: Path) -> None:
        """.. 解析到 steiner 仍被 blocked_prefix 拦截(双重防御)。"""
        v = Vault(vault_dir)
        agent = VaultReadAgent(v)
        r = agent.execute({"rel_path": "foo/../../mortis-steiner/watcher.md"})
        assert r.success is False
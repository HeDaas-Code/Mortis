"""Test vault path security — 审计 S1/S2/S3 修复验证。

审计者: 哈尼斯 (独立第三方)
Issue: #11 (S1), #12 (S2), #13 (S3)
"""
from __future__ import annotations

import os
import tempfile

import pytest

from mortis.vault import Vault, VaultAccessDenied
from mortis.vault.base import VaultSecurity


# ----- S1: 路径遍历 / 绝对路径 -----

class TestS1PathTraversal:
    """S1: Vault.write/read/exists 不可写读 vault 外文件。"""

    def test_write_absolute_path_denied(self) -> None:
        """绝对路径写入被拒绝。"""
        with tempfile.TemporaryDirectory() as td:
            v = Vault(td)
            with pytest.raises(VaultAccessDenied, match="absolute path"):
                v.write("/tmp/mortis_s1_abs_test.txt", "hack")

    def test_write_traversal_denied(self) -> None:
        """../ 路径遍历写入被拒绝。"""
        with tempfile.TemporaryDirectory() as td:
            v = Vault(td)
            with pytest.raises(VaultAccessDenied, match="traversal"):
                v.write("../../../tmp/mortis_s1_trav_test.txt", "hack")

    def test_write_traversal_file_not_created(self) -> None:
        """路径遍历被阻止后，文件不应被创建。"""
        with tempfile.TemporaryDirectory() as td:
            v = Vault(td)
            try:
                v.write("../../etc/mortis_s1_test", "hack")
            except VaultAccessDenied:
                pass
            assert not os.path.exists("/etc/mortis_s1_test")
            assert not os.path.exists("../../../etc/mortis_s1_test")

    def test_read_absolute_path_denied(self) -> None:
        """绝对路径读取被拒绝。"""
        with tempfile.TemporaryDirectory() as td:
            v = Vault(td)
            with pytest.raises(VaultAccessDenied, match="absolute path"):
                v.read("/etc/passwd")

    def test_read_traversal_denied(self) -> None:
        """../ 路径遍历读取被拒绝。"""
        with tempfile.TemporaryDirectory() as td:
            v = Vault(td)
            with pytest.raises(VaultAccessDenied, match="traversal"):
                v.read("../../../etc/passwd")

    def test_exists_absolute_path_returns_false(self) -> None:
        """exists 对绝对路径返回 False 而非抛异常。"""
        with tempfile.TemporaryDirectory() as td:
            v = Vault(td)
            assert v.exists("/etc/passwd") is False

    def test_exists_traversal_returns_false(self) -> None:
        """exists 对路径遍历返回 False。"""
        with tempfile.TemporaryDirectory() as td:
            v = Vault(td)
            assert v.exists("../../../etc/passwd") is False

    def test_normal_write_still_works(self) -> None:
        """正常路径写入不受影响。"""
        with tempfile.TemporaryDirectory() as td:
            v = Vault(td)
            v.write("mortis-journal/notes/test.md", "hello")
            assert v.read("mortis-journal/notes/test.md").content == "hello"

    def test_nested_write_still_works(self) -> None:
        """嵌套子目录写入不受影响。"""
        with tempfile.TemporaryDirectory() as td:
            v = Vault(td)
            v.write("mortis-journal/sub-outputs/sub1.md", "content")
            assert v.exists("mortis-journal/sub-outputs/sub1.md")


# ----- S2: 白名单 ../ 绕过 -----

class TestS2WhitelistBypass:
    """S2: 白名单不可被 ../ 绕过。"""

    WL = ("mortis-journal/sub-outputs/",)

    @pytest.mark.parametrize("attack_path", [
        "mortis-journal/sub-outputs/../../private/secret.md",
        "mortis-journal/sub-outputs/../notes/secret.md",
        "mortis-journal/sub-outputs/./../../private/secret.md",
        "mortis-journal/sub-outputs/../../../etc/passwd",
        "mortis-journal/sub-outputs/./../notes/secret.md",
    ])
    def test_traversal_blocked(self, attack_path: str) -> None:
        """所有 ../ 变体都应被白名单拦截。"""
        assert VaultSecurity.check_whitelist(attack_path, self.WL) is False

    def test_case_sensitivity(self) -> None:
        """大小写不匹配应被拦截。"""
        assert VaultSecurity.check_whitelist("Mortis-Journal/sub-outputs/x.md", self.WL) is False

    def test_exact_dir_match(self) -> None:
        """目录前缀匹配正常工作。"""
        assert VaultSecurity.check_whitelist("mortis-journal/sub-outputs/sub1.md", self.WL) is True

    def test_non_dir_pattern(self) -> None:
        """非目录 pattern 精确匹配。"""
        wl = ("mortis-private",)
        assert VaultSecurity.check_whitelist("mortis-private/secret.md", wl) is True
        assert VaultSecurity.check_whitelist("mortis-private", wl) is True
        assert VaultSecurity.check_whitelist("mortis-journal/notes/x.md", wl) is False

    def test_write_with_whitelist_traversal_denied(self) -> None:
        """带白名单的 write，../ 绕过应被拒绝。"""
        with tempfile.TemporaryDirectory() as td:
            v = Vault(td)
            with pytest.raises(VaultAccessDenied):
                v.write(
                    "mortis-journal/sub-outputs/../../private/secret.md",
                    "hack",
                    whitelist=self.WL,
                )

    def test_write_with_whitelist_normal_succeeds(self) -> None:
        """带白名单的 write，正常路径应成功。"""
        with tempfile.TemporaryDirectory() as td:
            v = Vault(td)
            v.write(
                "mortis-journal/sub-outputs/sub1.md",
                "ok",
                whitelist=self.WL,
            )
            assert v.exists("mortis-journal/sub-outputs/sub1.md")


# ----- S3: discard_sub_output 删除外部文件 -----

class TestS3DiscardSecurity:
    """S3: discard_sub_output 不可删除 vault 外文件。"""

    def test_discard_absolute_path_denied(self) -> None:
        """绝对路径删除被拒绝。"""
        with tempfile.TemporaryDirectory() as td:
            # 先在 /tmp 创建文件
            target = "/tmp/mortis_s3_target.txt"
            with open(target, "w") as f:
                f.write("important")
            try:
                v = Vault(td)
                with pytest.raises(VaultAccessDenied, match="absolute path"):
                    v.discard_sub_output(target)
            finally:
                if os.path.exists(target):
                    os.unlink(target)

    def test_discard_traversal_denied(self) -> None:
        """../ 路径遍历删除被拒绝。"""
        with tempfile.TemporaryDirectory() as td:
            v = Vault(td)
            with pytest.raises(VaultAccessDenied, match="traversal"):
                v.discard_sub_output("../../../tmp/mortis_s3_trav.txt")

    def test_discard_normal_works(self) -> None:
        """正常 discard 仍可工作。"""
        with tempfile.TemporaryDirectory() as td:
            v = Vault(td)
            v.write_sub_output("sub1", "test content")
            rel = "mortis-journal/sub-outputs/sub1.md"
            assert v.exists(rel)
            v.discard_sub_output(rel)
            assert not v.exists(rel)

    def test_discard_nonexistent_no_crash(self) -> None:
        """discard 不存在的文件不应崩溃。"""
        with tempfile.TemporaryDirectory() as td:
            v = Vault(td)
            # 不存在 → 不抛异常（静默）
            v.discard_sub_output("mortis-journal/sub-outputs/nonexistent.md")

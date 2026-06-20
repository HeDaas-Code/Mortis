"""Test vault — 主人格的脑子(连续性载体) + sub 产出管理。"""
from __future__ import annotations

from pathlib import Path

import pytest

from mortis.vault import Vault, VaultEntry


@pytest.fixture
def v(tmp_path: Path) -> Vault:
    return Vault(tmp_path)


# ----- 基本文件 I/O -----

def test_vault_creates_dirs(tmp_path: Path) -> None:
    Vault(tmp_path)
    assert (tmp_path / "mortis-journal").exists()
    assert (tmp_path / "mortis-journal" / "sub-outputs").exists()
    assert (tmp_path / "mortis-journal" / "notes").exists()


def test_vault_read_write_roundtrip(v: Vault) -> None:
    v.write("a.txt", "hello")
    entry = v.read("a.txt")
    assert entry.content == "hello"
    assert entry.path == "a.txt"
    assert entry.modified_at  # ISO8601


def test_vault_read_missing_raises(v: Vault) -> None:
    with pytest.raises(FileNotFoundError):
        v.read("nope.txt")


def test_vault_exists(v: Vault) -> None:
    assert not v.exists("x.txt")
    v.write("x.txt", "y")
    assert v.exists("x.txt")


def test_vault_list_entries_empty(v: Vault) -> None:
    assert v.list_entries() == []


def test_vault_list_entries_recursive(v: Vault) -> None:
    v.write("a.txt", "1")
    v.write("sub/b.txt", "2")
    v.write("sub/deeper/c.txt", "3")
    entries = v.list_entries()
    assert "a.txt" in entries
    assert "sub/b.txt" in entries
    assert "sub/deeper/c.txt" in entries


def test_vault_list_entries_subdir(v: Vault) -> None:
    v.write("a.txt", "1")
    v.write("sub/b.txt", "2")
    entries = v.list_entries("sub")
    assert entries == ["sub/b.txt"]


# ----- sub 产出管理(F:合并回 vault)-----

def test_write_sub_output_creates_file(v: Vault) -> None:
    rel = v.write_sub_output("sub-abc", "task result here")
    assert rel == "mortis-journal/sub-outputs/sub-abc.md"
    assert v.exists(rel)


def test_write_sub_output_has_header(v: Vault) -> None:
    rel = v.write_sub_output("sub-1", "body")
    content = v.read(rel).content
    assert "<!-- sub-output: sub-1 -->" in content
    assert "<!-- status: pending_review -->" in content
    assert "body" in content


def test_list_pending_sub_outputs(v: Vault) -> None:
    v.write_sub_output("a", "1")
    v.write_sub_output("b", "2")
    pending = v.list_pending_sub_outputs()
    assert "mortis-journal/sub-outputs/a.md" in pending
    assert "mortis-journal/sub-outputs/b.md" in pending


def test_list_pending_empty(v: Vault) -> None:
    assert v.list_pending_sub_outputs() == []


def test_approve_sub_output_strips_header(v: Vault) -> None:
    rel = v.write_sub_output("sub-1", "the body")
    target = v.approve_sub_output(rel)
    content = v.read(target).content
    assert "<!--" not in content  # header stripped
    assert "the body" in content


def test_approve_sub_output_marks_status(v: Vault) -> None:
    rel = v.write_sub_output("sub-1", "body")
    v.approve_sub_output(rel)
    new_content = v.read(rel).content
    assert "<!-- status: approved -->" in new_content


def test_approve_to_target_path(v: Vault) -> None:
    rel = v.write_sub_output("sub-1", "merge me")
    target = v.approve_sub_output(rel, target_rel="notes/merged.md")
    assert target == "notes/merged.md"
    assert v.exists("notes/merged.md")
    assert "merge me" in v.read("notes/merged.md").content


def test_discard_sub_output(v: Vault) -> None:
    rel = v.write_sub_output("sub-1", "x")
    v.discard_sub_output(rel)
    assert not v.exists(rel)
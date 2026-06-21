"""Mortis vault 本地目录实现。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .base import VaultEntry, VaultProtocol, VaultSecurity


@dataclass
class Vault:
    """本地目录实现的 vault。

    vault 目录布局:
        vault/
            mortis-seed.md      (种子 — 主人格的来源)
            mortis-journal/     (主人格日志 + sub 产出待审稿)
                sub-outputs/    (sub 完成任务后的产出,待主人审阅)
                notes/          (主人格正式笔记)
    """

    root: Path

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "mortis-journal" / "sub-outputs").mkdir(parents=True, exist_ok=True)
        (self.root / "mortis-journal" / "notes").mkdir(parents=True, exist_ok=True)

    def read(self, rel_path: str) -> VaultEntry:
        """读 vault 内一个文件。"""
        p = self.root / rel_path
        if not p.exists():
            raise FileNotFoundError(f"vault entry not found: {rel_path}")
        stat = p.stat()
        return VaultEntry(
            path=rel_path,
            content=p.read_text(encoding="utf-8"),
            modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        )

    def write(self, rel_path: str, content: str) -> VaultEntry:
        """写一个文件到 vault。"""
        p = self.root / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        stat = p.stat()
        return VaultEntry(
            path=rel_path,
            content=content,
            modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        )

    def exists(self, rel_path: str) -> bool:
        return (self.root / rel_path).exists()

    def list_entries(self, rel_dir: str = "") -> list[str]:
        """列 vault 内某目录的所有文件路径（相对 vault 根）。"""
        p = self.root / rel_dir
        if not p.exists():
            return []
        return sorted(
            str(f.relative_to(self.root))
            for f in p.rglob("*")
            if f.is_file()
        )

    def write_sub_output(self, sub_id: str, content: str) -> str:
        """sub 完成任务后，产出存到 mortis-journal/sub-outputs/<sub_id>.md。"""
        rel = f"mortis-journal/sub-outputs/{sub_id}.md"
        header = (
            f"<!-- sub-output: {sub_id} -->\n"
            f"<!-- created_at: {datetime.now(tz=timezone.utc).isoformat()} -->\n"
            f"<!-- status: pending_review -->\n\n"
        )
        self.write(rel, header + content)
        return rel

    def list_pending_sub_outputs(self) -> list[str]:
        """列出所有待主人审阅的 sub 产出。"""
        return sorted(self.list_entries("mortis-journal/sub-outputs"))

    def approve_sub_output(self, rel_path: str, target_rel: str | None = None) -> str:
        """主人审阅通过 sub 产出。"""
        entry = self.read(rel_path)
        body_lines = [
            line for line in entry.content.splitlines()
            if not line.lstrip().startswith("<!--")
        ]
        body = "\n".join(body_lines).strip()
        if target_rel is None:
            sub_id = Path(rel_path).stem
            target_rel = f"mortis-journal/notes/{sub_id}.md"
        self.write(target_rel, body)
        old_lines = entry.content.splitlines()
        new_lines = [
            line.replace("pending_review", "approved") if "pending_review" in line else line
            for line in old_lines
        ]
        self.write(rel_path, "\n".join(new_lines))
        return target_rel

    def discard_sub_output(self, rel_path: str) -> None:
        """主人拒绝 sub 产出 — 删除文件。"""
        (self.root / rel_path).unlink()
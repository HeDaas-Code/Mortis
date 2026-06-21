"""Mortis vault 本地目录实现。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .base import VaultEntry, VaultProtocol, VaultSecurity


class VaultAccessDenied(Exception):
    """vault 访问被白名单拒绝。"""


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

    def _enforce(self, rel_path: str, whitelist: tuple[str, ...] | None, op: str) -> None:
        """白名单强制检查（issue #6 落地）。

        不传 whitelist 时不强制（保持向后兼容）。
        传 whitelist 时调 VaultSecurity.check_whitelist，失败抛 VaultAccessDenied。
        """
        if whitelist is None:
            return
        if not VaultSecurity.check_whitelist(rel_path, whitelist):
            raise VaultAccessDenied(VaultSecurity.deny_reason(rel_path, whitelist))

    def read(self, rel_path: str, whitelist: tuple[str, ...] | None = None) -> VaultEntry:
        """读 vault 内一个文件。

        Args:
            rel_path: 相对 vault 根的路径。
            whitelist: 可选白名单。传了则强制检查，不通过抛 VaultAccessDenied。
        """
        self._enforce(rel_path, whitelist, "read")
        p = self.root / rel_path
        if not p.exists():
            raise FileNotFoundError(f"vault entry not found: {rel_path}")
        stat = p.stat()
        return VaultEntry(
            path=rel_path,
            content=p.read_text(encoding="utf-8"),
            modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        )

    def write(
        self,
        rel_path: str,
        content: str,
        whitelist: tuple[str, ...] | None = None,
    ) -> VaultEntry:
        """写一个文件到 vault。

        Args:
            rel_path: 相对 vault 根的路径。
            content: 文件内容。
            whitelist: 可选白名单。传了则强制检查，不通过抛 VaultAccessDenied。
        """
        self._enforce(rel_path, whitelist, "write")
        p = self.root / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        stat = p.stat()
        return VaultEntry(
            path=rel_path,
            content=content,
            modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        )

    def exists(self, rel_path: str, whitelist: tuple[str, ...] | None = None) -> bool:
        """检查文件是否存在（不抛错，仅返回 bool）。

        白名单不通过时返回 False（不抛异常 — exists 是探测型 API）。
        """
        if whitelist is not None and not VaultSecurity.check_whitelist(rel_path, whitelist):
            return False
        return (self.root / rel_path).exists()

    def list_entries(
        self,
        rel_dir: str = "",
        whitelist: tuple[str, ...] | None = None,
    ) -> list[str]:
        """列 vault 内某目录的所有文件路径（相对 vault 根）。

        Args:
            rel_dir: 相对 vault 根的目录（默认根）。
            whitelist: 可选白名单。传了则只返回白名单内的路径。
        """
        p = self.root / rel_dir
        if not p.exists():
            return []
        all_entries = sorted(
            str(f.relative_to(self.root))
            for f in p.rglob("*")
            if f.is_file()
        )
        if whitelist is None:
            return all_entries
        return [
            e for e in all_entries
            if VaultSecurity.check_whitelist(e, whitelist)
        ]

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
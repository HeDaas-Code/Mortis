"""Mortis vault — 主人格的脑子(连续性的载体)。

vault = 主人格唯一的状态载体。Sub 不可访问主人的私人笔记。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class VaultEntry:
    """vault 单条记录。"""
    path: str  # 相对 vault 根的路径
    content: str
    modified_at: str  # ISO8601


@dataclass
class Vault:
    """主人格 vault 的根目录视图。

    vault 目录布局:
        vault/
            mortis-seed.md      (种子 — 主人格的来源)
            mortis-journal/     (主人格日志 + sub 产出待审稿)
                sub-outputs/    (sub 完成任务后的产出,待主人审阅)
    """

    root: Path

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "mortis-journal" / "sub-outputs").mkdir(parents=True, exist_ok=True)
        (self.root / "mortis-journal" / "notes").mkdir(parents=True, exist_ok=True)

    # ----- 文件读写 -----

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

    # ----- 列举 -----

    def list_entries(self, rel_dir: str = "") -> list[str]:
        """列 vault 内某目录的所有文件路径(相对 vault 根)。"""
        p = self.root / rel_dir
        if not p.exists():
            return []
        return sorted(
            str(f.relative_to(self.root))
            for f in p.rglob("*")
            if f.is_file()
        )

    # ----- sub 产出管理(F:合并回 vault)-----

    def write_sub_output(self, sub_id: str, content: str) -> str:
        """sub 完成任务后,产出存到 mortis-journal/sub-outputs/<sub_id>.md。

        Returns:
            相对 vault 根的路径。
        """
        rel = f"mortis-journal/sub-outputs/{sub_id}.md"
        # sub 产出头部记录来源 — 主人审阅时能识别
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
        """主人审阅通过 sub 产出。

        Args:
            rel_path: 相对 vault 根的 sub 产出路径(如 mortis-journal/sub-outputs/abc.md)
            target_rel: 合并到的目标路径。None = 保留在 journal(待后续手动合)。

        Returns:
            最终落地路径(相对 vault 根)。
        """
        entry = self.read(rel_path)
        # 剥头部注释行(以 <!-- 开头的整行),保留纯内容
        body_lines = [
            line for line in entry.content.splitlines()
            if not line.lstrip().startswith("<!--")
        ]
        body = "\n".join(body_lines).strip()
        if target_rel is None:
            # 默认:合并到 mortis-journal/notes/<sub_id>.md
            # (保留 sub 产出在 sub-outputs/ 作为 audit trail)
            sub_id = Path(rel_path).stem
            target_rel = f"mortis-journal/notes/{sub_id}.md"
        self.write(target_rel, body)
        # 标记原文件为已批准(更新 status 注释行)
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
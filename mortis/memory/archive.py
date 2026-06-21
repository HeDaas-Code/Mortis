"""Mortis memory archive — 经验归档：thread → vault 长期记忆。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from mortis.vault import Vault


@dataclass
class ArchiveEntry:
    """归档记录 — 描述一次经验如何进入 vault。"""
    thread_id: str
    source_rel: str  # thread json 路径
    target_rel: str  # 归档到的 vault 路径
    summary: str     # 经验的简短摘要（主人格生成）
    archived_at: str


class MemoryArchive:
    """记忆归档器 — 主人格决定哪些 thread 经验入 vault。"""

    def __init__(self, vault: Vault) -> None:
        self._vault = vault

    def archive_thread(
        self,
        thread_id: str,
        thread_json_path: Path,
        summary: str,
        target_rel: str | None = None,
    ) -> ArchiveEntry:
        """将 thread 经验归档到 vault。

        Args:
            thread_id: 线程 ID。
            thread_json_path: thread 的持久化文件路径。
            summary: 经验的摘要（由主人格或 owner 提供）。
            target_rel: 归档到的 vault 路径。None = 默认路径。

        Returns:
            ArchiveEntry。
        """
        if target_rel is None:
            date = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
            target_rel = f"mortis-journal/notes/{date}-{thread_id}.md"

        if not thread_json_path.exists():
            raise FileNotFoundError(f"thread file not found: {thread_json_path}")

        # 读取 thread 内容，拼成可读的笔记
        import json
        data = json.loads(thread_json_path.read_text(encoding="utf-8"))
        lines = [
            f"# 经验归档 — {thread_id}",
            "",
            f"> {summary}",
            "",
            f"**任务**: {data['task']}",
            f"**状态**: {data['status']}",
            f"**创建**: {data['created_at']}",
            "",
            "## 执行步骤",
            "",
        ]
        for step in data.get("steps", []):
            lines.append(f"### [{step['step_type']}] {step['step_id']} — {step['timestamp']}")
            lines.append(f"**输入**: {step['input'][:200]}")
            lines.append(f"**输出**: {step['output'][:200]}")
            if step.get("tool_calls"):
                lines.append(f"**工具调用**: {len(step['tool_calls'])} 次")
            lines.append("")

        if data.get("final_output"):
            lines.append("## 最终产出")
            lines.append(data["final_output"])
            lines.append("")

        lines.append(f"<!-- archived_at: {datetime.now(tz=timezone.utc).isoformat()} -->")
        lines.append(f"<!-- thread_id: {thread_id} -->")

        content = "\n".join(lines)
        self._vault.write(target_rel, content)

        return ArchiveEntry(
            thread_id=thread_id,
            source_rel=str(thread_json_path),
            target_rel=target_rel,
            summary=summary,
            archived_at=datetime.now(tz=timezone.utc).isoformat(),
        )

    def auto_archive(self, thread_json_path: Path, target_rel: str | None = None) -> ArchiveEntry:
        """自动归档 — 用 task 字段作为 summary（无主人格介入）。"""
        import json
        data = json.loads(thread_json_path.read_text(encoding="utf-8"))
        return self.archive_thread(
            thread_id=data["thread_id"],
            thread_json_path=thread_json_path,
            summary=data.get("task", "untitled"),
            target_rel=target_rel,
        )

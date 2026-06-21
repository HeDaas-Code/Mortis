"""Mortis memory session — 单次会话上下文。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import json


@dataclass
class Session:
    """单次会话上下文。

    会话 = 从 owner 启动 CLI 到退出的整个生命周期。
    一个 session 内可以有多个 thread（多个任务）。
    """
    session_id: str
    created_at: str = field(default_factory=lambda: datetime.now(tz=timezone.utc).isoformat())
    threads: list[str] = field(default_factory=list)  # thread_id 列表
    metadata: dict[str, Any] = field(default_factory=dict)

    # ----- 持久化 -----

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "threads": self.threads,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Session:
        return cls(
            session_id=data["session_id"],
            created_at=data["created_at"],
            threads=data.get("threads", []),
            metadata=data.get("metadata", {}),
        )

    def save(self, dir_path: Path) -> Path:
        """将会话持久化到磁盘。"""
        p = dir_path / f"{self.session_id}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return p

    @classmethod
    def load(cls, dir_path: Path, session_id: str) -> Session:
        """从磁盘加载会话。"""
        p = dir_path / f"{session_id}.json"
        if not p.exists():
            raise FileNotFoundError(f"session not found: {session_id}")
        return cls.from_dict(json.loads(p.read_text(encoding="utf-8")))

    def add_thread(self, thread_id: str) -> None:
        """追加一个 thread。"""
        if thread_id not in self.threads:
            self.threads.append(thread_id)

"""Mortis memory thread — 单个任务的执行历史。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import json


@dataclass
class StepRecord:
    """单个步骤的执行记录。"""
    step_id: str
    step_type: str  # think | plan | act | tool | review
    input: str
    output: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(tz=timezone.utc).isoformat())


@dataclass
class Thread:
    """单个任务的执行线程。

    包含该任务的所有步骤历史、上下文引用、最终产出。
    """
    thread_id: str
    session_id: str
    task: str  # 原始任务描述
    status: str = "active"  # active | done | discarded
    steps: list[StepRecord] = field(default_factory=list)
    context_refs: list[str] = field(default_factory=list)  # 引用的 vault 文件
    final_output: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(tz=timezone.utc).isoformat())
    completed_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    # ----- 步骤记录 -----

    def add_step(self, step: StepRecord) -> None:
        self.steps.append(step)

    def complete(self, output: str) -> None:
        self.final_output = output
        self.status = "done"
        self.completed_at = datetime.now(tz=timezone.utc).isoformat()

    def discard(self) -> None:
        self.status = "discarded"
        self.completed_at = datetime.now(tz=timezone.utc).isoformat()

    def add_context_ref(self, rel_path: str) -> None:
        if rel_path not in self.context_refs:
            self.context_refs.append(rel_path)

    # ----- 持久化 -----

    def to_dict(self) -> dict[str, Any]:
        return {
            "thread_id": self.thread_id,
            "session_id": self.session_id,
            "task": self.task,
            "status": self.status,
            "steps": [
                {
                    **s.__dict__,
                    # step_type/input/output 已经是 str/dict，timestamp 也是 str
                }
                for s in self.steps
            ],
            "context_refs": self.context_refs,
            "final_output": self.final_output,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Thread:
        steps = [StepRecord(**s) for s in data.get("steps", [])]
        return cls(
            thread_id=data["thread_id"],
            session_id=data["session_id"],
            task=data["task"],
            status=data.get("status", "active"),
            steps=steps,
            context_refs=data.get("context_refs", []),
            final_output=data.get("final_output"),
            created_at=data.get("created_at", ""),
            completed_at=data.get("completed_at"),
            metadata=data.get("metadata", {}),
        )

    def save(self, dir_path: Path) -> Path:
        """将线程持久化到磁盘。"""
        p = dir_path / f"{self.thread_id}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return p

    @classmethod
    def load(cls, dir_path: Path, thread_id: str) -> Thread:
        """从磁盘加载线程。"""
        p = dir_path / f"{thread_id}.json"
        if not p.exists():
            raise FileNotFoundError(f"thread not found: {thread_id}")
        return cls.from_dict(json.loads(p.read_text(encoding="utf-8")))

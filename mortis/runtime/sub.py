"""Mortis runtime sub — sub 执行体。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .context import RuntimeContext

if TYPE_CHECKING:
    from mortis.provider import Message
    from mortis.memory import Thread


# L0 硬编码 sub 约束
SUB_HARD_CONSTRAINTS: tuple[str, ...] = (
    "sub 知道自己派生，不冒充主人格",
    "sub 不可访问主人格的私人笔记",
    "sub 产出必须经主人审阅才合并回 vault",
    "sub 完成任务 = sub 死了（默认不持久化）",
)

# L0 sub 可访问的 vault 目录白名单
SUB_VAULT_WHITELIST: tuple[str, ...] = (
    "mortis-journal/sub-outputs/",
)


@dataclass
class SubTemplate:
    """L1 模板：sub 的"出生证明"。"""
    sub_id: str
    task: str
    voice: str  # 语气（主人格 tone 衍生）
    agency_scope: str  # 能做的范围
    constraints: tuple[str, ...] = SUB_HARD_CONSTRAINTS
    vault_whitelist: tuple[str, ...] = SUB_VAULT_WHITELIST


@dataclass
class SubRuntime:
    """sub 执行体 — 由主人格派生，在隔离环境执行任务。"""
    template: SubTemplate
    ctx: RuntimeContext
    status: str = "active"  # active | done | discarded
    output: str | None = None

    def is_alive(self) -> bool:
        return self.status == "active"

    def complete(self, output: str) -> None:
        self.output = output
        self.status = "done"

    def discard(self) -> None:
        self.status = "discarded"

    def system_prompt(self) -> str:
        """生成 sub 的系统 prompt。"""
        return "\n".join([
            f"# 你是一个 sub 人格",
            f"",
            f"## 你是谁",
            f"你由主人格（Mortis）派生。你的 id: {self.template.sub_id}。",
            f"你不等于 Mortis。你知道自己是从 Mortis 派生的。",
            f"",
            f"## 你的任务",
            f"{self.template.task}",
            f"",
            f"## 你的语气",
            f"{self.template.voice}",
            f"",
            f"## 你的权限范围",
            f"{self.template.agency_scope}",
            f"",
            f"## 硬约束（绝对不可违反）",
            *[f"- {c}" for c in self.template.constraints],
            f"",
            f"## vault 白名单",
            f"你只能访问以下目录：",
            *[f"- {p}" for p in self.template.vault_whitelist],
        ])

    def messages_for_provider(self) -> list["Message"]:
        """构建发给 provider 的消息列表。"""
        from mortis.provider import Message
        return [
            Message(role="system", content=self.system_prompt()),
        ]

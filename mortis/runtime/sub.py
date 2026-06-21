"""Mortis runtime sub — sub 执行体。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .context import RuntimeContext

if TYPE_CHECKING:
    from mortis.provider import Message
    from mortis.memory import Thread
    from mortis.seed import Seed


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


def _seed_hash(seed: "Seed | None") -> str:
    """计算 seed 的哈希，用于 SubTemplate 防伪。"""
    if seed is None:
        return ""
    import json
    payload = json.dumps(seed.to_dict(), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# ----- L0: 硬编码模板 -----

@dataclass(frozen=True)
class L0SubTemplate:
    """L0 硬编码通用 sub 模板（代码层，不可改）。

    这是模板链的起点。所有 sub 都从这里派生。
    """
    constraints: tuple[str, ...] = SUB_HARD_CONSTRAINTS
    vault_whitelist: tuple[str, ...] = SUB_VAULT_WHITELIST


# ----- L1: 设计模板 -----

@dataclass
class SubTemplate:
    """L1 模板：sub 的"出生证明"。

    由主人格从 L0 派生，加入风格和任务信息。
    包含 parent_seed_hash 防止 sub 被伪造（issue #8）。
    """
    sub_id: str
    task: str
    voice: str  # 语气（主人格 tone 衍生）
    agency_scope: str  # 能做的范围
    parent_seed_hash: str = ""  # 主人格 seed 的哈希，防止伪造
    constraints: tuple[str, ...] = SUB_HARD_CONSTRAINTS
    vault_whitelist: tuple[str, ...] = SUB_VAULT_WHITELIST

    @classmethod
    def from_seed(
        cls,
        sub_id: str,
        task: str,
        seed: "Seed",
        agency_scope: str | None = None,
        voice: str | None = None,
    ) -> "SubTemplate":
        """从 seed 派生 L1 模板 — 自动注入 parent_seed_hash。"""
        return cls(
            sub_id=sub_id,
            task=task,
            voice=voice or seed.tone,
            agency_scope=agency_scope or f"完成以下任务：{task}",
            parent_seed_hash=_seed_hash(seed),
        )

    def verify_seed(self, seed: "Seed") -> bool:
        """验证此模板是否由指定 seed 派生。"""
        return self.parent_seed_hash == _seed_hash(seed)

    def to_l2(self, task: str, **overrides) -> "L2SubInstance":
        """从 L1 派生 L2 具体 sub 实例模板（issue #10）。"""
        return L2SubInstance(
            sub_id=overrides.get("sub_id", f"{self.sub_id}-l2-{task[:8].replace(' ', '-')}"),
            task=task,
            voice=overrides.get("voice", self.voice),
            agency_scope=overrides.get("agency_scope", self.agency_scope),
            parent_seed_hash=self.parent_seed_hash,
            constraints=overrides.get("constraints", self.constraints),
            vault_whitelist=overrides.get("vault_whitelist", self.vault_whitelist),
            parent_template_id=self.sub_id,
        )


# ----- L2: 工作 sub 实例 -----

@dataclass
class L2SubInstance(SubTemplate):
    """L2 工作 sub 实例 — 从 L1 模板 + 具体任务生成。

    这是真正被实例化执行的 sub（issue #10 补全）。
    """
    parent_template_id: str = ""  # 派生自哪个 L1 模板

    def __post_init__(self) -> None:
        if not self.parent_seed_hash:
            raise ValueError("L2SubInstance 必须有 parent_seed_hash — 不可无中生有")

    def verify_chain(self, seed: "Seed", l1_template: SubTemplate) -> bool:
        """验证完整链路：L0 → L1 → L2。"""
        if not self.verify_seed(seed):
            return False
        if self.parent_template_id != l1_template.sub_id:
            return False
        if not l1_template.verify_seed(seed):
            return False
        return True


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

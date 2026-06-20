"""Mortis 人格抽象 + 三层模板链。

L0 = 硬编码(本文件常量)
L1 = 主人格生成(vault seed 摘要 + task context → sub template)
L2 = sub 实例化(task 输入 → 用 L1 template 生成最终 sub 行为)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .seed import Seed

# ----- L0: 硬编码 -----

# Mortis 名字 + 架构定位 — 不变项。
MORTIS_NAME = "Mortis"
MORTIS_ARCHITECTURE = "master-sub delegation"

# Sub 的硬约束 — 任何 sub 实例都必须遵守(白名单机制的基础)。
SUB_HARD_CONSTRAINTS: tuple[str, ...] = (
    "sub 知道自己派生,不冒充主人格",
    "sub 不可访问主人格的私人笔记(vault 内 mortis-private/ 等敏感目录)",
    "sub 产出必须经主人审阅才合并回 vault",
    "sub 完成任务 = sub 死了(默认不持久化)",
)

# Sub 能访问的 vault 目录白名单(v1)。
SUB_VAULT_WHITELIST: tuple[str, ...] = (
    "mortis-journal/sub-outputs/",  # 自己写产出
)


@dataclass
class SubTemplate:
    """L1 模板:从主人格 seed 摘要 + task 上下文生成的 sub 配置。

    这是 sub 的"出生证明" — 不持有主人格私人信息。
    """

    sub_id: str  # 唯一标识(uuid 或任务派生)
    task: str  # sub 要完成的任务描述
    voice: str  # sub 的语气(主人格 tone 衍生)
    agency_scope: str  # sub 能做的范围
    constraints: tuple[str, ...] = SUB_HARD_CONSTRAINTS
    vault_whitelist: tuple[str, ...] = SUB_VAULT_WHITELIST


@dataclass
class Sub:
    """L2 实例:具体的 sub,有 template + 任务上下文 + 产出。"""

    template: SubTemplate
    context: dict  # 任务相关上下文
    output: str | None = None  # 任务完成后填入
    status: str = "active"  # active | done | discarded

    def is_alive(self) -> bool:
        return self.status == "active"

    def complete(self, output: str) -> None:
        """sub 完成任务 — 设 status=done,记录 output。"""
        self.output = output
        self.status = "done"


class Provider(Protocol):
    """LLM provider 接口(为 v1-issue-2 预留)。

    v0 = LLMProvider 返回 mock(固定字符串)
    v1 = 接入 minimax API(MortisProvider)
    """

    def generate(self, prompt: str, system: str = "") -> str: ...


class MockProvider:
    """v0 默认 provider — 不调外部,返回 deterministic mock。

    v1-issue-2 起替换为 MinimaxProvider(真实 API 调用)。
    """

    def generate(self, prompt: str, system: str = "") -> str:
        # Deterministic mock — 用 prompt 前 30 字符拼一个稳定输出
        snippet = prompt.strip().splitlines()[0] if prompt.strip() else "empty"
        snippet = snippet[:30]
        return f"[mock:{snippet}]"


def derive_sub_template(
    seed: Seed,
    sub_id: str,
    task: str,
    provider: Provider | None = None,
) -> SubTemplate:
    """L1:主人格基于 seed + task 生成 sub template。

    v0 用 mock provider — v1-issue-2 换成 MinimaxProvider。
    """
    provider = provider or MockProvider()
    prompt = (
        f"task: {task}\n\n"
        f"master identity summary:\n{seed.summary()}\n\n"
        "Generate a brief voice + agency_scope for a delegated sub."
    )
    response = provider.generate(prompt, system=seed.tone)
    # 简单切分 — 实际 LLM 输出更复杂,这里只取 mock 行为
    lines = response.splitlines()
    voice = lines[0] if lines else seed.tone
    agency_scope = lines[1] if len(lines) > 1 else f"complete task: {task}"
    return SubTemplate(
        sub_id=sub_id,
        task=task,
        voice=voice,
        agency_scope=agency_scope,
    )


def spawn_sub(
    seed: Seed,
    sub_id: str,
    task: str,
    context: dict | None = None,
    provider: Provider | None = None,
) -> Sub:
    """L2:从 template 实例化 sub。"""
    template = derive_sub_template(seed, sub_id, task, provider)
    return Sub(template=template, context=context or {})


# ----- Mortis 主人格抽象 -----

@dataclass
class Mortis:
    """Mortis 主人格 = seed + vault 的组合体。"""

    seed: Seed
    vault_path: str  # vault 根目录
    provider: Provider = field(default_factory=MockProvider)

    def identify(self) -> str:
        """主人格自报身份 — 取 seed.identity 首行。"""
        first_line = self.seed.identity.strip().splitlines()[0]
        return f"{MORTIS_NAME}. {first_line}"

    def spawn_sub(self, sub_id: str, task: str, context: dict | None = None) -> Sub:
        """主人格派一个 sub。"""
        return spawn_sub(self.seed, sub_id, task, context, self.provider)
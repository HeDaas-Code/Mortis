"""Mortis layers — 三层模板链编排。

L0 硬编码:在 persona.py 的 SUB_HARD_CONSTRAINTS / SUB_VAULT_WHITELIST
L1 模板生成:persona.derive_sub_template(seed, sub_id, task, provider)
L2 实例化:persona.spawn_sub(seed, sub_id, task, context, provider)

本模块封装"主→sub 委派"的高层编排:
    delegate(task, sub_id=None) -> Sub
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from .persona import Mortis, Sub, SubTemplate


@dataclass
class DelegationResult:
    """主→sub 委派的最终结果 — 给主人格审阅用。"""

    sub_id: str
    task: str
    output: str
    status: str  # done | discarded
    template_voice: str  # L1 生成的 voice(给主人审"这个 sub 派得对不对")


def delegate(
    master: Mortis,
    task: str,
    sub_id: str | None = None,
    context: dict | None = None,
) -> Sub:
    """主→sub 委派一条任务。

    Args:
        master: Mortis 主人格实例
        task: sub 要完成的任务描述
        sub_id: 可选,默认 uuid4
        context: 任务相关上下文(不进 template,只进 sub 运行时)

    Returns:
        Sub 实例(status=active)。要让它"完成任务",调 sub.complete(output)。
    """
    sid = sub_id or f"sub-{uuid.uuid4().hex[:8]}"
    return master.spawn_sub(sid, task, context)


def complete_delegation(sub: Sub, output: str) -> DelegationResult:
    """sub 完成任务 — 记 output + status=done,返回主人审阅用的结果。"""
    sub.complete(output)
    return DelegationResult(
        sub_id=sub.template.sub_id,
        task=sub.template.task,
        output=output,
        status=sub.status,
        template_voice=sub.template.voice,
    )
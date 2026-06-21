"""Mortis vault review — sub 产出审阅门。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from mortis.vault.base import VaultSecurity
from mortis.vault.local import VaultAccessDenied


class ReviewDecision(str, Enum):
    """主人格对 sub 产出的审阅决定。"""
    ADOPT = "adopt"
    DISCARD = "discard"
    MERGE = "merge"
    EDIT = "edit"
    OWNER_OVERRIDE = "owner_override"


@dataclass(frozen=True)
class ReviewResult:
    """审阅结果。"""
    decision: ReviewDecision
    reason: str
    target_rel: str | None = None
    edited_content: str | None = None  # EDIT 时的新内容


class ReviewGate:
    """审阅门 — 主人在 sub 产出合并到正式 vault 前必须决策。

    三种使用方式：
    1. 自动审阅（M1）：review() 静态方法，基于内容启发式判断
    2. 主人格审阅：master_review()，主人格通过 LLM 决策
    3. Owner 强制覆盖：owner_override()，owner 直接指定决策
    """

    @staticmethod
    def review(content: str, rel_path: str) -> ReviewResult:
        """自动审阅（M1 启发式）。

        根据文件名后缀和内容标记做粗略判断。
        不够智能，生产环境应使用 master_review()。
        """
        if rel_path.endswith(".tmp") or "DRAFT" in content[:200]:
            return ReviewResult(
                decision=ReviewDecision.DISCARD,
                reason="标记为草稿或临时文件",
            )
        return ReviewResult(
            decision=ReviewDecision.ADOPT,
            reason="内容看起来是正式产出",
        )

    @staticmethod
    def master_review(
        content: str,
        rel_path: str,
        master_decision: str,
        reason: str = "",
        edited_content: str | None = None,
    ) -> ReviewResult:
        """主人格审阅 — 主人格通过 LLM 或手动决策。

        Args:
            content: sub 产出内容
            rel_path: sub 产出路径
            master_decision: 主人格的决定 ("adopt"/"discard"/"merge"/"edit")
            reason: 决定原因
            edited_content: EDIT 时修改后的内容
        """
        try:
            decision = ReviewDecision(master_decision.lower().strip())
        except ValueError:
            raise ValueError(
                f"无效的审阅决定: {master_decision!r}，"
                f"可选: {[d.value for d in ReviewDecision]}"
            )

        return ReviewResult(
            decision=decision,
            reason=reason or f"主人格决定: {decision.value}",
            target_rel=rel_path,
            edited_content=edited_content if decision == ReviewDecision.EDIT else None,
        )

    @staticmethod
    def owner_override(
        content: str,
        rel_path: str,
        decision: ReviewDecision,
        reason: str = "",
        target_rel: str | None = None,
        edited_content: str | None = None,
    ) -> ReviewResult:
        """Owner 强制覆盖 — 绕过主人格审阅，owner 直接拍板。

        用于主人格判断失误或 owner 需要紧急干预的场景。
        记录中会标记为 OWNER_OVERRIDE。
        """
        return ReviewResult(
            decision=ReviewDecision.OWNER_OVERRIDE,
            reason=f"[OWNER_OVERRIDE] {reason or 'owner 直接干预'} → 实际动作: {decision.value}",
            target_rel=target_rel or rel_path,
            edited_content=edited_content,
        )

    @staticmethod
    def apply(
        vault_entry_content: str,
        rel_path: str,
        result: ReviewResult,
        vault_write_fn,
        vault_read_fn,
        vault_discard_fn,
        vault_whitelist=None,
    ) -> str:
        """执行审阅决定 — 将 ReviewResult 落地为 vault 操作。

        Args:
            vault_entry_content: sub 产出的原始内容
            rel_path: sub 产出在 vault 内的路径
            result: ReviewResult
            vault_write_fn: callable(rel_path, content) -> str
            vault_read_fn: callable(rel_path) -> str
            vault_discard_fn: callable(rel_path) -> None
            vault_whitelist: sub 可访问的 vault 目录白名单（issue #17 修复）。
                传了则所有写操作都被强制白名单检查 — 即使 target_rel 指向白名单外
                （如 owner_override 改路径）也无法写出。

        Returns: 最终写入的 target_rel（discard 返回空字符串）

        Raises:
            VaultAccessDenied: 当 target_rel 不在 vault_whitelist 内
        """
        decision = result.decision

        # OWNER_OVERRIDE: 看实际动作
        if decision == ReviewDecision.OWNER_OVERRIDE:
            # 解析 reason 中的实际动作
            actual = result.reason.split("实际动作:")[-1].strip() if "实际动作:" in result.reason else "adopt"
            try:
                decision = ReviewDecision(actual)
            except ValueError:
                decision = ReviewDecision.ADOPT

        if decision == ReviewDecision.DISCARD:
            vault_discard_fn(rel_path)
            return ""

        # 内部：所有写操作先过白名单。target_rel 是 sub 提供的可能不可信
        # （OWNER_OVERRIDE 路径里 owner 可以传任意 rel_path），
        # 即使 vault_write_fn 本身不强制，这里也强制。
        def _safe_write(target: str, content: str) -> None:
            if vault_whitelist is not None:
                if not VaultSecurity.check_whitelist(target, vault_whitelist):
                    raise VaultAccessDenied(
                        f"ReviewGate.apply: target '{target}' 不在白名单 {vault_whitelist}"
                    )
            vault_write_fn(target, content)

        if decision == ReviewDecision.ADOPT:
            target = result.target_rel or rel_path
            _safe_write(target, vault_entry_content)
            return target

        if decision == ReviewDecision.MERGE:
            # 合并：读取已有内容 + 新内容
            target = result.target_rel or rel_path
            try:
                existing = vault_read_fn(target)
                merged = existing + "\n\n---\n\n" + vault_entry_content
            except FileNotFoundError:
                merged = vault_entry_content
            _safe_write(target, merged)
            return target

        if decision == ReviewDecision.EDIT:
            target = result.target_rel or rel_path
            content = result.edited_content or vault_entry_content
            _safe_write(target, content)
            return target

        return ""
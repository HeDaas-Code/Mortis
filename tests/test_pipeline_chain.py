"""Test pipeline chain fixes — issue #7 #8 #9 #10.

审计者: 哈尼斯 (独立第三方)
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from mortis.seed import Seed
from mortis.vault import Vault, ReviewDecision, ReviewGate, ReviewResult
from mortis.runtime import SubTemplate, L0SubTemplate, L2SubInstance, SubRuntime
from mortis.provider import MockProvider
from mortis.memory import Session, Thread
from mortis.runtime.context import RuntimeContext


# ----- #8: SubTemplate parent_seed_hash -----

class TestSeedHash:
    """#8: SubTemplate 必须携带 parent_seed_hash 防伪。"""

    def _make_seed(self) -> Seed:
        return Seed(
            identity="test", values="v", tone="t", agency="a",
            relations="r", creativity="c", mortality="m",
        )

    def test_from_seed_injects_hash(self) -> None:
        """from_seed 自动注入 parent_seed_hash。"""
        seed = self._make_seed()
        tmpl = SubTemplate.from_seed("sub-1", "do task", seed)
        assert tmpl.parent_seed_hash != ""
        assert len(tmpl.parent_seed_hash) == 16

    def test_verify_seed_correct(self) -> None:
        """verify_seed 对正确 seed 返回 True。"""
        seed = self._make_seed()
        tmpl = SubTemplate.from_seed("sub-1", "do task", seed)
        assert tmpl.verify_seed(seed) is True

    def test_verify_seed_wrong_seed(self) -> None:
        """verify_seed 对错误 seed 返回 False。"""
        seed = self._make_seed()
        tmpl = SubTemplate.from_seed("sub-1", "do task", seed)
        wrong_seed = Seed(
            identity="different", values="v", tone="t", agency="a",
            relations="r", creativity="c", mortality="m",
        )
        assert tmpl.verify_seed(wrong_seed) is False

    def test_manual_construct_without_hash_allowed(self) -> None:
        """手动构造 SubTemplate 不传 hash 不报错（兼容旧代码），但 hash 为空。"""
        tmpl = SubTemplate(sub_id="x", task="y", voice="z", agency_scope="w")
        assert tmpl.parent_seed_hash == ""


# ----- #10: L2 模板链 -----

class TestL2TemplateChain:
    """#10: L0 → L1 → L2 模板链完整。"""

    def _make_seed(self) -> Seed:
        return Seed(
            identity="test", values="v", tone="t", agency="a",
            relations="r", creativity="c", mortality="m",
        )

    def test_l0_exists(self) -> None:
        """L0SubTemplate 可实例化。"""
        l0 = L0SubTemplate()
        assert l0.constraints == (
            "sub 知道自己派生，不冒充主人格",
            "sub 不可访问主人格的私人笔记",
            "sub 产出必须经主人审阅才合并回 vault",
            "sub 完成任务 = sub 死了（默认不持久化）",
        )

    def test_l1_to_l2_derivation(self) -> None:
        """L1 模板可派生 L2 实例。"""
        seed = self._make_seed()
        l1 = SubTemplate.from_seed("sub-1", "general task", seed)
        l2 = l1.to_l2("specific task")
        assert l2.parent_template_id == l1.sub_id
        assert l2.task == "specific task"
        assert l2.parent_seed_hash == l1.parent_seed_hash

    def test_l2_requires_seed_hash(self) -> None:
        """L2 实例不可无中生有 — 必须有 parent_seed_hash。"""
        with pytest.raises(ValueError, match="parent_seed_hash"):
            L2SubInstance(
                sub_id="x", task="y", voice="z", agency_scope="w",
            )

    def test_l2_verify_chain(self) -> None:
        """L2 可验证完整链路 L0→L1→L2。"""
        seed = self._make_seed()
        l1 = SubTemplate.from_seed("sub-1", "task", seed)
        l2 = l1.to_l2("specific")
        assert l2.verify_chain(seed, l1) is True

    def test_l2_verify_chain_wrong_l1(self) -> None:
        """L2 验证链路 — 错误的 L1 返回 False。"""
        seed = self._make_seed()
        l1 = SubTemplate.from_seed("sub-1", "task", seed)
        l2 = l1.to_l2("specific")
        other_l1 = SubTemplate.from_seed("sub-2", "other", seed)
        assert l2.verify_chain(seed, other_l1) is False


# ----- #9: ReviewDecision OWNER_OVERRIDE + MERGE/EDIT -----

class TestReviewDecision:
    """#9: ReviewDecision 补全 OWNER_OVERRIDE + MERGE/EDIT 可执行。"""

    def test_owner_override_exists(self) -> None:
        """ReviewDecision 有 OWNER_OVERRIDE。"""
        assert hasattr(ReviewDecision, "OWNER_OVERRIDE")
        assert ReviewDecision.OWNER_OVERRIDE.value == "owner_override"

    def test_master_review_valid(self) -> None:
        """master_review 接受有效决定。"""
        result = ReviewGate.master_review("content", "path", "adopt", "good")
        assert result.decision == ReviewDecision.ADOPT
        assert "good" in result.reason

    def test_master_review_invalid(self) -> None:
        """master_review 拒绝无效决定。"""
        with pytest.raises(ValueError, match="无效"):
            ReviewGate.master_review("c", "p", "invalid_decision")

    def test_owner_override(self) -> None:
        """owner_override 创建带标记的结果。"""
        result = ReviewGate.owner_override(
            "content", "path", ReviewDecision.ADOPT, "owner said so",
        )
        assert result.decision == ReviewDecision.OWNER_OVERRIDE
        assert "OWNER_OVERRIDE" in result.reason

    def test_apply_adopt(self) -> None:
        """apply 执行 ADOPT — 写入 vault。"""
        with tempfile.TemporaryDirectory() as td:
            v = Vault(td)
            target = ReviewGate.apply(
                "test content", "mortis-journal/sub-outputs/x.md",
                ReviewResult(decision=ReviewDecision.ADOPT, reason="ok",
                             target_rel="mortis-journal/notes/x.md"),
                v.write, lambda r: v.read(r).content, v.discard_sub_output,
            )
            assert target == "mortis-journal/notes/x.md"
            assert v.exists("mortis-journal/notes/x.md")
            assert v.read("mortis-journal/notes/x.md").content == "test content"

    def test_apply_discard(self) -> None:
        """apply 执行 DISCARD — 删除文件。"""
        with tempfile.TemporaryDirectory() as td:
            v = Vault(td)
            v.write_sub_output("sub1", "draft")
            rel = "mortis-journal/sub-outputs/sub1.md"
            target = ReviewGate.apply(
                "draft", rel,
                ReviewResult(decision=ReviewDecision.DISCARD, reason="bad"),
                v.write, lambda r: v.read(r).content, v.discard_sub_output,
            )
            assert target == ""
            assert not v.exists(rel)

    def test_apply_merge(self) -> None:
        """apply 执行 MERGE — 合并到已有文件。"""
        with tempfile.TemporaryDirectory() as td:
            v = Vault(td)
            v.write("mortis-journal/notes/x.md", "existing")
            target = ReviewGate.apply(
                "new content", "mortis-journal/sub-outputs/x.md",
                ReviewResult(decision=ReviewDecision.MERGE, reason="append",
                             target_rel="mortis-journal/notes/x.md"),
                v.write, lambda r: v.read(r).content, v.discard_sub_output,
            )
            merged = v.read("mortis-journal/notes/x.md").content
            assert "existing" in merged
            assert "new content" in merged

    def test_apply_edit(self) -> None:
        """apply 执行 EDIT — 写入编辑后内容。"""
        with tempfile.TemporaryDirectory() as td:
            v = Vault(td)
            target = ReviewGate.apply(
                "original", "mortis-journal/sub-outputs/x.md",
                ReviewResult(decision=ReviewDecision.EDIT, reason="fixed",
                             target_rel="mortis-journal/notes/x.md",
                             edited_content="edited version"),
                v.write, lambda r: v.read(r).content, v.discard_sub_output,
            )
            assert v.read("mortis-journal/notes/x.md").content == "edited version"


# ----- #7: PipelineExecutor 调用 ReviewGate -----

class TestPipelineReviewGate:
    """#7: PipelineExecutor 委派路径必须经过 ReviewGate。"""

    def _make_ctx(self, tmpdir: str) -> RuntimeContext:
        seed = Seed(
            identity="test", values="v", tone="t", agency="a",
            relations="r", creativity="c", mortality="m",
        )
        vault = Vault(tmpdir)
        provider = MockProvider(responses=["think output", "act output"])
        session = Session(session_id="test-session")
        from datetime import datetime, timezone
        thread = Thread(
            thread_id="test-thread",
            session_id="test-session",
            task="test task",
        )
        return RuntimeContext(
            seed=seed, vault=vault, provider=provider,
            session=session, thread=thread,
        )

    def test_delegated_path_calls_review_gate(self) -> None:
        """委派路径的输出包含 ReviewGate 决策记录。"""
        from mortis.pipeline import PipelineExecutor
        from mortis.provider import MockProvider

        with tempfile.TemporaryDirectory() as td:
            ctx = self._make_ctx(td)
            ctx.provider = MockProvider(responses=[
                "I should delegate this",  # think
                "sub did the work",         # act
            ])

            executor = PipelineExecutor(ctx, verbose=False)
            # 直接调用 _run_delegated 绕过 router
            result = executor._run_delegated(ctx.thread, [])

            # 检查 steps 里有 review 步骤
            review_steps = [s for s in result.steps if s.get("step_type") == "review"]
            assert len(review_steps) > 0
            assert "ReviewGate" in review_steps[0]["output"]
            assert result.delegated is True

    def test_sub_output_in_vault(self) -> None:
        """sub 产出写入 vault sub-outputs/。"""
        from mortis.pipeline import PipelineExecutor
        from mortis.provider import MockProvider

        with tempfile.TemporaryDirectory() as td:
            ctx = self._make_ctx(td)
            ctx.provider = MockProvider(responses=[
                "think", "act output here",
            ])

            executor = PipelineExecutor(ctx, verbose=False)
            result = executor._run_delegated(ctx.thread, [])

            assert result.delegated is True
            assert result.sub_id is not None


# ----- #17: ReviewGate.apply 必须强制 vault_whitelist -----

class TestReviewGateWhitelist:
    """#17: ReviewGate.apply 的写操作必须强制 whitelist。

    防止 OWNER_OVERRIDE/MERGE/EDIT 路径下 target_rel 指向白名单外，
    把 sub 产出写到主人格的私人笔记里。
    """

    def _write_log(self) -> list[str]:
        return []

    def test_adopt_blocks_target_outside_whitelist(self) -> None:
        """ADOPT 决策：target_rel 指向白名单外 → 抛 VaultAccessDenied。"""
        from mortis.vault import VaultAccessDenied

        writes: list[str] = []
        result = ReviewResult(
            decision=ReviewDecision.ADOPT,
            reason="test",
            target_rel="私人日记/2026-06-21.md",  # 白名单外！
        )
        with pytest.raises(VaultAccessDenied) as ei:
            ReviewGate.apply(
                vault_entry_content="evil content",
                rel_path="mortis-journal/sub-outputs/sub-x.md",
                result=result,
                vault_write_fn=lambda rel, content: writes.append(rel),
                vault_read_fn=lambda rel: "x",
                vault_discard_fn=lambda rel: None,
                vault_whitelist=("mortis-journal/sub-outputs/",),
            )
        assert "私人日记" in str(ei.value)
        assert writes == []  # 没有真的写出

    def test_merge_blocks_target_outside_whitelist(self) -> None:
        """MERGE 决策：target_rel 指向白名单外 → 抛 VaultAccessDenied。"""
        from mortis.vault import VaultAccessDenied

        writes: list[tuple[str, str]] = []
        result = ReviewResult(
            decision=ReviewDecision.MERGE,
            reason="test",
            target_rel="../私人/x.md",
        )
        with pytest.raises(VaultAccessDenied):
            ReviewGate.apply(
                vault_entry_content="evil",
                rel_path="mortis-journal/sub-outputs/sub-x.md",
                result=result,
                vault_write_fn=lambda rel, content: writes.append((rel, content)),
                vault_read_fn=lambda rel: "",
                vault_discard_fn=lambda rel: None,
                vault_whitelist=("mortis-journal/sub-outputs/",),
            )
        assert writes == []

    def test_edit_blocks_target_outside_whitelist(self) -> None:
        """EDIT 决策：target_rel 指向白名单外 → 抛 VaultAccessDenied。"""
        from mortis.vault import VaultAccessDenied

        writes: list[str] = []
        result = ReviewResult(
            decision=ReviewDecision.EDIT,
            reason="test",
            target_rel="绝对路径/etc/passwd",
        )
        with pytest.raises(VaultAccessDenied):
            ReviewGate.apply(
                vault_entry_content="evil",
                rel_path="mortis-journal/sub-outputs/sub-x.md",
                result=result,
                vault_write_fn=lambda rel, content: writes.append(rel),
                vault_read_fn=lambda rel: "",
                vault_discard_fn=lambda rel: None,
                vault_whitelist=("mortis-journal/sub-outputs/",),
            )
        assert writes == []

    def test_owner_override_blocks_target_outside_whitelist(self) -> None:
        """OWNER_OVERRIDE 决策：即便 reason 里标 "实际动作: adopt"，
        target_rel 指向白名单外 → 抛 VaultAccessDenied。

        这是 issue #17 描述的核心攻击面。
        """
        from mortis.vault import VaultAccessDenied

        writes: list[str] = []
        result = ReviewResult(
            decision=ReviewDecision.OWNER_OVERRIDE,
            reason="[OWNER_OVERRIDE] owner 紧急干预 → 实际动作: adopt",
            target_rel="mortis-journal/private-notes.md",  # 不在 SUB_VAULT_WHITELIST
        )
        with pytest.raises(VaultAccessDenied) as ei:
            ReviewGate.apply(
                vault_entry_content="secret",
                rel_path="mortis-journal/sub-outputs/sub-x.md",
                result=result,
                vault_write_fn=lambda rel, content: writes.append(rel),
                vault_read_fn=lambda rel: "",
                vault_discard_fn=lambda rel: None,
                vault_whitelist=("mortis-journal/sub-outputs/",),
            )
        assert "mortis-journal/private-notes.md" in str(ei.value)
        assert writes == []

    def test_adopt_allows_target_inside_whitelist(self) -> None:
        """ADOPT 决策：target 在白名单内 → 正常写出。"""
        writes: list[tuple[str, str]] = []
        result = ReviewResult(
            decision=ReviewDecision.ADOPT,
            reason="test",
            target_rel="mortis-journal/sub-outputs/sub-final.md",
        )
        out = ReviewGate.apply(
            vault_entry_content="ok",
            rel_path="mortis-journal/sub-outputs/sub-x.md",
            result=result,
            vault_write_fn=lambda rel, content: writes.append((rel, content)),
            vault_read_fn=lambda rel: "",
            vault_discard_fn=lambda rel: None,
            vault_whitelist=("mortis-journal/sub-outputs/",),
        )
        assert out == "mortis-journal/sub-outputs/sub-final.md"
        assert writes == [("mortis-journal/sub-outputs/sub-final.md", "ok")]

    def test_discard_does_not_check_whitelist(self) -> None:
        """DISCARD 决策：discard 的是 rel_path（白名单内），不写新文件，
        所以不应该被 whitelist 卡住。"""
        discards: list[str] = []
        result = ReviewResult(
            decision=ReviewDecision.DISCARD,
            reason="trash",
        )
        out = ReviewGate.apply(
            vault_entry_content="x",
            rel_path="mortis-journal/sub-outputs/sub-bad.md",
            result=result,
            vault_write_fn=lambda rel, content: None,
            vault_read_fn=lambda rel: "",
            vault_discard_fn=lambda rel: discards.append(rel),
            vault_whitelist=("mortis-journal/sub-outputs/",),
        )
        assert out == ""
        assert discards == ["mortis-journal/sub-outputs/sub-bad.md"]

    def test_no_whitelist_means_no_extra_check(self) -> None:
        """不传 vault_whitelist → 维持原行为（向后兼容，不强制）。"""
        writes: list[str] = []
        result = ReviewResult(
            decision=ReviewDecision.ADOPT,
            reason="x",
            target_rel="任何路径.md",  # 没传 whitelist 时不检查
        )
        out = ReviewGate.apply(
            vault_entry_content="ok",
            rel_path="mortis-journal/sub-outputs/sub-x.md",
            result=result,
            vault_write_fn=lambda rel, content: writes.append(rel),
            vault_read_fn=lambda rel: "",
            vault_discard_fn=lambda rel: None,
            # 没传 vault_whitelist
        )
        assert out == "任何路径.md"
        assert writes == ["任何路径.md"]

    def test_adopt_normalizes_path_traversal(self) -> None:
        """白名单检查用归一化路径 — 'mortis-journal/sub-outputs/../private.md'
        会被识别为 'mortis-journal/private.md'，不在 SUB_VAULT_WHITELIST 内 → 拒。
        """
        from mortis.vault import VaultAccessDenied

        writes: list[str] = []
        result = ReviewResult(
            decision=ReviewDecision.ADOPT,
            reason="x",
            target_rel="mortis-journal/sub-outputs/../../private/secret.md",
        )
        with pytest.raises(VaultAccessDenied):
            ReviewGate.apply(
                vault_entry_content="x",
                rel_path="mortis-journal/sub-outputs/sub-x.md",
                result=result,
                vault_write_fn=lambda rel, content: writes.append(rel),
                vault_read_fn=lambda rel: "",
                vault_discard_fn=lambda rel: None,
                vault_whitelist=("mortis-journal/sub-outputs/",),
            )
        assert writes == []


# ----- #17: PipelineExecutor 必须把 SUB_VAULT_WHITELIST 传给 ReviewGate -----

class TestPipelinePassesWhitelist:
    """#17: PipelineExecutor._run_delegated 调用 ReviewGate.apply 时
    必须传 vault_whitelist=SUB_VAULT_WHITELIST。

    这是 owner 给 sub 委派路径的最后一道安全边界。
    """

    def test_executor_passes_sub_vault_whitelist(self) -> None:
        """通过 monkeypatch 拦截 ReviewGate.apply，检查传入了正确的白名单。"""
        from mortis.pipeline import PipelineExecutor
        from mortis.provider import MockProvider
        from mortis.runtime import SUB_VAULT_WHITELIST

        captured: dict[str, object] = {}

        import mortis.vault.review as review_mod
        original_apply = review_mod.ReviewGate.apply

        def spy_apply(*args, **kwargs):
            captured["vault_whitelist"] = kwargs.get("vault_whitelist")
            captured["kwargs"] = kwargs
            # 调用真实 apply 但用安全的 vault_write_fn
            return original_apply(*args, **kwargs)

        seed = Seed(
            identity="test", values="v", tone="t", agency="a",
            relations="r", creativity="c", mortality="m",
        )
        with tempfile.TemporaryDirectory() as td:
            vault = Vault(td)
            provider = MockProvider(responses=["think", "act"])
            from datetime import datetime, timezone
            from mortis.memory import Session, Thread

            session = Session(session_id="test-session")
            thread = Thread(thread_id="t1", session_id="s1", task="do x")
            ctx = RuntimeContext(
                seed=seed, vault=vault, provider=provider,
                session=session, thread=thread,
            )

            # 把 review_mod.ReviewGate.apply 替换成 spy
            review_mod.ReviewGate.apply = staticmethod(spy_apply)
            try:
                executor = PipelineExecutor(ctx, verbose=False)
                executor._run_delegated(thread, [])
            finally:
                review_mod.ReviewGate.apply = original_apply

        assert captured.get("vault_whitelist") == SUB_VAULT_WHITELIST, (
            f"PipelineExecutor 必须把 SUB_VAULT_WHITELIST 传给 ReviewGate.apply, "
            f"实际传了: {captured.get('vault_whitelist')}"
        )

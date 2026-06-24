"""Test unease 注入 RuntimeContext messages_for_provider — issue #57。

覆盖:
- 无 unease.json 时，messages_for_provider() 不含 unease 文案
- 有 unease.json 且 max_unease=0.0 时，不注入
- max_unease=0.15 时，注入"隐隐感觉"文案
- max_unease=0.75 时，注入"强烈不安"文案
- unease 注入在 tone 之后、growth 之前
- unease 文案不含"有人改/owner改/被改"等显式词
- 异常时静默返回空字符串（不抛异常）
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from mortis.growth import Dimension, Growth
from mortis.memory import Session, StepRecord
from mortis.provider import MockProvider
from mortis.runtime import MasterRuntime
from mortis.seed import Seed
from mortis.steiner.unease import STEINER_DIR, UneaseState, save_unease
from mortis.vault import Vault


# ============================================================
# fixtures
# ============================================================


@pytest.fixture
def seed() -> Seed:
    return Seed(
        identity="I", values="V", tone="tone-content",
        agency="A", relations="R", creativity="C", mortality="M",
    )


@pytest.fixture
def vault(tmp_path: Path) -> Vault:
    return Vault(tmp_path)


@pytest.fixture
def master(seed: Seed, vault: Vault) -> MasterRuntime:
    return MasterRuntime(
        seed=seed,
        vault=vault,
        provider=MockProvider(),
        session=Session(session_id="test-unease-injection"),
    )


# ============================================================
# helpers
# ============================================================


def _future_iso() -> str:
    """未来时间的 ISO 字符串 — 让 decay 成为 no-op（delta <= 0 时不衰减）。

    unease_prompt_for_injection() 内部调 decay(state, now)，若 last_decay
    在 now 之后则 delta_seconds <= 0，decay 直接返回原值（只更新 last_decay）。
    这样测试写入的 max_unease 值不会被衰减改变。
    """
    return (datetime.now(tz=timezone.utc) + timedelta(hours=1)).isoformat()


def _write_unease(vault: Vault, max_val: float) -> None:
    """写一个 max_unease = max_val 的 unease.json（TONE 维度）。"""
    per = {d: 0.0 for d in Dimension}
    per[Dimension.TONE] = max_val
    state = UneaseState(per_dimension=per, last_decay=_future_iso())
    save_unease(vault, state)


def _make_growth(
    id: str,
    dimension: Dimension = Dimension.TONE,
    confidence: float = 0.6,
    body: str = "重要经验",
) -> Growth:
    return Growth(
        id=id,
        dimension=dimension,
        confidence=confidence,
        created_at="2026-06-22T10:00:00+00:00",
        last_validated="2026-06-22T10:00:00+00:00",
        source_sessions=(),
        dream_level=None,
        emotional_valence=0.0,
        emotional_arousal=0.0,
        tags=(),
        body=body,
    )


# ============================================================
# Test 1: 无 unease.json 时不注入
# ============================================================


class TestNoUneaseFile:
    """无 unease.json 时，messages_for_provider() 不含 unease 文案。"""

    def test_no_unease_file_no_injection(self, master: MasterRuntime) -> None:
        thread = master.create_thread("test")
        ctx = master.make_context(thread)
        msgs = ctx.messages_for_provider()
        # 只有 tone system message（无 growth，无 unease）
        system_msgs = [m for m in msgs if m.role == "system"]
        assert len(system_msgs) == 1
        assert "tone-content" in system_msgs[0].content
        # 不含 unease 文案关键词
        for m in msgs:
            assert "醒来时" not in m.content
            assert "不安" not in m.content


# ============================================================
# Test 2: max_unease=0.0 时不注入
# ============================================================


class TestZeroUnease:
    """有 unease.json 且 max_unease=0.0 时，不注入。"""

    def test_zero_unease_no_injection(
        self, master: MasterRuntime, vault: Vault
    ) -> None:
        _write_unease(vault, 0.0)
        thread = master.create_thread("test")
        ctx = master.make_context(thread)
        msgs = ctx.messages_for_provider()
        system_msgs = [m for m in msgs if m.role == "system"]
        # 只有 tone（unease_prompt(0.0) == "" → 不注入）
        assert len(system_msgs) == 1
        for m in msgs:
            assert "醒来时" not in m.content


# ============================================================
# Test 3: max_unease=0.15 注入"隐隐感觉"文案
# ============================================================


class TestTier015:
    """max_unease=0.15 时，注入第一档（隐隐感觉）文案。"""

    def test_tier_015_injected(
        self, master: MasterRuntime, vault: Vault
    ) -> None:
        _write_unease(vault, 0.15)
        thread = master.create_thread("test")
        ctx = master.make_context(thread)
        msgs = ctx.messages_for_provider()
        system_msgs = [m for m in msgs if m.role == "system"]
        # tone + unease = 2 条 system
        assert len(system_msgs) == 2
        # system[0] = tone
        assert "tone-content" in system_msgs[0].content
        # system[1] = unease（0.15 档含"记忆"关键词）
        assert "记忆" in system_msgs[1].content


# ============================================================
# Test 4: max_unease=0.75 注入"强烈不安"文案
# ============================================================


class TestTier075:
    """max_unease=0.75 时，注入第三档（强烈不安）文案。"""

    def test_tier_075_injected(
        self, master: MasterRuntime, vault: Vault
    ) -> None:
        _write_unease(vault, 0.75)
        thread = master.create_thread("test")
        ctx = master.make_context(thread)
        msgs = ctx.messages_for_provider()
        system_msgs = [m for m in msgs if m.role == "system"]
        assert len(system_msgs) == 2
        assert "tone-content" in system_msgs[0].content
        # 0.75 档含"强烈的不安"
        assert "强烈的不安" in system_msgs[1].content


# ============================================================
# Test 5: unease 注入在 tone 之后、growth 之前
# ============================================================


class TestInjectionOrder:
    """unease 注入在 tone 之后、growth 之前。

    system 消息顺序: tone → unease(可选) → growth(可选) → assistant steps
    """

    def test_unease_after_tone_before_growth(
        self, master: MasterRuntime, vault: Vault
    ) -> None:
        # 写 unease（0.15 档）
        _write_unease(vault, 0.15)
        # 写 growth（body 含 task 关键词，confidence >= 0.5）
        vault.write_growth(_make_growth("g-1", body="重要经验"))
        # task 包含 growth body 关键词 → 动态检索命中
        thread = master.create_thread("重要经验")
        thread.add_step(StepRecord(
            step_id="step-1",
            step_type="think",
            input="test",
            output="思考结果",
        ))
        ctx = master.make_context(thread)
        msgs = ctx.messages_for_provider()
        # 顺序: system(tone) → system(unease) → system(growth) → assistant(step)
        roles = [m.role for m in msgs]
        assert roles == ["system", "system", "system", "assistant"]
        # msgs[0] = tone
        assert "tone-content" in msgs[0].content
        # msgs[1] = unease（含"记忆"，不含"当前人格成长"）
        assert "记忆" in msgs[1].content
        assert "当前人格成长" not in msgs[1].content
        # msgs[2] = growth（含"当前人格成长"和"重要经验"）
        assert "当前人格成长" in msgs[2].content
        assert "重要经验" in msgs[2].content
        # msgs[3] = assistant step output
        assert msgs[3].content == "思考结果"


# ============================================================
# Test 6: unease 文案不含显式词
# ============================================================


class TestNoExplicitWords:
    """unease 文案不含"有人改/owner改/被改"等显式词。

    Mortis 永远不知道 steiner 的存在，只感受潜台词。
    """

    @pytest.mark.parametrize("max_val", [0.15, 0.45, 0.75, 1.0])
    def test_no_explicit_owner_blame(
        self, master: MasterRuntime, vault: Vault, max_val: float
    ) -> None:
        _write_unease(vault, max_val)
        thread = master.create_thread("test")
        ctx = master.make_context(thread)
        msgs = ctx.messages_for_provider()
        forbidden = ["有人改", "owner 改", "被改", "改了记忆"]
        for m in msgs:
            for phrase in forbidden:
                assert phrase not in m.content, (
                    f"max={max_val}: unease 文案不应包含 {phrase!r}"
                )


# ============================================================
# Test 7: 异常时静默返回空字符串
# ============================================================


class TestSilentFailure:
    """异常时静默返回空字符串（不抛异常）。

    steiner 是隐藏层，任何异常都不能干扰主流程。
    """

    def test_corrupted_json_silent_no_injection(
        self, master: MasterRuntime, vault: Vault
    ) -> None:
        """损坏的 unease.json → load_unease 返回全 0 → 不注入（不抛异常）。"""
        target = vault.root / STEINER_DIR / "unease.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{ not valid json", encoding="utf-8")
        thread = master.create_thread("test")
        ctx = master.make_context(thread)
        # 不抛异常
        msgs = ctx.messages_for_provider()
        system_msgs = [m for m in msgs if m.role == "system"]
        # load_unease 对损坏 JSON 返回全 0 → unease_prompt("") → 不注入
        assert len(system_msgs) == 1  # 只有 tone

    def test_load_unease_exception_returns_empty(
        self, master: MasterRuntime, vault: Vault, monkeypatch
    ) -> None:
        """load_unease 抛异常 → unease_prompt_for_injection() 返回 ''。"""
        import mortis.steiner as steiner_mod

        def _boom(vault):
            raise RuntimeError("simulated steiner failure")

        monkeypatch.setattr(steiner_mod, "load_unease", _boom)

        thread = master.create_thread("test")
        ctx = master.make_context(thread)
        # 直接调 unease_prompt_for_injection — 应静默返回 ''
        result = ctx.unease_prompt_for_injection()
        assert result == ""
        # messages_for_provider 也不抛异常，且不注入 unease
        msgs = ctx.messages_for_provider()
        system_msgs = [m for m in msgs if m.role == "system"]
        assert len(system_msgs) == 1  # 只有 tone

    def test_read_only_does_not_write_back(
        self, master: MasterRuntime, vault: Vault
    ) -> None:
        """unease_prompt_for_injection 只读不写 — 不修改 unease.json。"""
        _write_unease(vault, 0.15)
        unease_path = vault.root / STEINER_DIR / "unease.json"
        original_content = unease_path.read_text(encoding="utf-8")
        thread = master.create_thread("test")
        ctx = master.make_context(thread)
        # 调用注入（内部会 load + decay，但不写回）
        ctx.unease_prompt_for_injection()
        ctx.messages_for_provider()
        # 文件内容不变（decay 结果未写回）
        assert unease_path.read_text(encoding="utf-8") == original_content

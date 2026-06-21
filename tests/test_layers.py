"""Test runtime — MasterRuntime / SubRuntime / PipelineExecutor。"""
from __future__ import annotations

from pathlib import Path

import pytest

from mortis.seed import Seed, load_seed, save_seed
from mortis.vault import Vault
from mortis.provider import MockProvider
from mortis.memory import Session, Thread, StepRecord
from mortis.runtime import (
    MasterRuntime,
    SubRuntime,
    SubTemplate,
    RuntimeContext,
    SUB_HARD_CONSTRAINTS,
    SUB_VAULT_WHITELIST,
    MORTIS_NAME,
)


@pytest.fixture
def seed(tmp_path: Path) -> Seed:
    return Seed(
        identity="Mortis. master of vault.",
        values="honesty first.",
        tone="short.",
        agency="Hedaas decides.",
        relations="Hedaas first.",
        creativity="structure first.",
        mortality="vault = continuity.",
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
        session=Session(session_id="test-session"),
    )


# ----- MORTIS_NAME -----

def test_mortis_name_constant() -> None:
    assert MORTIS_NAME == "Mortis"


# ----- L0 硬编码约束 -----

def test_sub_hard_constraints_include_no_ooc() -> None:
    assert any("冒充" in c or "派生" in c for c in SUB_HARD_CONSTRAINTS)


def test_sub_vault_whitelist_is_restrictive() -> None:
    assert "mortis-private" not in " ".join(SUB_VAULT_WHITELIST)
    assert "mortis-journal/sub-outputs/" in SUB_VAULT_WHITELIST


# ----- MasterRuntime -----

def test_master_identify(seed: Seed, vault: Vault, master: MasterRuntime) -> None:
    assert master.identify() == "Mortis. Mortis. master of vault."


def test_master_identify_first_line_only(seed: Seed, vault: Vault) -> None:
    m = MasterRuntime(
        seed=Seed(
            identity="line1\nline2\nline3",
            values="v", tone="t", agency="a",
            relations="r", creativity="c", mortality="m",
        ),
        vault=vault,
        provider=MockProvider(),
        session=Session(session_id="s"),
    )
    assert m.identify() == "Mortis. line1"


def test_master_read_write_vault(seed: Seed, vault: Vault, master: MasterRuntime) -> None:
    master.write_vault("test.txt", "hello world")
    assert master.read_vault("test.txt") == "hello world"


# ----- Thread 管理 -----

def test_master_create_thread(seed: Seed, vault: Vault, master: MasterRuntime) -> None:
    thread = master.create_thread("do the thing")
    assert thread.task == "do the thing"
    assert thread.status == "active"
    assert thread.thread_id.startswith("th-")


def test_master_create_thread_persists(seed: Seed, vault: Vault, master: MasterRuntime) -> None:
    thread = master.create_thread("persist test")
    thread_id = thread.thread_id
    loaded = master.get_thread(thread_id)
    assert loaded is not None
    assert loaded.task == "persist test"


def test_master_complete_thread(seed: Seed, vault: Vault, master: MasterRuntime) -> None:
    thread = master.create_thread("complete me")
    master.complete_thread(thread.thread_id, "the result")
    loaded = master.get_thread(thread.thread_id)
    assert loaded is not None
    assert loaded.status == "done"
    assert loaded.final_output == "the result"


def test_master_discard_thread(seed: Seed, vault: Vault, master: MasterRuntime) -> None:
    thread = master.create_thread("discard me")
    master.discard_thread(thread.thread_id)
    loaded = master.get_thread(thread.thread_id)
    assert loaded is not None
    assert loaded.status == "discarded"


# ----- RuntimeContext -----

def test_make_context(seed: Seed, vault: Vault, master: MasterRuntime) -> None:
    thread = master.create_thread("ctx test")
    ctx = master.make_context(thread)
    assert ctx.seed is seed
    assert ctx.vault is vault
    assert ctx.thread is thread


def test_messages_for_provider_includes_tone(seed: Seed, vault: Vault, master: MasterRuntime) -> None:
    thread = master.create_thread("msg test")
    ctx = master.make_context(thread)
    msgs = ctx.messages_for_provider()
    assert len(msgs) >= 1
    assert msgs[0].role == "system"
    assert "short" in msgs[0].content  # tone from seed


def test_messages_for_provider_reconstructs_thread_history(seed: Seed, vault: Vault, master: MasterRuntime) -> None:
    """messages_for_provider 重建 Thread 步骤历史，使后续 LLM 调用有上下文。"""
    thread = master.create_thread("build context")
    thread.add_step(StepRecord(
        step_id="step-think-1",
        step_type="think",
        input="build context",
        output="first thought: check vault",
    ))
    thread.add_step(StepRecord(
        step_id="step-plan-1",
        step_type="plan",
        input="build context",
        output="step 1: read notes",
    ))

    ctx = master.make_context(thread)
    msgs = ctx.messages_for_provider()

    assert len(msgs) >= 3
    # 第一个是 system（tone）
    assert msgs[0].role == "system"
    # 第二个是 think 输出（assistant）
    assert msgs[1].role == "assistant"
    assert "first thought" in msgs[1].content
    # 第三个是 plan 输出（assistant）
    assert msgs[2].role == "assistant"
    assert "step 1" in msgs[2].content


def test_messages_for_provider_empty_thread_only_tone(seed: Seed, vault: Vault, master: MasterRuntime) -> None:
    """空 thread 返回唯一一条 system 消息。"""
    thread = master.create_thread("fresh task")
    ctx = master.make_context(thread)
    msgs = ctx.messages_for_provider()
    assert len(msgs) == 1
    assert msgs[0].role == "system"


def test_messages_for_provider_step_types_distinguish_roles(seed: Seed, vault: Vault, master: MasterRuntime) -> None:
    """不同 step_type 都作为 assistant 角色重建，不混角色。"""
    thread = master.create_thread("role test")
    for i, step_type in enumerate(["think", "plan", "act", "review"]):
        thread.add_step(StepRecord(
            step_id=f"step-{step_type}-1",
            step_type=step_type,
            input="role test",
            output=f"{step_type} output {i}",
        ))

    ctx = master.make_context(thread)
    msgs = ctx.messages_for_provider()

    # system + 4 steps = 5 messages minimum
    assert len(msgs) == 5, f"expected 5 messages, got {len(msgs)}"
    assert msgs[0].role == "system"
    for i, msg in enumerate(msgs[1:], start=1):
        assert msg.role == "assistant", f"msg[{i}] should be assistant, got {msg.role}"


# ----- SubTemplate -----

def test_sub_template_default_constraints() -> None:
    tmpl = SubTemplate(
        sub_id="sub-x",
        task="do y",
        voice="neutral",
        agency_scope="task y",
    )
    assert tmpl.constraints == SUB_HARD_CONSTRAINTS
    assert tmpl.vault_whitelist == SUB_VAULT_WHITELIST


# ----- SubRuntime -----

def test_sub_runtime_system_prompt(seed: Seed, vault: Vault, master: MasterRuntime) -> None:
    thread = master.create_thread("sub prompt test")
    ctx = master.make_context(thread)
    sub_tmpl = SubTemplate(
        sub_id="sub-test",
        task="write a summary",
        voice="concise",
        agency_scope="write summary of the day",
    )
    sub = SubRuntime(template=sub_tmpl, ctx=ctx)
    prompt = sub.system_prompt()
    assert "sub" in prompt
    assert "Mortis" in prompt
    assert "write a summary" in prompt


def test_sub_runtime_complete(seed: Seed, vault: Vault, master: MasterRuntime) -> None:
    thread = master.create_thread("sub complete test")
    ctx = master.make_context(thread)
    sub = SubRuntime(
        template=SubTemplate(
            sub_id="sub-c",
            task="t",
            voice="v",
            agency_scope="a",
        ),
        ctx=ctx,
    )
    assert sub.is_alive()
    sub.complete("done output")
    assert not sub.is_alive()
    assert sub.output == "done output"


def test_sub_runtime_discard(seed: Seed, vault: Vault, master: MasterRuntime) -> None:
    thread = master.create_thread("sub discard test")
    ctx = master.make_context(thread)
    sub = SubRuntime(
        template=SubTemplate(
            sub_id="sub-d",
            task="t",
            voice="v",
            agency_scope="a",
        ),
        ctx=ctx,
    )
    sub.discard()
    assert sub.status == "discarded"


# ----- 旧层兼容别名（如果 migration 时需要） -----

def test_delegate_result_equivalents() -> None:
    """DelegationResult 的等价物现在在 PipelineResult 里。"""
    from mortis.pipeline import PipelineResult
    result = PipelineResult(
        thread_id="th-x",
        task="do y",
        output="done",
        steps=[],
        delegated=False,
        sub_id=None,
    )
    assert result.task == "do y"
    assert result.output == "done"
    assert result.delegated is False

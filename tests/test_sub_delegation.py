"""Tests for sub-agent delegation context passing."""

import pytest
import tempfile
from pathlib import Path

from mortis.provider.mock import MockProvider
from mortis.seed import Seed
from mortis.vault import Vault
from mortis.memory import Session
from mortis.runtime import SubTemplate, SubRuntime, RuntimeContext
from mortis.memory import Thread


def _make_seed() -> Seed:
    return Seed(
        identity="test", values="v", tone="t", agency="a",
        relations="r", creativity="c", mortality="m",
    )


def test_subtemplate_has_context_fields():
    seed = _make_seed()
    template = SubTemplate.from_seed(
        sub_id="sub-test-001",
        task="分析 identity 维度",
        seed=seed,
        master_analysis="主人格分析: identity 维度需要关注自我认知",
        context_refs=("mortis-growth/identity/identity-001.md",),
    )
    assert template.master_analysis == "主人格分析: identity 维度需要关注自我认知"
    assert template.context_refs == ("mortis-growth/identity/identity-001.md",)


def test_subtemplate_context_defaults_empty():
    seed = _make_seed()
    template = SubTemplate.from_seed(
        sub_id="sub-test-002",
        task="简单任务",
        seed=seed,
    )
    assert template.master_analysis == ""
    assert template.context_refs == ()


def test_subruntime_system_prompt_includes_context():
    seed = _make_seed()
    template = SubTemplate.from_seed(
        sub_id="sub-test-003",
        task="综合分析",
        seed=seed,
        master_analysis="需要交叉验证 identity 和 values",
        context_refs=(
            "mortis-growth/identity/identity-001.md",
            "mortis-growth/values/values-001.md",
        ),
    )
    vault_root = Path(tempfile.mkdtemp()) / "vault"
    vault_root.mkdir(parents=True)
    vault = Vault(vault_root)
    provider = MockProvider()
    session = Session(session_id="test-session")
    thread = Thread(thread_id="test-thread", session_id="test-session", task="综合分析")
    ctx = RuntimeContext(
        seed=seed, vault=vault, provider=provider,
        session=session, thread=thread,
    )
    sub = SubRuntime(template=template, ctx=ctx)
    prompt = sub.system_prompt()
    assert "主人格分析" in prompt
    assert "需要交叉验证 identity 和 values" in prompt
    assert "identity-001.md" in prompt
    assert "values-001.md" in prompt
    assert "硬约束" in prompt
    assert "vault 白名单" in prompt


def test_subruntime_system_prompt_without_context():
    seed = _make_seed()
    template = SubTemplate.from_seed(
        sub_id="sub-test-004",
        task="简单任务",
        seed=seed,
    )
    vault_root = Path(tempfile.mkdtemp()) / "vault"
    vault_root.mkdir(parents=True)
    vault = Vault(vault_root)
    provider = MockProvider()
    session = Session(session_id="test-session")
    thread = Thread(thread_id="test-thread", session_id="test-session", task="简单任务")
    ctx = RuntimeContext(
        seed=seed, vault=vault, provider=provider,
        session=session, thread=thread,
    )
    sub = SubRuntime(template=template, ctx=ctx)
    prompt = sub.system_prompt()
    assert "主人格分析" not in prompt
    assert "相关 vault 文件" not in prompt
    assert "你的任务" in prompt
    assert "硬约束" in prompt

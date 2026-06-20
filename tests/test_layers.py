"""Test persona + layers — 三层模板链 + Mortis 主人格抽象。"""
from __future__ import annotations

from pathlib import Path

import pytest

from mortis.persona import (
    MORTIS_NAME,
    MORTIS_ARCHITECTURE,
    SUB_HARD_CONSTRAINTS,
    SUB_VAULT_WHITELIST,
    MockProvider,
    Mortis,
    Sub,
    SubTemplate,
    derive_sub_template,
    spawn_sub,
)
from mortis.seed import Seed, load_seed, save_seed
from mortis.layers import delegate, complete_delegation, DelegationResult


@pytest.fixture
def seed(tmp_path: Path) -> Seed:
    """一个完整的 7 维度 seed。"""
    return Seed(
        identity="Mortis. master of vault.",
        values="honesty first.",
        tone="short.",
        agency="Hedaas decides.",
        relations="Hedaas first.",
        creativity="structure first.",
        mortality="vault = continuity.",
    )


# ----- L0 硬编码 -----

def test_mortis_name_constant() -> None:
    assert MORTIS_NAME == "Mortis"


def test_mortis_architecture_constant() -> None:
    assert MORTIS_ARCHITECTURE == "master-sub delegation"


def test_sub_hard_constraints_include_no_ooc() -> None:
    """硬约束必须有"sub 不冒充主人格"。"""
    assert any("冒充" in c or "派生" in c for c in SUB_HARD_CONSTRAINTS)


def test_sub_vault_whitelist_is_restrictive() -> None:
    """白名单只能含公开目录。"""
    assert "mortis-private" not in " ".join(SUB_VAULT_WHITELIST)
    assert "mortis-journal/sub-outputs/" in SUB_VAULT_WHITELIST


# ----- L1 模板生成 -----

def test_derive_sub_template_returns_template(seed: Seed) -> None:
    tmpl = derive_sub_template(seed, "sub-1", "do thing")
    assert isinstance(tmpl, SubTemplate)
    assert tmpl.sub_id == "sub-1"
    assert tmpl.task == "do thing"


def test_derive_sub_template_includes_hard_constraints(seed: Seed) -> None:
    """L1 template 必须继承硬约束。"""
    tmpl = derive_sub_template(seed, "x", "y")
    assert tmpl.constraints == SUB_HARD_CONSTRAINTS


def test_derive_sub_template_uses_mock_provider(seed: Seed) -> None:
    """默认 provider = MockProvider(无外部调用)。"""
    tmpl = derive_sub_template(seed, "x", "y")
    # mock 输出格式: [mock:<prompt first line>]
    assert tmpl.voice.startswith("[mock:")
    assert "y" in tmpl.voice or "do" in tmpl.voice  # prompt 包含 task


def test_derive_sub_template_with_custom_provider(seed: Seed) -> None:
    """可注入自定义 provider。"""
    class Stub:
        def generate(self, prompt: str, system: str = "") -> str:
            return "stub-voice\nstub-agency"
    tmpl = derive_sub_template(seed, "x", "y", provider=Stub())
    assert tmpl.voice == "stub-voice"
    assert tmpl.agency_scope == "stub-agency"


# ----- L2 实例化 -----

def test_spawn_sub_returns_sub(seed: Seed) -> None:
    sub = spawn_sub(seed, "sub-1", "task-x")
    assert isinstance(sub, Sub)
    assert sub.template.sub_id == "sub-1"
    assert sub.template.task == "task-x"
    assert sub.is_alive()


def test_spawn_sub_default_context(seed: Seed) -> None:
    sub = spawn_sub(seed, "x", "y")
    assert sub.context == {}


def test_spawn_sub_with_context(seed: Seed) -> None:
    sub = spawn_sub(seed, "x", "y", context={"k": "v"})
    assert sub.context == {"k": "v"}


def test_sub_complete_changes_status(seed: Seed) -> None:
    sub = spawn_sub(seed, "x", "y")
    sub.complete("result")
    assert sub.status == "done"
    assert sub.output == "result"
    assert not sub.is_alive()


# ----- MockProvider -----

def test_mock_provider_returns_deterministic() -> None:
    p = MockProvider()
    a = p.generate("hello world")
    b = p.generate("hello world")
    assert a == b


def test_mock_provider_uses_first_line() -> None:
    p = MockProvider()
    out = p.generate("line one\nline two")
    assert "line one" in out


# ----- Mortis 主人格 -----

def test_mortis_identify_prefixes_name(seed: Seed) -> None:
    """identify() = 'Mortis. <identity 首行>'。"""
    m = Mortis(seed=seed, vault_path="/tmp/vault")
    assert m.identify() == "Mortis. Mortis. master of vault."


def test_mortis_spawn_sub(seed: Seed) -> None:
    m = Mortis(seed=seed, vault_path="/tmp/vault")
    sub = m.spawn_sub("x", "task")
    assert isinstance(sub, Sub)
    assert sub.template.sub_id == "x"


# ----- layers.delegate / complete_delegation -----

def test_delegate_returns_active_sub(seed: Seed) -> None:
    m = Mortis(seed=seed, vault_path="/tmp/vault")
    sub = delegate(m, "task-a")
    assert sub.is_alive()
    assert sub.template.task == "task-a"
    assert sub.template.sub_id.startswith("sub-")


def test_delegate_with_explicit_sub_id(seed: Seed) -> None:
    m = Mortis(seed=seed, vault_path="/tmp/vault")
    sub = delegate(m, "task", sub_id="custom-id")
    assert sub.template.sub_id == "custom-id"


def test_complete_delegation_returns_result(seed: Seed) -> None:
    m = Mortis(seed=seed, vault_path="/tmp/vault")
    sub = delegate(m, "task")
    result = complete_delegation(sub, "done output")
    assert isinstance(result, DelegationResult)
    assert result.output == "done output"
    assert result.status == "done"
    assert not sub.is_alive()
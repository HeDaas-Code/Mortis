"""Test RuntimeContext × growth 集成 — issue #20 验收。

覆盖:
- search_growths 多维过滤(dimension / tag / query / min_confidence / limit)
- query 命中 body / wikilinks / tags_inline
- growth_system_prompt 格式 / 空集 / 排序
- messages_for_provider 注入位置(seed.tone → growth 摘要 → step output)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mortis.growth import Dimension, DreamLevel, Growth
from mortis.memory import Session, StepRecord
from mortis.provider import MockProvider
from mortis.runtime import (
    MasterRuntime,
    RuntimeContext,
    growth_system_prompt,
    search_growths,
)
from mortis.seed import Seed
from mortis.vault import Vault


# ----- fixtures -----


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
        session=Session(session_id="test-runtime-growth"),
    )


def _make_growth(
    id: str,
    dimension: Dimension = Dimension.TONE,
    confidence: float = 0.6,
    body: str = "public body",
    tags: tuple[str, ...] = (),
    wikilinks: tuple[str, ...] = (),
    tags_inline: tuple[str, ...] = (),
    last_validated: str = "2026-06-22T10:00:00+00:00",
) -> Growth:
    return Growth(
        id=id,
        dimension=dimension,
        confidence=confidence,
        created_at="2026-06-22T10:00:00+00:00",
        last_validated=last_validated,
        source_sessions=(),
        dream_level=None,
        emotional_valence=0.0,
        emotional_arousal=0.0,
        tags=tags,
        body=body,
        wikilinks=wikilinks,
        tags_inline=tags_inline,
    )


class _DummySession:
    """最小 Session 替身 — MasterRuntime 构造要求,本测试不真用。"""
    session_id: str = "dummy"

    def add_thread(self, tid: str) -> None:
        pass


# ============================================================
# search_growths
# ============================================================


class TestSearchByDimension:
    def test_filter_by_dimension(self, vault: Vault) -> None:
        vault.write_growth(_make_growth("g-tone-1", dimension=Dimension.TONE))
        vault.write_growth(_make_growth("g-identity-1", dimension=Dimension.IDENTITY))

        results = search_growths(vault, dimension=Dimension.TONE)
        assert len(results) == 1
        assert results[0].id == "g-tone-1"

    def test_no_filter_returns_all(self, vault: Vault) -> None:
        for i in range(3):
            vault.write_growth(_make_growth(f"g-{i}", dimension=Dimension.TONE))
        results = search_growths(vault)
        assert len(results) == 3


class TestSearchByTag:
    def test_filter_by_frontmatter_tag(self, vault: Vault) -> None:
        vault.write_growth(_make_growth("g-a", tags=("沟通策略",)))
        vault.write_growth(_make_growth("g-b", tags=("其他",)))

        results = search_growths(vault, tag="沟通策略")
        assert len(results) == 1
        assert results[0].id == "g-a"

    def test_no_match_returns_empty(self, vault: Vault) -> None:
        vault.write_growth(_make_growth("g-a", tags=("X",)))
        results = search_growths(vault, tag="Y")
        assert results == []


class TestSearchByQuery:
    def test_query_matches_body(self, vault: Vault) -> None:
        vault.write_growth(_make_growth("g-1", body="先给结论再解释"))
        vault.write_growth(_make_growth("g-2", body="先解释再给结论"))
        results = search_growths(vault, query="先给结论")
        assert [g.id for g in results] == ["g-1"]

    def test_query_matches_wikilink(self, vault: Vault) -> None:
        """wikilink 来源 — body 含 `[[xxx]]` 段(vault.read 时 Obsidian 解析抽取到 wikilinks 字段)。"""
        vault.write_growth(_make_growth("g-1", body="linked to [[session-abc]] here"))
        vault.write_growth(_make_growth("g-2", body="linked to [[session-xyz]] here"))
        results = search_growths(vault, query="abc")
        assert [g.id for g in results] == ["g-1"]

    def test_query_matches_tags_inline(self, vault: Vault) -> None:
        """tags_inline 来源 — body 含 `#xxx` 段(Obsidian 解析抽取)。"""
        vault.write_growth(_make_growth("g-1", body="this is #inlinetag content"))
        results = search_growths(vault, query="inlinetag")
        assert len(results) == 1

    def test_query_case_insensitive(self, vault: Vault) -> None:
        vault.write_growth(_make_growth("g-1", body="CamelCase Body"))
        results = search_growths(vault, query="camelcase")
        assert len(results) == 1


class TestSearchByMinConfidence:
    def test_below_threshold_excluded(self, vault: Vault) -> None:
        vault.write_growth(_make_growth("g-low", confidence=0.3))
        vault.write_growth(_make_growth("g-high", confidence=0.9))
        results = search_growths(vault, min_confidence=0.5)
        assert [g.id for g in results] == ["g-high"]

    def test_boundary_inclusive(self, vault: Vault) -> None:
        """min_confidence 用 >=(不是 >)。"""
        vault.write_growth(_make_growth("g-edge", confidence=0.5))
        results = search_growths(vault, min_confidence=0.5)
        assert len(results) == 1


class TestSearchLimit:
    def test_limit_caps_results(self, vault: Vault) -> None:
        for i in range(15):
            vault.write_growth(_make_growth(f"g-{i:02d}", confidence=0.5 + i / 100))
        results = search_growths(vault, limit=5)
        assert len(results) == 5


class TestSearchSortOrder:
    def test_sorted_by_confidence_desc(self, vault: Vault) -> None:
        vault.write_growth(_make_growth("g-low", confidence=0.3))
        vault.write_growth(_make_growth("g-high", confidence=0.9))
        vault.write_growth(_make_growth("g-mid", confidence=0.6))
        results = search_growths(vault)
        assert [g.id for g in results] == ["g-high", "g-mid", "g-low"]


# ============================================================
# growth_system_prompt
# ============================================================


class TestGrowthSystemPrompt:
    def test_empty_returns_empty_string(self) -> None:
        assert growth_system_prompt([]) == ""

    def test_with_single_growth(self, vault: Vault) -> None:
        g = _make_growth("g-tone-1", dimension=Dimension.TONE, body="先给结论。")
        prompt = growth_system_prompt([g])
        assert "## 当前人格成长" in prompt
        assert "tone" in prompt
        assert "1 条" in prompt
        assert "先给结论。" in prompt
        assert "g-tone-1" in prompt

    def test_groups_by_dimension(self, vault: Vault) -> None:
        gs = [
            _make_growth("g-t1", dimension=Dimension.TONE),
            _make_growth("g-t2", dimension=Dimension.TONE),
            _make_growth("g-i1", dimension=Dimension.IDENTITY),
        ]
        prompt = growth_system_prompt(gs)
        # tone 段 2 条 / identity 段 1 条
        assert "tone" in prompt and "2 条" in prompt
        assert "identity" in prompt and "1 条" in prompt

    def test_sort_within_dimension_by_last_validated(self) -> None:
        gs = [
            _make_growth("g-old", last_validated="2026-01-01T00:00:00+00:00"),
            _make_growth("g-new", last_validated="2026-12-31T00:00:00+00:00"),
        ]
        prompt = growth_system_prompt(gs)
        # new 应在 old 之前
        assert prompt.index("g-new") < prompt.index("g-old")


# ============================================================
# RuntimeContext 集成
# ============================================================


class TestRuntimeContextSearchGrowths:
    def test_search_growths_method_exists(
        self, master: MasterRuntime
    ) -> None:
        thread = master.create_thread("test")
        ctx = master.make_context(thread)
        assert hasattr(ctx, "search_growths")
        assert callable(ctx.search_growths)

    def test_growth_system_prompt_method_exists(
        self, master: MasterRuntime
    ) -> None:
        thread = master.create_thread("test")
        ctx = master.make_context(thread)
        assert hasattr(ctx, "growth_system_prompt")

    def test_search_returns_results(self, master: MasterRuntime, vault: Vault) -> None:
        vault.write_growth(_make_growth("g-1", dimension=Dimension.TONE))
        thread = master.create_thread("test")
        ctx = master.make_context(thread)
        results = ctx.search_growths()
        assert len(results) == 1


class TestGrowthInjectionIntoSystemMessage:
    """messages_for_provider 注入位置: seed.tone → growth 摘要 → step output"""

    def test_growth_prompt_injected_after_tone(
        self, master: MasterRuntime, vault: Vault
    ) -> None:
        vault.write_growth(_make_growth("g-1", body="关键经验"))
        # issue #59: 使用包含 growth body 关键词的 task 进行动态检索
        thread = master.create_thread("关键经验")
        ctx = master.make_context(thread)
        msgs = ctx.messages_for_provider()
        # system[0] = tone
        assert msgs[0].role == "system"
        assert "tone-content" in msgs[0].content
        # system[1] = growth 摘要
        assert msgs[1].role == "system"
        assert "当前人格成长" in msgs[1].content
        assert "关键经验" in msgs[1].content

    def test_no_growth_means_no_extra_system_message(
        self, master: MasterRuntime
    ) -> None:
        """无 growth 时,只发 tone — 不发空段。"""
        thread = master.create_thread("test")
        ctx = master.make_context(thread)
        msgs = ctx.messages_for_provider()
        # 只 1 条 system(tone),不注入空 growth 段
        system_msgs = [m for m in msgs if m.role == "system"]
        assert len(system_msgs) == 1

    def test_growth_appears_before_step_output(
        self, master: MasterRuntime, vault: Vault
    ) -> None:
        vault.write_growth(_make_growth("g-1", body="重要经验"))
        # issue #59: 使用包含 growth body 关键词的 task 进行动态检索
        thread = master.create_thread("重要经验")
        thread.add_step(StepRecord(
            step_id="step-1",
            step_type="think",
            input="test",
            output="思考结果",
        ))
        ctx = master.make_context(thread)
        msgs = ctx.messages_for_provider()
        # 顺序: system(tone) → system(growth) → assistant(step output)
        roles = [m.role for m in msgs]
        assert roles == ["system", "system", "assistant"]
        assert "重要经验" in msgs[1].content
        assert msgs[2].content == "思考结果"

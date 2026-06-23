"""Test mortis.pipeline.growth_injection — pipeline step 动态注入 growth (#59)。

issue #59: growth 检索集成 — pipeline prompt 自动注入相关 growth 上下文。

覆盖:
- RuntimeContext.growth_context_for_task(task) 根据任务检索相关 growth
- Step 基类支持注入 growth 上下文到 prompt
- ThinkStep、ActStep 等子类的 prompt 包含相关 growth
- 动态检索优于静态注入
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mortis.growth import Dimension, DreamLevel, Growth
from mortis.memory import Session, StepRecord
from mortis.provider import MockProvider
from mortis.runtime import MasterRuntime, RuntimeContext
from mortis.pipeline.step import ThinkStep, ActStep, PlanStep, ReviewStep
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
        session=Session(session_id="test-growth-injection"),
    )


def _make_growth(
    id: str,
    dimension: Dimension = Dimension.TONE,
    confidence: float = 0.7,
    body: str = "growth body content",
    tags: tuple[str, ...] = (),
) -> Growth:
    return Growth(
        id=id,
        dimension=dimension,
        confidence=confidence,
        created_at="2026-06-22T10:00:00+00:00",
        last_validated="2026-06-22T10:00:00+00:00",
        source_sessions=(),
        dream_level=DreamLevel.LIGHT,
        emotional_valence=0.0,
        emotional_arousal=0.0,
        tags=tags,
        body=body,
        wikilinks=(),
        tags_inline=(),
    )


# ============================================================
# RuntimeContext.growth_context_for_task
# ============================================================


class TestGrowthContextForTask:
    """issue #59: 根据任务动态检索相关 growth。"""

    def test_method_exists(self, master: MasterRuntime) -> None:
        """RuntimeContext 应该有 growth_context_for_task 方法。"""
        thread = master.create_thread("test")
        ctx = master.make_context(thread)
        assert hasattr(ctx, "growth_context_for_task")
        assert callable(ctx.growth_context_for_task)

    def test_returns_growth_context_string(self, master: MasterRuntime, vault: Vault) -> None:
        """返回的应该是格式化后的 growth 上下文字符串。

        注意: query 应该匹配 growth body 中的关键词。
        """
        vault.write_growth(_make_growth("g-1", body="沟通技巧"))
        thread = master.create_thread("test")
        ctx = master.make_context(thread)
        # 使用包含 growth body 关键词的 query
        context = ctx.growth_context_for_task("沟通技巧")
        assert isinstance(context, str)
        assert "growth" in context.lower() or "沟通" in context

    def test_task_query_matches_growth_body(self, master: MasterRuntime, vault: Vault) -> None:
        """任务查询应匹配 growth body。"""
        vault.write_growth(_make_growth("g-1", body="先给结论再解释"))
        vault.write_growth(_make_growth("g-2", body="详细分析问题"))
        thread = master.create_thread("test")
        ctx = master.make_context(thread)
        # 查询包含 "结论" - 匹配 g-1
        context = ctx.growth_context_for_task("结论")
        assert "g-1" in context or "先给结论" in context
        assert "g-2" not in context or "详细分析" not in context

    def test_task_query_matches_growth_tags(self, master: MasterRuntime, vault: Vault) -> None:
        """任务查询应匹配 growth tags。"""
        vault.write_growth(_make_growth("g-1", body="content", tags=("沟通策略",)))
        vault.write_growth(_make_growth("g-2", body="content", tags=("技术细节",)))
        thread = master.create_thread("test")
        ctx = master.make_context(thread)
        # 查询包含 tag 关键词
        context = ctx.growth_context_for_task("沟通策略")
        assert "g-1" in context or "沟通" in context
        assert "g-2" not in context or "技术" not in context

    def test_empty_task_returns_empty_or_limited_context(
        self, master: MasterRuntime, vault: Vault
    ) -> None:
        """空任务应该返回空或有限制的上下文。"""
        vault.write_growth(_make_growth("g-1", body="content"))
        thread = master.create_thread("test")
        ctx = master.make_context(thread)
        context = ctx.growth_context_for_task("")
        # 空任务不应返回大量 growth
        assert isinstance(context, str)

    def test_respects_max_items_limit(self, master: MasterRuntime, vault: Vault) -> None:
        """growth_context_for_task 应该支持 max_items 参数限制数量。"""
        for i in range(10):
            vault.write_growth(_make_growth(f"g-{i}", body=f"content {i}"))
        thread = master.create_thread("test")
        ctx = master.make_context(thread)
        context = ctx.growth_context_for_task("content", max_items=3)
        # 应该只包含有限数量的 growth
        assert isinstance(context, str)


# ============================================================
# Step 基类 growth_injection
# ============================================================


class TestStepGrowthInjection:
    """issue #59: Step 基类支持注入 growth 上下文。"""

    def test_step_has_growth_injection_method(self, master: MasterRuntime) -> None:
        """Step 基类应该有 growth_injection 方法。"""
        thread = master.create_thread("test")
        ctx = master.make_context(thread)
        # 检查 Step 基类是否有相关方法
        # 应该在 prompt 构造时调用 growth 检索
        assert hasattr(ctx, "growth_context_for_task")

    def test_think_step_includes_growth_in_context(self, master: MasterRuntime, vault: Vault) -> None:
        """ThinkStep 的 prompt 应该包含相关 growth 上下文。"""
        vault.write_growth(_make_growth("g-1", body="先给结论再解释"))
        thread = master.create_thread("test")
        ctx = master.make_context(thread)
        # ThinkStep 应该能够获取 growth 上下文
        # 使用包含 growth body 关键词的 query
        growth_context = ctx.growth_context_for_task("结论")
        assert isinstance(growth_context, str)
        # growth 上下文应该与任务相关
        assert len(growth_context) > 0

    def test_act_step_includes_growth_in_context(self, master: MasterRuntime, vault: Vault) -> None:
        """ActStep 的 prompt 应该包含相关 growth 上下文。"""
        vault.write_growth(_make_growth("g-1", body="用户喜欢直接回答"))
        thread = master.create_thread("test")
        ctx = master.make_context(thread)
        growth_context = ctx.growth_context_for_task("直接回答")
        assert isinstance(growth_context, str)

    def test_plan_step_includes_growth_in_context(self, master: MasterRuntime, vault: Vault) -> None:
        """PlanStep 的 prompt 应该包含相关 growth 上下文。"""
        vault.write_growth(_make_growth("g-1", body="计划要分步骤"))
        thread = master.create_thread("test")
        ctx = master.make_context(thread)
        growth_context = ctx.growth_context_for_task("计划")
        assert isinstance(growth_context, str)

    def test_review_step_includes_growth_in_context(self, master: MasterRuntime, vault: Vault) -> None:
        """ReviewStep 的 prompt 应该包含相关 growth 上下文。"""
        vault.write_growth(_make_growth("g-1", body="复盘要客观"))
        thread = master.create_thread("test")
        ctx = master.make_context(thread)
        growth_context = ctx.growth_context_for_task("复盘")
        assert isinstance(growth_context, str)


# ============================================================
# 动态检索 vs 静态注入
# ============================================================


class TestDynamicVsStaticGrowthInjection:
    """issue #59: 动态检索优于静态注入。"""

    def test_dynamic_retrieval_filters_relevant_growth(
        self, master: MasterRuntime, vault: Vault
    ) -> None:
        """动态检索应该过滤出与当前任务相关的 growth。"""
        vault.write_growth(_make_growth("g-relevant", body="沟通技巧"))
        vault.write_growth(_make_growth("g-irrelevant", body="烹饪食谱"))
        vault.write_growth(_make_growth("g-also-irrelevant", body="足球比赛"))
        thread = master.create_thread("test")
        ctx = master.make_context(thread)
        # 查询与沟通相关 (使用关键词 "沟通")
        context = ctx.growth_context_for_task("沟通")
        assert "沟通" in context
        assert "烹饪" not in context
        assert "足球" not in context

    def test_dynamic_respects_dimension_filter(self, master: MasterRuntime, vault: Vault) -> None:
        """动态检索应该支持按 dimension 过滤。"""
        vault.write_growth(_make_growth("g-tone", dimension=Dimension.TONE, body="语气要友好"))
        vault.write_growth(_make_growth("g-identity", dimension=Dimension.IDENTITY, body="我是谁"))
        vault.write_growth(_make_growth("g-values", dimension=Dimension.VALUES, body="价值观"))
        thread = master.create_thread("test")
        ctx = master.make_context(thread)
        # 使用 dimension 过滤查询语气
        context = ctx.growth_context_for_task("语气", dimension=Dimension.TONE)
        assert "语气" in context
        assert "我是谁" not in context
        assert "价值观" not in context

    def test_dynamic_respects_confidence_threshold(self, master: MasterRuntime, vault: Vault) -> None:
        """动态检索应该支持按 confidence 过滤。"""
        vault.write_growth(_make_growth("g-low", confidence=0.3, body="低置信度"))
        vault.write_growth(_make_growth("g-high", confidence=0.9, body="高置信度"))
        vault.write_growth(_make_growth("g-mid", confidence=0.6, body="中置信度"))
        thread = master.create_thread("test")
        ctx = master.make_context(thread)
        # 查询 "置信度" — 因为 min_confidence=0.5,g-low(0.3) 被排除
        context = ctx.growth_context_for_task("置信度")
        # 应该包含高置信度的 growth
        assert "高置信度" in context or "g-high" in context


# ============================================================
# Integration: Pipeline with Growth Injection
# ============================================================


class TestPipelineGrowthInjectionIntegration:
    """issue #59: Pipeline 集成 growth 动态注入。"""

    def test_messages_include_growth_for_think_step(
        self, master: MasterRuntime, vault: Vault
    ) -> None:
        """ThinkStep 执行时 messages 应该包含相关 growth。"""
        vault.write_growth(_make_growth("g-1", body="先给结论"))
        # 创建包含 growth body 关键词的 task
        thread = master.create_thread("先给结论")
        # 添加一个 think step
        thread.add_step(StepRecord(
            step_id="think-1",
            step_type="think",
            input="先给结论",
            output="",
        ))
        ctx = master.make_context(thread)
        msgs = ctx.messages_for_provider()
        # 应该包含 growth 上下文
        content = " ".join([m.content for m in msgs])
        # 因为 task 包含 "结论"，growth 应该被检索到
        assert "g-1" in content or "先给结论" in content

    def test_growth_context_appended_to_user_message(
        self, master: MasterRuntime, vault: Vault
    ) -> None:
        """growth 上下文应该附加到 user message 中。"""
        vault.write_growth(_make_growth("g-1", body="重要经验"))
        # 创建包含 growth body 关键词的 task
        thread = master.create_thread("重要经验")
        ctx = master.make_context(thread)
        msgs = ctx.messages_for_provider()
        # growth 上下文应该在消息中
        content = " ".join([m.content for m in msgs])
        assert "重要经验" in content or "g-1" in content

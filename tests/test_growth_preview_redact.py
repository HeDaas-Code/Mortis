"""Test growth preview redact — issue #85.

issue #85: messages_for_provider() 通过 growth_system_prompt(growths) 将 growth
内容注入 system prompt, body 中的 dream callout / emotion 标签 / subconscious
注释等 owner 私密字段未 redact, 可能泄漏给外部 LLM (违反 HARNESS.md '数据不外流')。

前置: issue #83 已提供共享 redact_snippet() (mortis/redact.py)。

本测试验证:
- growth_system_prompt() 对 body 调用 redact_snippet() 后, 私密字段被替换
- dream callout / emotion 标签 / subconscious 注释均被 redact
- messages_for_provider() 注入的 system prompt 不含原始私密内容
- growth_context_for_task() 返回的上下文也不含原始私密内容
- 非私密字段 (dimension, id, 公开 body 内容) 保留不变
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mortis.growth import Dimension, DreamLevel, Growth
from mortis.memory import Session, StepRecord
from mortis.provider import MockProvider
from mortis.runtime import MasterRuntime, growth_system_prompt
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
        session=Session(session_id="test-growth-preview-redact"),
    )


def _make_growth(
    id: str,
    dimension: Dimension = Dimension.TONE,
    confidence: float = 0.8,
    body: str = "public body",
    tags: tuple[str, ...] = (),
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
        wikilinks=(),
        tags_inline=(),
    )


# 私密内容标记 — 若出现在 prompt 中即视为泄漏
_SECRET_DREAM = "secret-dream-about-flying-over-mountains-9f3a7c"
_SECRET_EMOTION = "exuberant-joy-7b2e1d"
_SECRET_SUBCONSCIOUS = "i-secretly-doubt-everything-4c8f2a"


# ============================================================
# growth_system_prompt — dream callout redact
# ============================================================


class TestDreamCalloutRedacted:
    """dream callout 在 body 中注入 system prompt 前被 redact。"""

    def test_dream_callout_content_not_in_prompt(self) -> None:
        """body 含 > [!dream] callout — 原始 dream 内容不出现在 prompt 中。"""
        body = (
            f"Public growth insight.\n\n"
            f"> [!dream] {_SECRET_DREAM}\n"
            f"> The dream was vivid and emotional\n\n"
            f"This growth is about communication."
        )
        g = _make_growth("g-dream-1", body=body)
        prompt = growth_system_prompt([g])
        assert _SECRET_DREAM not in prompt, (
            f"dream callout 原文泄漏到 system prompt: {prompt!r}"
        )

    def test_dream_callout_not_leaked_when_only_callout(self) -> None:
        """body 仅含 dream callout — 原始内容不出现在 prompt 中。

        注意: _preview_body 在 `!` 处截断 (callout 语法 `[!dream]` 的 `!`),
        preview 为 '> [!' — 不含原始 dream 内容。redact 确保即使截断逻辑
        变化也不泄漏。
        """
        body = (
            f"> [!dream] {_SECRET_DREAM}\n"
            f"> continuation line\n"
        )
        g = _make_growth("g-dream-2", body=body)
        prompt = growth_system_prompt([g])
        assert _SECRET_DREAM not in prompt, (
            f"dream callout 原文泄漏到 system prompt: {prompt!r}"
        )
        assert "g-dream-2" in prompt  # id 保留

    def test_dream_callout_public_content_preserved(self) -> None:
        """dream callout 之外的公开内容保留。"""
        body = (
            "Public insight about communication.\n\n"
            f"> [!dream] {_SECRET_DREAM}\n"
            "> private continuation\n"
        )
        g = _make_growth("g-dream-3", body=body)
        prompt = growth_system_prompt([g])
        assert "Public insight about communication" in prompt
        assert _SECRET_DREAM not in prompt


# ============================================================
# growth_system_prompt — emotion 标签 redact
# ============================================================


class TestEmotionTagRedacted:
    """行内 [emotion:...] 标签在注入 system prompt 前被 redact。"""

    def test_emotion_tag_content_not_in_prompt(self) -> None:
        """body 含 [emotion:joy@0.9] — emotion 内容不出现在 prompt 中。"""
        body = f"[emotion:{_SECRET_EMOTION}@0.9] I feel great about this milestone"
        g = _make_growth("g-emo-1", body=body)
        prompt = growth_system_prompt([g])
        assert _SECRET_EMOTION not in prompt, (
            f"emotion 标签原文泄漏到 system prompt: {prompt!r}"
        )

    def test_emotion_tag_replaced_with_redacted(self) -> None:
        """emotion 标签被 [emotion:REDACTED] 替换。"""
        body = f"[emotion:{_SECRET_EMOTION}@0.9] public text here"
        g = _make_growth("g-emo-2", body=body)
        prompt = growth_system_prompt([g])
        assert "[emotion:REDACTED]" in prompt, (
            f"emotion 标签应被 [emotion:REDACTED] 替换: {prompt!r}"
        )

    def test_emotion_tag_public_content_preserved(self) -> None:
        """emotion 标签之外的公开内容保留。"""
        body = (
            f"Public milestone reached. "
            f"[emotion:{_SECRET_EMOTION}@0.8] inline emotion."
        )
        g = _make_growth("g-emo-3", body=body)
        prompt = growth_system_prompt([g])
        assert "Public milestone reached" in prompt
        assert _SECRET_EMOTION not in prompt


# ============================================================
# growth_system_prompt — subconscious 注释 redact
# ============================================================


class TestSubconsciousRedacted:
    """%%subconscious%% 注释在注入 system prompt 前被 redact。"""

    def test_subconscious_content_not_in_prompt(self) -> None:
        """body 含 %%subconscious%% — 私密注释内容不出现在 prompt 中。"""
        body = (
            f"%%subconscious%% {_SECRET_SUBCONSCIOUS} %%/subconscious%%\n"
            f"Public text about growth."
        )
        g = _make_growth("g-sub-1", body=body)
        prompt = growth_system_prompt([g])
        assert _SECRET_SUBCONSCIOUS not in prompt, (
            f"subconscious 注释原文泄漏到 system prompt: {prompt!r}"
        )

    def test_subconscious_replaced_with_redacted(self) -> None:
        """subconscious 注释被 REDACTED 占位符替换。"""
        body = (
            f"%%subconscious%% {_SECRET_SUBCONSCIOUS} %%/subconscious%%\n"
            f"public ending"
        )
        g = _make_growth("g-sub-2", body=body)
        prompt = growth_system_prompt([g])
        assert "REDACTED" in prompt, (
            f"subconscious 注释应被 REDACTED 占位符替换: {prompt!r}"
        )

    def test_sub_alias_also_redacted(self) -> None:
        """%%sub%% 短别名也被 redact。"""
        body = f"%%sub%% {_SECRET_SUBCONSCIOUS} %%/sub%% public text"
        g = _make_growth("g-sub-3", body=body)
        prompt = growth_system_prompt([g])
        assert _SECRET_SUBCONSCIOUS not in prompt
        assert "REDACTED" in prompt

    def test_subconscious_public_content_preserved(self) -> None:
        """subconscious 注释之外的公开内容保留。"""
        body = (
            f"%%subconscious%% {_SECRET_SUBCONSCIOUS} %%/subconscious%%\n"
            f"Public growth about resilience."
        )
        g = _make_growth("g-sub-4", body=body)
        prompt = growth_system_prompt([g])
        assert "Public growth about resilience" in prompt
        assert _SECRET_SUBCONSCIOUS not in prompt


# ============================================================
# growth_system_prompt — 综合场景
# ============================================================


class TestCombinedSensitivePatterns:
    """多种私密字段同时出现在 body 中 — 全部 redact。"""

    def test_all_patterns_redacted_in_single_growth(self) -> None:
        """dream callout + emotion 标签 + subconscious 注释同时出现 — 全部 redact。"""
        body = (
            f"%%subconscious%% {_SECRET_SUBCONSCIOUS} %%/subconscious%%\n\n"
            f"Public intro text.\n\n"
            f"[emotion:{_SECRET_EMOTION}@0.9] inline emotion.\n\n"
            f"> [!dream] {_SECRET_DREAM}\n"
            f"> dream continuation\n"
        )
        g = _make_growth("g-combined-1", body=body)
        prompt = growth_system_prompt([g])
        assert _SECRET_DREAM not in prompt
        assert _SECRET_EMOTION not in prompt
        assert _SECRET_SUBCONSCIOUS not in prompt
        assert "Public intro text" in prompt

    def test_multiple_growths_all_redacted(self) -> None:
        """多个 growth 各含不同私密字段 — 全部 redact。"""
        g1 = _make_growth(
            "g-multi-1",
            body=f"> [!dream] {_SECRET_DREAM}\n> continuation",
        )
        g2 = _make_growth(
            "g-multi-2",
            dimension=Dimension.IDENTITY,
            body=f"[emotion:{_SECRET_EMOTION}@0.8] public text",
        )
        g3 = _make_growth(
            "g-multi-3",
            dimension=Dimension.VALUES,
            body=f"%%subconscious%% {_SECRET_SUBCONSCIOUS} %%/subconscious%% public",
        )
        prompt = growth_system_prompt([g1, g2, g3])
        assert _SECRET_DREAM not in prompt
        assert _SECRET_EMOTION not in prompt
        assert _SECRET_SUBCONSCIOUS not in prompt


# ============================================================
# growth_system_prompt — 非私密字段保留
# ============================================================


class TestNonSensitiveFieldsPreserved:
    """redact 只作用于 body — 其他字段 (dimension, id, confidence) 不受影响。"""

    def test_dimension_still_in_prompt(self) -> None:
        """dimension 标题保留 (不被 redact 影响)。"""
        body = f"> [!dream] {_SECRET_DREAM}\n> continuation"
        g = _make_growth("g-preserve-1", dimension=Dimension.IDENTITY, body=body)
        prompt = growth_system_prompt([g])
        assert "identity" in prompt
        assert "1 条" in prompt

    def test_growth_id_still_in_prompt(self) -> None:
        """growth id 保留 (不被 redact 影响)。"""
        body = f"> [!dream] {_SECRET_DREAM}\n> continuation"
        g = _make_growth("g-preserve-2", body=body)
        prompt = growth_system_prompt([g])
        assert "g-preserve-2" in prompt

    def test_public_body_content_preserved(self) -> None:
        """body 中的公开内容保留。"""
        body = (
            "Public growth about communication skills.\n\n"
            f"> [!secret] {_SECRET_DREAM}\n"
        )
        g = _make_growth("g-preserve-3", body=body)
        prompt = growth_system_prompt([g])
        assert "Public growth about communication skills" in prompt
        assert _SECRET_DREAM not in prompt

    def test_empty_growth_after_redact_shows_placeholder(self) -> None:
        """body 全是私密内容 — redact 后 preview 显示占位符, 不泄漏原文。"""
        body = f"> [!dream] {_SECRET_DREAM}\n> all private"
        g = _make_growth("g-empty-redact", body=body)
        prompt = growth_system_prompt([g])
        assert _SECRET_DREAM not in prompt
        assert "g-empty-redact" in prompt  # id 仍在


# ============================================================
# messages_for_provider 集成 — system prompt 不含私密内容
# ============================================================


class TestMessagesForProviderRedact:
    """messages_for_provider() 注入的 system prompt 不含原始私密内容。

    验证完整链路: RuntimeContext -> growth_context_for_task ->
    growth_system_prompt -> _preview_body -> redact_snippet。
    """

    def test_dream_callout_not_in_system_prompt(
        self, master: MasterRuntime, vault: Vault
    ) -> None:
        """dream callout 内容不出现在 messages_for_provider 的 system prompt 中。"""
        body = (
            f"Public keyword for retrieval.\n\n"
            f"> [!dream] {_SECRET_DREAM}\n"
            f"> dream continuation line\n"
        )
        vault.write_growth(_make_growth("g-msg-dream", body=body))
        thread = master.create_thread("Public keyword")
        ctx = master.make_context(thread)
        msgs = ctx.messages_for_provider()
        # 拼接所有 system message 内容
        system_content = " ".join(m.content for m in msgs if m.role == "system")
        assert _SECRET_DREAM not in system_content, (
            f"dream callout 原文泄漏到 messages_for_provider: {system_content!r}"
        )

    def test_emotion_tag_not_in_system_prompt(
        self, master: MasterRuntime, vault: Vault
    ) -> None:
        """emotion 标签内容不出现在 messages_for_provider 的 system prompt 中。"""
        body = f"Retrieval keyword. [emotion:{_SECRET_EMOTION}@0.9] inline emotion."
        vault.write_growth(_make_growth("g-msg-emo", body=body))
        thread = master.create_thread("Retrieval keyword")
        ctx = master.make_context(thread)
        msgs = ctx.messages_for_provider()
        system_content = " ".join(m.content for m in msgs if m.role == "system")
        assert _SECRET_EMOTION not in system_content, (
            f"emotion 标签原文泄漏到 messages_for_provider: {system_content!r}"
        )

    def test_subconscious_not_in_system_prompt(
        self, master: MasterRuntime, vault: Vault
    ) -> None:
        """subconscious 注释内容不出现在 messages_for_provider 的 system prompt 中。"""
        body = (
            f"%%subconscious%% {_SECRET_SUBCONSCIOUS} %%/subconscious%%\n"
            f"Retrieval keyword public text."
        )
        vault.write_growth(_make_growth("g-msg-sub", body=body))
        thread = master.create_thread("Retrieval keyword")
        ctx = master.make_context(thread)
        msgs = ctx.messages_for_provider()
        system_content = " ".join(m.content for m in msgs if m.role == "system")
        assert _SECRET_SUBCONSCIOUS not in system_content, (
            f"subconscious 注释原文泄漏到 messages_for_provider: {system_content!r}"
        )

    def test_public_content_still_in_system_prompt(
        self, master: MasterRuntime, vault: Vault
    ) -> None:
        """公开内容仍出现在 system prompt 中 (redact 不误伤)。"""
        body = (
            "Public growth about resilience.\n\n"
            f"> [!dream] {_SECRET_DREAM}\n"
            f"> private dream\n"
        )
        vault.write_growth(_make_growth("g-msg-public", body=body))
        thread = master.create_thread("Public growth")
        ctx = master.make_context(thread)
        msgs = ctx.messages_for_provider()
        system_content = " ".join(m.content for m in msgs if m.role == "system")
        assert "Public growth about resilience" in system_content
        assert _SECRET_DREAM not in system_content

    def test_growth_section_header_preserved(
        self, master: MasterRuntime, vault: Vault
    ) -> None:
        """growth 段标题 + dimension 保留 (redact 只作用于 body)。"""
        body = (
            f"Retrieval keyword.\n\n"
            f"> [!dream] {_SECRET_DREAM}\n"
        )
        vault.write_growth(_make_growth("g-msg-hdr", dimension=Dimension.TONE, body=body))
        thread = master.create_thread("Retrieval keyword")
        ctx = master.make_context(thread)
        msgs = ctx.messages_for_provider()
        system_content = " ".join(m.content for m in msgs if m.role == "system")
        assert "当前人格成长" in system_content
        assert "tone" in system_content
        assert _SECRET_DREAM not in system_content


# ============================================================
# growth_context_for_task 集成 — 返回上下文不含私密内容
# ============================================================


class TestGrowthContextForTaskRedact:
    """growth_context_for_task() 返回的上下文不含原始私密内容。"""

    def test_dream_callout_not_in_context(
        self, master: MasterRuntime, vault: Vault
    ) -> None:
        """dream callout 内容不出现在 growth_context_for_task 返回值中。"""
        body = (
            f"Retrieval keyword.\n\n"
            f"> [!dream] {_SECRET_DREAM}\n"
            f"> dream continuation\n"
        )
        vault.write_growth(_make_growth("g-ctx-dream", body=body))
        thread = master.create_thread("test")
        ctx = master.make_context(thread)
        context = ctx.growth_context_for_task("Retrieval keyword")
        assert _SECRET_DREAM not in context, (
            f"dream callout 原文泄漏到 growth_context_for_task: {context!r}"
        )

    def test_emotion_tag_not_in_context(
        self, master: MasterRuntime, vault: Vault
    ) -> None:
        """emotion 标签内容不出现在 growth_context_for_task 返回值中。"""
        body = f"Retrieval keyword. [emotion:{_SECRET_EMOTION}@0.9] inline."
        vault.write_growth(_make_growth("g-ctx-emo", body=body))
        thread = master.create_thread("test")
        ctx = master.make_context(thread)
        context = ctx.growth_context_for_task("Retrieval keyword")
        assert _SECRET_EMOTION not in context, (
            f"emotion 标签原文泄漏到 growth_context_for_task: {context!r}"
        )

    def test_subconscious_not_in_context(
        self, master: MasterRuntime, vault: Vault
    ) -> None:
        """subconscious 注释内容不出现在 growth_context_for_task 返回值中。"""
        body = (
            f"%%subconscious%% {_SECRET_SUBCONSCIOUS} %%/subconscious%%\n"
            f"Retrieval keyword public text."
        )
        vault.write_growth(_make_growth("g-ctx-sub", body=body))
        thread = master.create_thread("test")
        ctx = master.make_context(thread)
        context = ctx.growth_context_for_task("Retrieval keyword")
        assert _SECRET_SUBCONSCIOUS not in context, (
            f"subconscious 注释原文泄漏到 growth_context_for_task: {context!r}"
        )

    def test_public_content_still_in_context(
        self, master: MasterRuntime, vault: Vault
    ) -> None:
        """公开内容仍出现在 growth_context_for_task 返回值中。"""
        body = (
            "Public growth about communication.\n\n"
            f"> [!dream] {_SECRET_DREAM}\n"
        )
        vault.write_growth(_make_growth("g-ctx-public", body=body))
        thread = master.create_thread("test")
        ctx = master.make_context(thread)
        context = ctx.growth_context_for_task("Public growth")
        assert "Public growth about communication" in context
        assert _SECRET_DREAM not in context

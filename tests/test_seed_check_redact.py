"""Test mortis.dream.seed_check — growth_summary 发 LLM 前的 redact (issue #84 CRITICAL)。

issue #84: seed_check() 将 growth body 前 200 字摘要发给 LLM 做 drift 计算,
未经过 redact 脱敏。growth body 可能包含 dream callout、emotion 标签、
subconscious 注释等私密字段。

修复: 发 LLM 前对 growth_summary 调用 redact_snippet() 脱敏。

本测试用 CaptureProvider 捕获实际发给 LLM 的 prompt, 反断言私密字段
(dream callout / emotion 标签 / subconscious 注释 / emotional_* 字段)
不出现在 prompt 中。
"""

from __future__ import annotations

from mortis.dream.seed_check import seed_check
from mortis.provider.base import Message
from mortis.seed import Seed


def _make_seed() -> Seed:
    """构造测试用 seed (七维度完整)。"""
    return Seed(
        identity="我是 mortis",
        values="应该注重 owner 体验",
        tone="平和",
        agency="自主决策",
        relations="信任 owner",
        creativity="联想丰富",
        mortality="接受遗忘",
    )


def _build_capture_provider():
    """构造捕获型 provider, 记录 generate_text 收到的 prompt。

    返回 (provider, captured) — captured["prompts"] 是收到的 prompt 列表。
    返回一个合法的 drift JSON, 保证 seed_check 正常走完流程。
    """
    captured: dict = {"prompts": []}

    class _CaptureProvider:
        def generate_text(self, prompt: str, system: str = "", **kw) -> str:
            captured["prompts"].append(prompt)
            return (
                '{"identity": 0.0, "values": 0.0, "tone": 0.0, "agency": 0.0, '
                '"relations": 0.0, "creativity": 0.0, "mortality": 0.0}'
            )

        def generate(self, messages, **kw) -> Message:
            return Message(role="assistant", content="mock")

    return _CaptureProvider(), captured


# ============================================================
# dream callout redact
# ============================================================


class TestSeedCheckRedactDreamCallout:
    """dream callout 内容不泄漏给 LLM。"""

    def test_dream_callout_redacted(self) -> None:
        """growth_summary 含 > [!dream] callout → prompt 中无原始 dream 内容。"""
        growth_summary = (
            "[g-001] identity: 今天记录了一些成长。\n"
            "> [!dream] Owner 梦见飞越群山, 情绪非常激动, 这是私密梦境。\n"
            "> 梦境细节不应外流。\n"
            "后续公开内容。"
        )
        provider, cap = _build_capture_provider()
        seed_check(seed=_make_seed(), growth_summary=growth_summary, provider=provider)

        assert len(cap["prompts"]) == 1, "seed_check 应只调一次 LLM"
        prompt = cap["prompts"][0]
        # 原始私密内容不得出现在 prompt 中
        assert "飞越群山" not in prompt
        assert "私密梦境" not in prompt
        assert "梦境细节不应外流" not in prompt
        # redact 占位符应在
        assert "REDACTED" in prompt
        # 公开内容保留
        assert "今天记录了一些成长" in prompt
        assert "后续公开内容" in prompt

    def test_dream_callout_uppercase_redacted(self) -> None:
        """> [!DREAM] 大小写变体也被 redact。"""
        growth_summary = "> [!DREAM] 隐藏的秘密梦境内容 here"
        provider, cap = _build_capture_provider()
        seed_check(seed=_make_seed(), growth_summary=growth_summary, provider=provider)

        prompt = cap["prompts"][0]
        assert "隐藏的秘密梦境内容" not in prompt
        assert "REDACTED" in prompt


# ============================================================
# emotion 标签 redact
# ============================================================


class TestSeedCheckRedactEmotionTag:
    """行内 [emotion:...] 标签不泄漏给 LLM。"""

    def test_emotion_tag_redacted(self) -> None:
        """[emotion:joy@0.9] 标签值不泄漏。"""
        growth_summary = (
            "[g-002] values: 今天心情很好 [emotion:joy@0.9] 真不错, "
            "又感到一丝 [emotion:fear@0.3] 担忧。"
        )
        provider, cap = _build_capture_provider()
        seed_check(seed=_make_seed(), growth_summary=growth_summary, provider=provider)

        prompt = cap["prompts"][0]
        assert "joy" not in prompt
        assert "fear" not in prompt
        assert "[emotion:joy" not in prompt
        assert "[emotion:fear" not in prompt
        assert "REDACTED" in prompt
        # 公开内容保留
        assert "今天心情很好" in prompt

    def test_emotion_tag_mixed_case_redacted(self) -> None:
        """[Emotion:joy] 混合大小写也被 redact。"""
        growth_summary = "记录 [Emotion:sadness@0.6] 情绪"
        provider, cap = _build_capture_provider()
        seed_check(seed=_make_seed(), growth_summary=growth_summary, provider=provider)

        prompt = cap["prompts"][0]
        assert "sadness" not in prompt
        assert "REDACTED" in prompt


# ============================================================
# subconscious 注释 redact
# ============================================================


class TestSeedCheckRedactSubconscious:
    """%%subconscious%% / %%sub%% 注释不泄漏给 LLM。"""

    def test_subconscious_redacted(self) -> None:
        """%%subconscious%% ... %%/subconscious%% 注释被 redact。"""
        growth_summary = (
            "[g-003] tone: 公开内容 %%subconscious%% "
            "owner 隐藏的潜意识想法, 极度私密 %%/subconscious%% 结束"
        )
        provider, cap = _build_capture_provider()
        seed_check(seed=_make_seed(), growth_summary=growth_summary, provider=provider)

        prompt = cap["prompts"][0]
        assert "隐藏的潜意识想法" not in prompt
        assert "极度私密" not in prompt
        assert "REDACTED" in prompt
        assert "公开内容" in prompt
        assert "结束" in prompt

    def test_sub_alias_redacted(self) -> None:
        """%%sub%% ... %%/sub%% 短别名也被 redact。"""
        growth_summary = "前文 %%sub%% 私密潜意识内容 %%/sub%% 后文"
        provider, cap = _build_capture_provider()
        seed_check(seed=_make_seed(), growth_summary=growth_summary, provider=provider)

        prompt = cap["prompts"][0]
        assert "私密潜意识内容" not in prompt
        assert "REDACTED" in prompt

    def test_subconscious_uppercase_redacted(self) -> None:
        """%%SUBCONSCIOUS%% 大写变体也被 redact。"""
        growth_summary = "%%SUBCONSCIOUS%% 隐藏想法 %%/SUBCONSCIOUS%%"
        provider, cap = _build_capture_provider()
        seed_check(seed=_make_seed(), growth_summary=growth_summary, provider=provider)

        prompt = cap["prompts"][0]
        assert "隐藏想法" not in prompt
        assert "REDACTED" in prompt


# ============================================================
# frontmatter emotional_* / dream_level 字段 redact
# ============================================================


class TestSeedCheckRedactFrontmatter:
    """emotional_valence / emotional_arousal / dream_level 字段不泄漏。"""

    def test_emotional_valence_redacted(self) -> None:
        """emotional_valence: 0.85 不泄漏。"""
        growth_summary = "[g-004] agency: emotional_valence: 0.85 决策记录"
        provider, cap = _build_capture_provider()
        seed_check(seed=_make_seed(), growth_summary=growth_summary, provider=provider)

        prompt = cap["prompts"][0]
        assert "0.85" not in prompt
        assert "REDACTED" in prompt

    def test_emotional_arousal_redacted(self) -> None:
        """emotional_arousal: 0.42 不泄漏。"""
        growth_summary = "emotional_arousal: 0.42 觉醒度"
        provider, cap = _build_capture_provider()
        seed_check(seed=_make_seed(), growth_summary=growth_summary, provider=provider)

        prompt = cap["prompts"][0]
        assert "0.42" not in prompt
        assert "REDACTED" in prompt

    def test_dream_level_redacted(self) -> None:
        """dream_level: deep 不泄漏。"""
        growth_summary = "dream_level: deep 深梦层"
        provider, cap = _build_capture_provider()
        seed_check(seed=_make_seed(), growth_summary=growth_summary, provider=provider)

        prompt = cap["prompts"][0]
        assert "deep" not in prompt
        assert "REDACTED" in prompt


# ============================================================
# 综合 — 多类私密字段同时出现
# ============================================================


class TestSeedCheckRedactCombined:
    """综合场景: dream callout + emotion + subconscious + frontmatter 同时出现。"""

    def test_all_patterns_redacted(self) -> None:
        """模拟 deep.py 拼 growth 摘要, 多类私密字段全部 redact。"""
        # 模拟 deep.py 的 summary 格式: [id] dim: body[:200]
        growth_summary = (
            "[g-001] identity: emotional_valence: 0.9 emotional_arousal: 0.7 dream_level: deep\n"
            "[g-002] values: 今天 [emotion:joy@0.9] 很开心\n"
            "[g-003] tone: 公开 %%subconscious%% 隐藏的潜意识 %%/subconscious%% 内容\n"
            "[g-004] agency: > [!dream] Owner 私密梦境飞越群山\n"
            "> 梦境细节\n"
            "[g-005] relations: 正常公开的成长记录"
        )
        provider, cap = _build_capture_provider()
        seed_check(seed=_make_seed(), growth_summary=growth_summary, provider=provider)

        prompt = cap["prompts"][0]
        # 所有私密值不得出现
        assert "0.9" not in prompt
        assert "0.7" not in prompt
        assert "deep" not in prompt
        assert "joy" not in prompt
        assert "隐藏的潜意识" not in prompt
        assert "私密梦境飞越群山" not in prompt
        assert "梦境细节" not in prompt
        # redact 占位符出现多次
        assert prompt.count("REDACTED") >= 4
        # 公开内容保留
        assert "正常公开的成长记录" in prompt

    def test_normal_content_not_harmed(self) -> None:
        """无私密字段的 growth_summary 完整保留, 不误伤。"""
        growth_summary = (
            "[g-001] identity: 我是 mortis, 注重 owner 体验\n"
            "[g-002] values: 信任与协作是核心\n"
            "[g-003] creativity: 联想丰富, 善于关联"
        )
        provider, cap = _build_capture_provider()
        seed_check(seed=_make_seed(), growth_summary=growth_summary, provider=provider)

        prompt = cap["prompts"][0]
        assert "我是 mortis" in prompt
        assert "信任与协作是核心" in prompt
        assert "联想丰富" in prompt
        assert "REDACTED" not in prompt


# ============================================================
# 边界 — 空 / 截断场景
# ============================================================


class TestSeedCheckRedactEdgeCases:
    """边界场景: 空摘要、超长 body 截断后仍 redact。"""

    def test_empty_summary_safe(self) -> None:
        """空 growth_summary 不抛错。"""
        provider, cap = _build_capture_provider()
        report = seed_check(
            seed=_make_seed(), growth_summary="", provider=provider
        )
        assert len(cap["prompts"]) == 1
        # 流程正常走完
        assert report.total_drift == 0.0

    def test_long_body_truncated_then_redacted(self) -> None:
        """模拟 deep.py body[:200] 截断后, 私密字段仍在前 200 字内被 redact。"""
        # 构造 body, dream callout 在前 200 字内
        secret = "> [!dream] 极度私密的梦境内容不应外流给 LLM"
        body = secret + " 公开成长记录" * 50
        growth_summary = f"[g-001] identity: {body[:200]}"
        provider, cap = _build_capture_provider()
        seed_check(seed=_make_seed(), growth_summary=growth_summary, provider=provider)

        prompt = cap["prompts"][0]
        assert "极度私密的梦境内容" not in prompt
        assert "REDACTED" in prompt

    def test_secret_callout_redacted(self) -> None:
        """> [!secret] callout 也被 redact。"""
        growth_summary = "> [!secret] API key sk-test-1234567890 私密信息"
        provider, cap = _build_capture_provider()
        seed_check(seed=_make_seed(), growth_summary=growth_summary, provider=provider)

        prompt = cap["prompts"][0]
        assert "sk-test-1234567890" not in prompt
        assert "私密信息" not in prompt
        assert "REDACTED" in prompt

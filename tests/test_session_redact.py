"""Test session redact — dream.associate + reflect.score_emotion 发 LLM 前 redact。

issue #86: 两个 LLM 调用点将 session 全文发给外部 LLM, 未 redact:
1. reflect/emotion.py 的 score_emotion() — 发 session 全文给 LLM 做情绪打分
2. dream/associate.py 的 associate() — 发 recall_texts (session 内容) 给 LLM 找模式

前置: mortis/redact.py 共享模块 (issue #83) 提供 redact_snippet()。

本测试用 CaptureProvider 模式: 捕获 generate_text 实际收到的 prompt,
反断言 owner 私密字段 (dream callouts / emotion 标签 / subconscious /
emotional_*) 不在其中, 验证 '数据不外流' 原则 (HARNESS.md)。
"""

from __future__ import annotations

import pytest

from mortis.dream.associate import associate
from mortis.reflect.emotion import clear_cache, score_emotion

# ============================================================
# fixtures
# ============================================================


@pytest.fixture(autouse=True)
def _reset_emotion_cache() -> None:
    """每个测试前后清空 emotion module-level 缓存, 避免跨测试污染。

    score_emotion 按 session_path 缓存, 若不清空, 同 path 第二次调用
    会命中缓存而不调 provider, 导致 CaptureProvider 捕不到 prompt。
    """
    clear_cache()
    yield
    clear_cache()


# ============================================================
# CaptureProvider — 捕获发给 LLM 的 prompt
# ============================================================


def _build_emotion_capture_provider():
    """构造 provider, 捕获 generate_text 收到的 prompt, 返回合法 emotion JSON。

    score_emotion 期望 LLM 输出 {"valence": <num>, "arousal": <num>}。
    """
    captured: dict[str, list[str]] = {"prompts": []}

    class _CaptureProvider:
        def generate_text(self, prompt, system="", **kw):
            captured["prompts"].append(prompt)
            return '{"valence": 0.3, "arousal": 0.6}'

        def generate(self, messages, **kw):
            from mortis.provider.base import Message

            return Message(role="assistant", content='{"valence": 0.3, "arousal": 0.6}')

    return _CaptureProvider(), captured


def _build_associate_capture_provider():
    """构造 provider, 捕获 generate_text 收到的 prompt, 返回合法 associate JSON。

    associate 期望 LLM 输出 {"body": "...", "tags": ["..."]}。
    """
    captured: dict[str, list[str]] = {"prompts": []}

    class _CaptureProvider:
        def generate_text(self, prompt, system="", **kw):
            captured["prompts"].append(prompt)
            return '{"body": "owner 注重简洁", "tags": ["简洁"]}'

        def generate(self, messages, **kw):
            from mortis.provider.base import Message

            return Message(
                role="assistant",
                content='{"body": "owner 注重简洁", "tags": ["简洁"]}',
            )

    return _CaptureProvider(), captured


# ============================================================
# score_emotion — 发 LLM 前必须 redact
# ============================================================


class TestScoreEmotionRedact:
    """issue #86: score_emotion() 发给 LLM 的 prompt 中不含 owner 私密字段。

    score_emotion 把 session 全文拼进 prompt 发给外部 LLM 做情绪打分。
    若 session 含 dream callouts / emotion 标签 / subconscious / emotional_*,
    必须先 redact 再发, 否则违反 HARNESS.md '数据不外流' 原则。
    """

    def test_redacts_dream_callout(self) -> None:
        """dream callout 内容不泄漏给 LLM (issue #86 核心断言)。"""
        session_text = (
            "今天的公开总结。\n\n"
            "> [!dream] owner 最深层的秘密飞行梦境, 飞越群山\n"
            "> 情绪非常激动\n\n"
            "公开正文。"
        )
        provider, cap = _build_emotion_capture_provider()
        score_emotion(provider, "sessions/2026-06-22/s1", session_text)
        assert cap["prompts"], "应捕获到发给 LLM 的 prompt"
        prompt = cap["prompts"][0]
        # 核心: 原始 dream callout 内容不在 prompt 中
        assert "最深层的秘密飞行梦境" not in prompt
        assert "飞越群山" not in prompt
        assert "情绪非常激动" not in prompt
        # redact 占位符应在
        assert "REDACTED" in prompt
        # 非私密内容保留
        assert "今天的公开总结" in prompt
        assert "公开正文" in prompt

    def test_redacts_emotion_tag(self) -> None:
        """行内 emotion 标签值不泄漏给 LLM。"""
        session_text = "今天很开心 [emotion:joy@0.9] 真好, 继续工作"
        provider, cap = _build_emotion_capture_provider()
        score_emotion(provider, "s1", session_text)
        prompt = cap["prompts"][0]
        assert "joy" not in prompt
        assert "[emotion:joy" not in prompt
        assert "REDACTED" in prompt
        assert "继续工作" in prompt

    def test_redacts_subconscious(self) -> None:
        """subconscious 注释不泄漏给 LLM。"""
        session_text = (
            "公开内容 %%subconscious%% 隐藏的潜意识想法 %%/subconscious%% 结束"
        )
        provider, cap = _build_emotion_capture_provider()
        score_emotion(provider, "s1", session_text)
        prompt = cap["prompts"][0]
        assert "隐藏的潜意识想法" not in prompt
        assert "REDACTED" in prompt
        assert "公开内容" in prompt

    def test_redacts_emotional_valence(self) -> None:
        """frontmatter emotional_valence 值不泄漏给 LLM。"""
        session_text = "---\nemotional_valence: 0.85\n---\n正文内容"
        provider, cap = _build_emotion_capture_provider()
        score_emotion(provider, "s1", session_text)
        prompt = cap["prompts"][0]
        assert "0.85" not in prompt
        assert "REDACTED" in prompt

    def test_redacts_all_combined(self) -> None:
        """综合: 多类私密字段同时出现, 全部 redact。"""
        session_text = (
            "---\nemotional_valence: 0.9\nemotional_arousal: 0.7\n---\n\n"
            "公开开头。\n\n"
            "[emotion:joy@0.9] 行内情绪\n\n"
            "%%subconscious%% 私密想法 %%/subconscious%%\n\n"
            "> [!dream] 秘密梦境内容\n"
            "> 更多梦境\n\n"
            "正常结尾。"
        )
        provider, cap = _build_emotion_capture_provider()
        score_emotion(provider, "s1", session_text)
        prompt = cap["prompts"][0]
        assert "0.9" not in prompt
        assert "0.7" not in prompt
        assert "joy" not in prompt
        assert "私密想法" not in prompt
        assert "秘密梦境内容" not in prompt
        assert "更多梦境" not in prompt
        assert prompt.count("REDACTED") >= 3
        assert "公开开头" in prompt
        assert "正常结尾" in prompt

    def test_redacts_uppercase_variants(self) -> None:
        """大小写变体也 redact (callout / 标签语法本身大小写不敏感)。"""
        session_text = "> [!DREAM] UPPER SECRET\n[Emotion:joy] mixed case"
        provider, cap = _build_emotion_capture_provider()
        score_emotion(provider, "s1", session_text)
        prompt = cap["prompts"][0]
        assert "UPPER SECRET" not in prompt
        assert "joy" not in prompt
        assert "REDACTED" in prompt

    def test_normal_text_passes_through(self) -> None:
        """非私密内容正常发给 LLM (不误伤)。"""
        session_text = "今天完成了项目里程碑, 感觉很有成就感。继续推进下一步。"
        provider, cap = _build_emotion_capture_provider()
        score_emotion(provider, "s1", session_text)
        prompt = cap["prompts"][0]
        assert "完成了项目里程碑" in prompt
        assert "REDACTED" not in prompt

    def test_still_returns_valid_score(self) -> None:
        """redact 不影响 score_emotion 正常返回 (valence, arousal)。"""
        session_text = "> [!dream] 秘密\n公开内容"
        provider, cap = _build_emotion_capture_provider()
        v, a = score_emotion(provider, "s1", session_text)
        assert v == 0.3
        assert a == 0.6


# ============================================================
# associate — 发 LLM 前必须 redact
# ============================================================


class TestAssociateRedact:
    """issue #86: associate() 发给 LLM 的 prompt 中不含 owner 私密字段。

    associate 把多条 recall_text (session 内容) 拼进 prompt 发给外部 LLM
    找共同模式。若 session 含 dream callouts / emotion 标签 / subconscious /
    emotional_*, 必须先逐条 redact 再发。
    """

    def test_redacts_emotion_tag(self) -> None:
        """emotion 标签值不泄漏给 LLM (issue #86 核心断言)。"""
        sessions = ["今天很开心 [emotion:joy@0.9] 真好, 继续工作"]
        provider, cap = _build_associate_capture_provider()
        associate(provider, sessions)
        assert cap["prompts"], "应捕获到发给 LLM 的 prompt"
        prompt = cap["prompts"][0]
        # 核心: 原始 emotion 标签不在 prompt 中
        assert "joy" not in prompt
        assert "[emotion:joy" not in prompt
        assert "REDACTED" in prompt
        assert "继续工作" in prompt

    def test_redacts_dream_callout(self) -> None:
        """dream callout 内容不泄漏给 LLM。"""
        sessions = [
            "公开总结\n> [!dream] owner 最深层的秘密飞行梦境\n> 飞越群山\n公开结尾"
        ]
        provider, cap = _build_associate_capture_provider()
        associate(provider, sessions)
        prompt = cap["prompts"][0]
        assert "最深层的秘密飞行梦境" not in prompt
        assert "飞越群山" not in prompt
        assert "REDACTED" in prompt
        assert "公开总结" in prompt
        assert "公开结尾" in prompt

    def test_redacts_subconscious(self) -> None:
        """subconscious 注释不泄漏给 LLM。"""
        sessions = ["公开 %%subconscious%% 隐藏想法 %%/subconscious%% 结束"]
        provider, cap = _build_associate_capture_provider()
        associate(provider, sessions)
        prompt = cap["prompts"][0]
        assert "隐藏想法" not in prompt
        assert "REDACTED" in prompt
        assert "公开" in prompt

    def test_redacts_emotional_valence(self) -> None:
        """frontmatter emotional_valence 值不泄漏给 LLM。"""
        sessions = ["---\nemotional_valence: 0.85\n---\n正文"]
        provider, cap = _build_associate_capture_provider()
        associate(provider, sessions)
        prompt = cap["prompts"][0]
        assert "0.85" not in prompt
        assert "REDACTED" in prompt

    def test_redacts_each_session_independently(self) -> None:
        """多条 session 逐条 redact — 每条的私密字段都不泄漏。"""
        sessions = [
            "session1 [emotion:joy] 开心",
            "session2 > [!dream] 秘密梦境",
            "session3 %%sub%% 隐藏 %%/sub%% 结束",
        ]
        provider, cap = _build_associate_capture_provider()
        associate(provider, sessions)
        prompt = cap["prompts"][0]
        # 每条 session 的私密字段都被 redact
        assert "joy" not in prompt
        assert "秘密梦境" not in prompt
        assert "隐藏" not in prompt
        # 非私密标识保留 (证明三条都进了 prompt)
        assert "session1" in prompt
        assert "session2" in prompt
        assert "session3" in prompt
        assert prompt.count("REDACTED") >= 3

    def test_redacts_all_combined(self) -> None:
        """综合: 多类私密字段同时出现, 全部 redact。"""
        sessions = [
            "---\nemotional_valence: 0.9\n---\n"
            "公开开头\n"
            "[emotion:joy] 行内情绪\n"
            "%%subconscious%% 私密 %%/subconscious%%\n"
            "> [!dream] 秘密梦境\n"
            "正常结尾"
        ]
        provider, cap = _build_associate_capture_provider()
        associate(provider, sessions)
        prompt = cap["prompts"][0]
        assert "0.9" not in prompt
        assert "joy" not in prompt
        assert "私密" not in prompt
        assert "秘密梦境" not in prompt
        assert prompt.count("REDACTED") >= 3
        assert "公开开头" in prompt
        assert "正常结尾" in prompt

    def test_redacts_uppercase_variants(self) -> None:
        """大小写变体也 redact。"""
        sessions = ["> [!DREAM] UPPER SECRET\n[Emotion:joy] mixed"]
        provider, cap = _build_associate_capture_provider()
        associate(provider, sessions)
        prompt = cap["prompts"][0]
        assert "UPPER SECRET" not in prompt
        assert "joy" not in prompt
        assert "REDACTED" in prompt

    def test_normal_text_passes_through(self) -> None:
        """非私密内容正常发给 LLM (不误伤)。"""
        sessions = [
            "今天完成了项目里程碑",
            "继续推进下一步计划",
        ]
        provider, cap = _build_associate_capture_provider()
        associate(provider, sessions)
        prompt = cap["prompts"][0]
        assert "完成了项目里程碑" in prompt
        assert "推进下一步计划" in prompt
        assert "REDACTED" not in prompt

    def test_still_returns_valid_result(self) -> None:
        """redact 不影响 associate 正常返回 {body, tags}。"""
        sessions = ["> [!dream] 秘密\n公开内容", "第二条公开内容"]
        provider, cap = _build_associate_capture_provider()
        result = associate(provider, sessions)
        assert result["body"] == "owner 注重简洁"
        assert result["tags"] == ["简洁"]

    def test_empty_sessions_no_llm_call(self) -> None:
        """空 sessions 列表不调 LLM (不发 prompt)。"""
        provider, cap = _build_associate_capture_provider()
        result = associate(provider, [])
        assert cap["prompts"] == []
        assert result["body"] == "(no sessions)"

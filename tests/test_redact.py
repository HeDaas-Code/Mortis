"""Test mortis.redact — 共享 redact 工具 (issue #83)。

issue #83: _redact_snippet + _SENSITIVE_PATTERNS 从 toolagent.vault_search
提升为共享模块 mortis/redact.py, 公共 API: redact_snippet() + SENSITIVE_PATTERNS。

本测试直接针对 mortis.redact 公共 API, 验证:
- 基本功能: dream callout / emotion 标签 / subconscious / emotional_* 字段
- IGNORECASE: 大小写变体不绕过
- fail-closed: re.sub 异常时返回占位符, 不 fail-open 泄漏原文
- 从 mortis.redact 可 import
"""

from __future__ import annotations

import logging

import pytest

from mortis.redact import SENSITIVE_PATTERNS, redact_snippet


# ============================================================
# 模块导出 / 结构
# ============================================================


class TestRedactModuleExports:
    """mortis.redact 公共 API 可用性。"""

    def test_redact_snippet_callable(self) -> None:
        """redact_snippet 是可调用对象。"""
        assert callable(redact_snippet)

    def test_sensitive_patterns_is_tuple(self) -> None:
        """SENSITIVE_PATTERNS 是 tuple[tuple[str, str], ...]。"""
        assert isinstance(SENSITIVE_PATTERNS, tuple)
        assert len(SENSITIVE_PATTERNS) == 6, (
            f"应有 6 个 pattern, 实得 {len(SENSITIVE_PATTERNS)}"
        )
        for entry in SENSITIVE_PATTERNS:
            assert isinstance(entry, tuple)
            assert len(entry) == 2
            assert isinstance(entry[0], str)  # pattern
            assert isinstance(entry[1], str)  # replacement

    def test_all_exports(self) -> None:
        """__all__ 导出 redact_snippet 和 SENSITIVE_PATTERNS。"""
        import mortis.redact as mod

        assert "redact_snippet" in mod.__all__
        assert "SENSITIVE_PATTERNS" in mod.__all__

    def test_import_from_mortis_redact(self) -> None:
        """可直接从 mortis.redact import 两个公共符号。"""
        from mortis.redact import redact_snippet as rs, SENSITIVE_PATTERNS as sp  # noqa: F401

        assert rs is redact_snippet
        assert sp is SENSITIVE_PATTERNS


# ============================================================
# 基本功能 — 6 类私密字段全部 redact
# ============================================================


class TestRedactBasicFunctionality:
    """redact_snippet 基本功能: 各类私密字段被占位符替换。"""

    def test_redact_dream_callout(self) -> None:
        """> [!dream] callout 整段被 REDACTED。"""
        text = (
            "Public summary.\n\n"
            "> [!dream] Owner had a vivid dream about flying over mountains.\n"
            "> The landscape was detailed and emotional.\n"
            "> Felt peaceful.\n\n"
            "Next public paragraph."
        )
        out = redact_snippet(text)
        assert "flying over mountains" not in out
        assert "vivid dream" not in out
        assert "REDACTED" in out
        assert "Public summary" in out
        assert "Next public paragraph" in out

    def test_redact_warning_callout(self) -> None:
        """> [!warning] callout 被 REDACTED。"""
        text = "Normal text.\n\n> [!warning] Sensitive owner information here.\n\nMore text."
        out = redact_snippet(text)
        assert "Sensitive owner information" not in out
        assert "REDACTED" in out
        assert "Normal text" in out

    def test_redact_secret_callout(self) -> None:
        """> [!secret] callout 被 REDACTED。"""
        text = "OK.\n\n> [!secret] API key: sk-test-1234567890\n\nEnd."
        out = redact_snippet(text)
        assert "sk-test-1234567890" not in out
        assert "REDACTED" in out

    def test_redact_private_callout(self) -> None:
        """> [!private] callout 被 REDACTED。"""
        text = "Before.\n\n> [!private] owner-private diary entry\n\nAfter."
        out = redact_snippet(text)
        assert "owner-private diary" not in out

    def test_redact_confidential_callout(self) -> None:
        """> [!confidential] callout 被 REDACTED。"""
        text = "Before.\n\n> [!confidential] secret strategy notes\n\nAfter."
        out = redact_snippet(text)
        assert "secret strategy" not in out

    def test_redact_emotion_tag(self) -> None:
        """行内 [emotion:joy@0.8] 标签被 REDACTED。"""
        text = "I feel great today [emotion:joy@0.8] really good"
        out = redact_snippet(text)
        assert "[emotion:joy" not in out
        assert "joy" not in out
        assert "REDACTED" in out

    def test_redact_subconscious_comment(self) -> None:
        """%%subconscious%% ... %%/subconscious%% 注释被 REDACTED。"""
        text = "public text %%subconscious%% owner private dream %%/subconscious%% public again"
        out = redact_snippet(text)
        assert "owner private dream" not in out
        assert "REDACTED" in out
        assert "public text" in out
        assert "public again" in out

    def test_redact_sub_alias(self) -> None:
        """%%sub%% ... %%/sub%% 短别名也被 redact。"""
        text = "before %%sub%% private %%/sub%% after"
        out = redact_snippet(text)
        assert "private" not in out
        assert "REDACTED" in out

    def test_redact_emotional_valence(self) -> None:
        """frontmatter emotional_valence 字段被 REDACTED。"""
        text = "---\ntitle: x\nemotional_valence: 0.85\n---\nbody"
        out = redact_snippet(text)
        assert "0.85" not in out
        assert "REDACTED" in out

    def test_redact_emotional_arousal(self) -> None:
        """frontmatter emotional_arousal 字段被 REDACTED。"""
        text = "---\nemotional_arousal: 0.42\n---\nbody"
        out = redact_snippet(text)
        assert "0.42" not in out
        assert "REDACTED" in out

    def test_redact_dream_level(self) -> None:
        """frontmatter dream_level 字段被 REDACTED。"""
        text = "---\ndream_level: deep\n---\nbody"
        out = redact_snippet(text)
        assert "deep" not in out or "REDACTED" in out

    def test_redact_unclosed_subconscious_to_eof(self) -> None:
        """%%subconscious%% 无终止符时也 redact 到 EOF。"""
        text = (
            "%%subconscious%%\n"
            "deeply private thought\n"
            "multiple lines of private\n"
            "no closing tag"
        )
        out = redact_snippet(text)
        assert "deeply private thought" not in out
        assert "multiple lines of private" not in out

    def test_redact_preserves_normal_content(self) -> None:
        """非私密内容完全保留 — 不误伤。"""
        text = (
            "This is a normal growth record about public identity facts.\n"
            "[[wikilink]] reference and #public-tag should pass through.\n"
            'Some normal emotional language: "I felt happy about this milestone".\n'
            "emotional (lowercase, not a tag) is fine."
        )
        out = redact_snippet(text)
        assert "normal growth record" in out
        assert "[[wikilink]]" in out
        assert "#public-tag" in out
        assert "I felt happy" in out
        assert "REDACTED" not in out

    def test_redact_combined_all_patterns(self) -> None:
        """综合场景: 6 类私密字段同时出现, 全部 redact。"""
        text = """---
emotional_valence: 0.9
emotional_arousal: 0.7
dream_level: deep
---

Public intro.

[emotion:joy@0.9] inline emotion.

%%subconscious%% private thought %%/subconscious%%

> [!dream] vivid dream content here
> more dream text

> [!secret] API key sk-abc-123

Normal ending text."""
        out = redact_snippet(text)
        assert "0.9" not in out
        assert "0.7" not in out
        assert "deep" not in out
        assert "joy" not in out
        assert "private thought" not in out
        assert "vivid dream content" not in out
        assert "sk-abc-123" not in out
        assert out.count("REDACTED") >= 3
        assert "Public intro" in out
        assert "Normal ending text" in out

    def test_redact_empty_string(self) -> None:
        """空串安全处理 (不抛错)。"""
        assert redact_snippet("") == ""

    def test_redact_none_returns_none(self) -> None:
        """None 防御 (调用方可能传 None)。"""
        assert redact_snippet(None) is None  # type: ignore[arg-type]


# ============================================================
# IGNORECASE — 大小写变体不绕过
# ============================================================


class TestRedactIgnoreCase:
    """redact_snippet 必须大小写不敏感 (re.IGNORECASE)。

    Obsidian callout / 标签语法本身大小写不敏感, 攻击者用大小写变体
    可绕过仅匹配小写的正则, 导致私密数据外流。
    """

    def test_dream_callout_uppercase(self) -> None:
        """> [!DREAM] 大写绕过。"""
        out = redact_snippet("> [!DREAM] my secret dream")
        assert "my secret dream" not in out
        assert "REDACTED" in out

    def test_dream_callout_mixed_case(self) -> None:
        """> [!Dream] 混合大小写绕过。"""
        out = redact_snippet("> [!Dream] hidden content")
        assert "hidden content" not in out
        assert "REDACTED" in out

    def test_secret_callout_uppercase(self) -> None:
        """> [!SECRET] 大写绕过。"""
        out = redact_snippet("> [!SECRET] private data")
        assert "private data" not in out
        assert "REDACTED" in out

    def test_emotion_tag_mixed_case(self) -> None:
        """[Emotion:joy] 混合大小写绕过。"""
        out = redact_snippet("[Emotion:joy] feeling today")
        assert "joy" not in out
        assert "REDACTED" in out

    def test_emotion_tag_all_uppercase(self) -> None:
        """[EMOTION:joy] 全大写绕过。"""
        out = redact_snippet("[EMOTION:joy] feeling")
        assert "joy" not in out
        assert "REDACTED" in out

    def test_subconscious_uppercase(self) -> None:
        """%%SUB%% 大写绕过。"""
        out = redact_snippet("%%SUB%% hidden thought %%/SUB%%")
        assert "hidden thought" not in out
        assert "REDACTED" in out

    def test_subconscious_mixed_case(self) -> None:
        """%%Subconscious%% 混合大小写绕过。"""
        out = redact_snippet("%%Subconscious%% secret %%/Subconscious%%")
        assert "secret" not in out
        assert "REDACTED" in out

    def test_frontmatter_field_uppercase(self) -> None:
        """Emotional_Valence: 0.8 大写绕过。"""
        out = redact_snippet("Emotional_Valence: 0.8")
        assert "0.8" not in out
        assert "REDACTED" in out

    def test_frontmatter_field_space_before_colon(self) -> None:
        """emotional_valence : 0.8 冒号前空格绕过。"""
        out = redact_snippet("emotional_valence : 0.8")
        assert "0.8" not in out
        assert "REDACTED" in out

    def test_dream_level_uppercase(self) -> None:
        """DREAM_LEVEL: 5 大写绕过。"""
        out = redact_snippet("DREAM_LEVEL: 5")
        assert "5" not in out or "REDACTED" in out


# ============================================================
# fail-closed — re.sub 异常时返回占位符
# ============================================================


class TestRedactFailClosed:
    """redact 失败时不能 fail-open 返回原文, 必须返回占位符。"""

    def test_redact_returns_placeholder_on_internal_error(self, monkeypatch) -> None:
        """模拟 re.sub 抛错 — 应返回 REDACTED 占位符, 不是原文。"""
        import re as _re

        def boom(pattern, repl, string, flags=0):
            raise RuntimeError("simulated re error")

        monkeypatch.setattr(_re, "sub", boom)

        body = "private content with dream markers"
        out = redact_snippet(body)

        # fail-closed: 不能返回原文
        assert "private content" not in out or "[REDACTED" in out, (
            f"fail-open 泄漏: {out!r}"
        )

    def test_fail_closed_logs_warning(self, monkeypatch, caplog) -> None:
        """fail-closed 时应 log warning (便于运维发现)。"""
        import re as _re

        def boom(pattern, repl, string, flags=0):
            raise RuntimeError("simulated re error")

        monkeypatch.setattr(_re, "sub", boom)

        with caplog.at_level(logging.WARNING, logger="mortis.redact"):
            out = redact_snippet("some private content here")

        assert "[REDACTED" in out
        warns = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("redact_snippet failed" in r.getMessage() for r in warns)


# ============================================================
# 共享模块一致性 — toolagent 层别名指向同一函数
# ============================================================


class TestSharedModuleConsistency:
    """issue #83: toolagent 层 _redact_snippet 别名指向 mortis.redact.redact_snippet。"""

    def test_vault_search_alias_is_shared_function(self) -> None:
        """vault_search._redact_snippet 是 mortis.redact.redact_snippet 的别名。"""
        from mortis.toolagent.vault_search import _redact_snippet as vs_redact

        assert vs_redact is redact_snippet

    def test_vault_read_alias_is_shared_function(self) -> None:
        """vault_read._redact_snippet 是 mortis.redact.redact_snippet 的别名。"""
        from mortis.toolagent.vault_read import _redact_snippet as vr_redact

        assert vr_redact is redact_snippet

    def test_all_three_references_identical(self) -> None:
        """三处引用 (redact / vault_search / vault_read) 指向同一函数对象。"""
        from mortis.toolagent.vault_read import _redact_snippet as vr_redact
        from mortis.toolagent.vault_search import _redact_snippet as vs_redact

        assert redact_snippet is vs_redact is vr_redact

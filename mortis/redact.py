"""Mortis 共享 redact 工具 — 发给外部 LLM 前过滤 owner 私密字段。

issue #83: 原 _redact_snippet + _SENSITIVE_PATTERNS 定义在
mortis/toolagent/vault_search.py 内部, 仅 toolagent 层 2 个调用点使用。
提升为共享模块供 dream/reflect/runtime 层复用, 保证所有 LLM 入口
redact 行为一致 (HARNESS.md '数据不外流' 原则)。

公共 API:
    SENSITIVE_PATTERNS: redact 模式表 (pattern, replacement)
    redact_snippet(text): 对 snippet / body 做 redact

行为与原 toolagent.vault_search._redact_snippet 完全一致:
- re.IGNORECASE | re.DOTALL | re.MULTILINE flags
- fail-closed: re.sub 任何异常 → 返回占位符 (不 fail-open 泄漏原文)
"""

from __future__ import annotations

import logging
import re

__all__ = ["redact_snippet", "SENSITIVE_PATTERNS"]

_logger = logging.getLogger(__name__)


# issue #73 MEDIUM-I — semantic rerank 把私密字段发 LLM 前的 redact 模式
# 设计: HARNESS.md '数据不外流' 原则, growth body 含 owner 私密信息
# (emotional_*, dream_level, subconscious, dream callouts) 不应被外部 LLM 看到
SENSITIVE_PATTERNS: tuple[tuple[str, str], ...] = (
    # Obsidian callout: > [!dream] ... (支持嵌套 > > [!dream] + 同段相邻 > [!secret])
    # round 2 设计: 续行用 (?:[ ]{0,3}>(?:[ \t]*>)*[ \t]*)(?!\s*\[!) 严格排除 "下一行是 callout"
    # 防止 dream 段把紧跟的 secret 段吞掉
    (r"(?:[ ]{0,3}>(?:[ \t]*>)*[ \t]*)\[!dream\][^\n]*(?:\n(?:[ ]{0,3}>(?:[ \t]*>)*[ \t]*)(?!\s*\[!)[^\n]*)*",
     "> [!dream]: [REDACTED — owner private dream content]"),
    # Obsidian callout: > [!warning] / > [!secret] / > [!private] / > [!confidential]
    (r"(?:[ ]{0,3}>(?:[ \t]*>)*[ \t]*)\[!(?:warning|secret|private|confidential)\][^\n]*(?:\n(?:[ ]{0,3}>(?:[ \t]*>)*[ \t]*)(?!\s*\[!)[^\n]*)*",
     "> [!redacted]: [REDACTED — owner private callout]"),
    # 行内 emotion 标签: [emotion:joy] / [emotion:joy@0.8]
    (r"\[emotion:[^\]]+\]", "[emotion:REDACTED]"),
    # 潜意识注释: %%subconscious%% ... %% / %%sub%% ... %%
    # 接受 %%sub%% / %%subconscious%% + 对应的 %%/sub%% / %%/subconscious%% 终止符
    # round 2: 加 fallback 分支支持无终止符 (到 EOF)
    (r"%%sub(?:conscious)?%%[\s\S]*?%%/sub(?:conscious)?%%",
     "%%subconscious:REDACTED%%"),
    (r"%%sub(?:conscious)?%%[\s\S]*$",
     "%%subconscious:REDACTED%% (unclosed)"),
    # frontmatter 情感字段: emotional_valence / emotional_arousal / dream_level
    # round 2: 去掉 ^ 锚点, 允许行内出现 (如 YAML 嵌套)
    # 审计 CRITICAL-2: \s*:\s* 允许冒号前后空格 (emotional_valence : 0.8 绕过)
    (r"(emotional_valence|emotional_arousal|dream_level)\s*:\s*[^\n]+",
     r"\1: REDACTED"),
)


def redact_snippet(text: str) -> str:
    """issue #73 MEDIUM-I — redact owner 私密字段, 防止发给外部 LLM。

    输入: snippet 字符串 (来自 _snippet 或 raw body)
    输出: redact 后的字符串, 私密字段被占位符替换

    处理模式 (见模块级 SENSITIVE_PATTERNS):
    - Obsidian dream/warning/secret/private/confidential callouts → 占位符
    - 行内 [emotion:...] 标签 → 占位符
    - %%subconscious%% / %%sub%% 注释 → 占位符
    - frontmatter emotional_valence / emotional_arousal / dream_level → REDACTED

    设计:
    - 函数式 (无副作用), 易于测试
    - round 2 H-3 fail-closed: re.sub 任何异常 → 返回 [REDACTED — redact failed]
      (宁可不展示内容, 也不 fail-open 泄漏私密字段)
    - 占位符含语义 (REDACTED — owner private dream content) 便于 LLM 理解
    """
    if not text:
        return text
    try:
        for pattern, replacement in SENSITIVE_PATTERNS:
            # 审计 CRITICAL-2: 加 IGNORECASE — Obsidian callout / 标签大小写不敏感,
            # 原 redact 仅匹配小写, [!DREAM] / [Emotion:joy] / %%SUB%% / Emotional_Valence 等大小写变体绕过泄漏
            text = re.sub(pattern, replacement, text, flags=re.DOTALL | re.MULTILINE | re.IGNORECASE)
        return text
    except Exception as e:  # noqa: BLE001 — redact 失败: fail-closed, 不返回原文
        _logger.warning(
            "redact_snippet failed, returning fail-closed placeholder: %s", e,
        )
        return "[REDACTED — redact failed, content withheld]"

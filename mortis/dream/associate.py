"""Mortis dream — ASSOCIATE phase: LLM 找相似点。

issue #22: 把多条 session 喂给 LLM,让它生成"模式描述"(候选 growth 的 body)。

设计要点:
- 单轮 prompt + JSON 响应
- 输入: session_texts 列表(每条是 Session 拼好的纯文本)
- 输出: dict {"body": "...", "tags": ["..."]}
- parse 失败 → 回退:body = "auto-fallback: " + 所有 session 第一行拼接
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from mortis.provider.base import LLMProviderProtocol


_logger = logging.getLogger(__name__)


_ASSOCIATE_PROMPT = """请阅读以下 {n} 条会话内容,找出它们之间的**共同模式或潜在洞察**。

要求:
1. 用 1-3 句话提炼这个模式(中文,第一人称)
2. 输出 JSON: {{"body": "<模式描述>", "tags": ["<tag1>", "<tag2>"]}}
3. tags 2-4 个,简短中文词
4. 不要 markdown 代码块包裹,不要解释

会话:
\"\"\"
{sessions_text}
\"\"\"
"""


def _format_sessions(sessions_text: list[str]) -> str:
    """把多条 session 拼成喂 LLM 的文本。

    每条 session 用 "--- Session {i} ---" 分隔。
    """
    parts: list[str] = []
    for i, txt in enumerate(sessions_text, 1):
        parts.append(f"--- Session {i} ---\n{txt.strip()}")
    return "\n\n".join(parts)


def _parse_associate_response(raw: str) -> dict[str, Any]:
    """parse LLM 响应为 {body, tags}。失败回退。"""
    if not raw:
        _logger.warning("associate: empty response, fallback")
        return {"body": "", "tags": []}

    # 策略 1: 严格 JSON
    try:
        data = json.loads(raw.strip())
        if isinstance(data, dict) and "body" in data:
            return {
                "body": str(data.get("body", "")).strip(),
                "tags": list(data.get("tags", [])),
            }
    except (json.JSONDecodeError, ValueError):
        pass

    # 策略 2: regex 抓 body 字段
    m = re.search(r'"body"\s*:\s*"([^"]+)"', raw)
    if m:
        body = m.group(1).strip()
        tags_m = re.search(r'"tags"\s*:\s*\[([^\]]*)\]', raw)
        tags: list[str] = []
        if tags_m:
            tags = [t.strip().strip('"').strip("'") for t in tags_m.group(1).split(",") if t.strip()]
        return {"body": body, "tags": tags}

    _logger.warning("associate: failed to parse response, fallback to raw text")
    return {"body": raw.strip(), "tags": []}


def associate(
    provider: LLMProviderProtocol,
    sessions_text: list[str],
) -> dict[str, Any]:
    """调用 LLM 找多条 session 的共同模式。

    Args:
        provider: LLM provider。
        sessions_text: 已加载好的 session 纯文本列表(每条是 summary)。

    Returns:
        {"body": str, "tags": list[str]} — body 是候选 growth 的内容,
        tags 是建议写入 frontmatter 的标签。
    """
    if not sessions_text:
        return {"body": "(no sessions)", "tags": []}

    formatted = _format_sessions(sessions_text)
    # 用 .replace 不用 .format — 避免 session_text 里 JSON 花括号触 KeyError
    prompt = _ASSOCIATE_PROMPT.replace("{n}", str(len(sessions_text))).replace(
        "{sessions_text}", formatted
    )
    raw = provider.generate_text(prompt)
    return _parse_associate_response(raw)


__all__ = ["associate"]
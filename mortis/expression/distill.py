"""Mortis expression distill — dream phase: LLM 提炼表达模式 (issue #94 第二步)。

EXPRESSION_DISTILL phase:
1. 从近期 expression-stats 聚合统计
2. 调 LLM 提炼表达模式描述 (基于用户说话风格)
3. 产出写入 ``mortis-growth/tone/expression-<date>.md`` (confidence=0.3, dream_level=LIGHT)

设计要点:
- 依赖 issue #92 (对话→Session) 产出的 stats 数据; 无 stats 时 phase 跳过 (ok=True)。
- 复用 ``make_candidate`` 构造 tone growth, dimension=TONE, id 显式 ``expression-<date>``。
- 同一天重复 dream 会覆盖当天 expression growth (id 相同) — 取最新模式, 符合 issue 意图。
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from mortis.expression.stats import TurnStats, format_stats_for_prompt, load_recent_stats
from mortis.growth.model import Dimension
from mortis.provider.base import LLMProviderProtocol, Message
from mortis.vault.local import Vault

_logger = logging.getLogger(__name__)

# expression growth 的 id 前缀 — context.py 据此过滤注入
EXPRESSION_ID_PREFIX = "expression-"

# distill 默认采样天数
DEFAULT_DISTILL_DAYS = 7


def expression_growth_id(now: datetime | None = None) -> str:
    """生成 expression-YYYY-MM-DD id (同天覆盖, 取最新模式)。"""
    ts = now or datetime.now(tz=timezone.utc)
    return f"{EXPRESSION_ID_PREFIX}{ts.strftime('%Y-%m-%d')}"


def _build_distill_prompt(stats_text: str) -> list[Message]:
    """构造 LLM distill prompt。"""
    system = (
        "你是 Mortis 的人格演化模块。根据近期对话统计, 提炼 Mortis 应该采用的表达方式模式。"
        "模式应基于用户的说话偏好 (用户偏好短句 → Mortis 也该简洁; 用户用 '嗯' 认可 → "
        "Mortis 可复用该标记)。输出 3-5 条模式, 每条一行, 以 '- ' 开头。"
    )
    user = (
        "## 近期对话统计\n\n"
        f"{stats_text}\n\n"
        "## 要求\n"
        "输出 3-5 条表达模式 (基于用户偏好的可操作建议), 每行格式:\n"
        "- <模式描述>\n\n"
        "只输出列表, 不要额外解释。"
    )
    return [
        Message(role="system", content=system),
        Message(role="user", content=user),
    ]


def distill_expression_patterns(
    provider: LLMProviderProtocol,
    turns: list[TurnStats],
    *,
    temperature: float = 0.5,
) -> dict[str, Any]:
    """调 LLM 从对话统计提炼表达模式。

    Args:
        provider: LLM provider。
        turns: 近期 turn 统计列表。
        temperature: 采样温度 (低温度 = 更稳定的模式)。

    Returns:
        ``{"body": "<markdown bullet list>", "turn_count": N}``。
        空输入返回 ``{"body": "", "turn_count": 0}``。
    """
    if not turns:
        return {"body": "", "turn_count": 0}
    stats_text = format_stats_for_prompt(turns)
    if not stats_text:
        return {"body": "", "turn_count": len(turns)}
    messages = _build_distill_prompt(stats_text)
    try:
        resp = provider.generate(messages, temperature=temperature)
        body = resp.content.strip()
    except Exception as e:
        _logger.warning("distill expression patterns LLM call failed: %s", e)
        return {"body": "", "turn_count": len(turns)}
    # 清理: 剥离 <think> 标签 (兼容 MiniMax-M3)
    body = re.sub(r"<think>.*?</think>", "", body, flags=re.DOTALL).strip()
    return {"body": body, "turn_count": len(turns)}


def is_expression_growth(growth_id: str) -> bool:
    """判断 growth id 是否为 expression 模式 (供 context 注入过滤)。"""
    return bool(growth_id) and growth_id.startswith(EXPRESSION_ID_PREFIX)


__all__ = [
    "distill_expression_patterns",
    "expression_growth_id",
    "is_expression_growth",
    "EXPRESSION_ID_PREFIX",
    "DEFAULT_DISTILL_DAYS",
]

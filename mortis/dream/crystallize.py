"""Mortis dream — CRYSTALLIZE phase: 生成 Growth 候选。

issue #22: 把 ASSOCIATE 的联想结果结晶成 confidence=0.3 的 Growth 候选,
写入 vault.mortis-growth/<dim>/<id>.md。

设计要点:
- candidate id: dream-<YYYY-MM-DD>-<NNN> (当天序号从 001 起,与 Reflection 风格一致)
- dimension: 由 ASSOCIATE 推断出的 7 维度之一(RFC-001 §七)
- confidence 固定 0.3 (浅梦 RFC §三 — 低置信度,等 owner 验证后再 validate)
- dream_level = LIGHT
- source_sessions = 被选中的 session_paths
- body = LLM 联想生成的模式描述(已含 wikilinks / callout / tags 由 Obsidian 解析层后续抓)
- 不写潜意识(subconscious=None)— 浅梦不沉淀潜意识到 growth,只在 conflict 里
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import PurePosixPath

from mortis.growth.model import Dimension, DreamLevel, Growth
from mortis.provider.base import LLMProviderProtocol
from mortis.vault.local import Vault


# ============================================================
# id 生成
# ============================================================


_TODAY_DREAM_COUNTERS: dict[str, int] = {}


def _next_dream_id(today: str | None = None) -> str:
    """生成 dream-YYYY-MM-DD-NNN id(NNN 当天从 001 起)。

    进程内自增计数器。跨进程不保证唯一(同一秒多个 LightDreamer 实例可能冲突),
    但 dream 通常一次只跑一次,冲突概率极低。
    """
    if today is None:
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    n = _TODAY_DREAM_COUNTERS.get(today, 0) + 1
    _TODAY_DREAM_COUNTERS[today] = n
    return f"dream-{today}-{n:03d}"


def reset_counter() -> None:
    """清空 id 计数器 — 供测试用。"""
    _TODAY_DREAM_COUNTERS.clear()


# ============================================================
# dimension 推断
# ============================================================


# 关键词 → 维度映射 (RFC §七)
# 匹配规则: 在 body 文本中任一关键词命中 → 对应维度
_DIMENSION_KEYWORDS: dict[Dimension, tuple[str, ...]] = {
    Dimension.IDENTITY: ("我是", "身份", "人格", "mortis 是", "我是谁"),
    Dimension.VALUES: ("价值", "原则", "底线", "应该", "不该"),
    Dimension.TONE: ("语气", "文风", "语调", "风格"),
    Dimension.AGENCY: ("自主", "决策", "行动", "委派", "选择"),
    Dimension.RELATIONS: ("owner", "关系", "信任", "合作", "伙伴"),
    Dimension.CREATIVITY: ("创造", "联想", "想法", "模式", "新"),
    Dimension.MORTALITY: ("死亡", "结束", "时间", "遗忘", "记忆"),
}


def infer_dimension(body: str) -> Dimension:
    """从 body 文本粗略推断维度。

    简单关键词命中 — 不是 LLM 推断(节省 token,且单维度模糊归属可接受)。
    没命中任何关键词 → IDENTITY (默认 fallback)。
    """
    text = body.lower()
    best_dim = Dimension.IDENTITY
    best_count = 0
    for dim, keywords in _DIMENSION_KEYWORDS.items():
        c = sum(1 for kw in keywords if kw.lower() in text)
        if c > best_count:
            best_count = c
            best_dim = dim
    return best_dim


# ============================================================
# candidate 生成
# ============================================================


def make_candidate(
    *,
    body: str,
    dimension: Dimension,
    source_sessions: list[str],
    valence: float,
    arousal: float,
    id: str | None = None,
) -> Growth:
    """构造一个 confidence=0.3 / dream_level=LIGHT 的 Growth 候选。

    Args:
        body: 候选内容(已含 LLM 联想的模式描述)。
        dimension: 归属维度。
        source_sessions: 触发该候选的 session path 列表(RELATIVE 路径,非绝对)。
        valence, arousal: 候选的整体情绪基调(从源 sessions 平均得到)。
        id: 可选显式 id;默认自增生成。

    注意:
        - last_validated = created_at(尚未被 owner 验证)
        - tags = ()(空) — writer 跑时如发现 body 里有 #tag,Obsidian 解析层会回填
        - wikilinks / tags_inline / callout / subconscious 都默认空(由 Obsidian 解析层
          在 write_growth → write → read 周期后回填;首次写时就是空)
    """
    now = datetime.now(tz=timezone.utc).isoformat()
    return Growth(
        id=id or _next_dream_id(),
        dimension=dimension,
        confidence=0.3,
        created_at=now,
        last_validated=now,
        source_sessions=tuple(source_sessions),
        dream_level=DreamLevel.LIGHT,
        emotional_valence=valence,
        emotional_arousal=arousal,
        tags=(),
        body=body,
    )


# ============================================================
# 平均情绪 (跨 sessions)
# ============================================================


def average_emotion(pairs: list[tuple[float, float]]) -> tuple[float, float]:
    """求 (valence, arousal) 平均。

    空列表 → (0.0, 0.0)。
    """
    if not pairs:
        return 0.0, 0.0
    n = len(pairs)
    v = sum(v for v, _a in pairs) / n
    a = sum(a for _v, a in pairs) / n
    # clamp 到合法范围
    v = max(-1.0, min(1.0, v))
    a = max(0.0, min(1.0, a))
    return v, a


__all__ = [
    "_next_dream_id",
    "reset_counter",
    "infer_dimension",
    "make_candidate",
    "average_emotion",
]
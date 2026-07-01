"""Mortis expression stats — 对话统计提取 (issue #94 第一步)。

每次对话后, 从 user / mortis 双侧文本中提取表达特征:
- 平均句长 (chars/sentence)
- 标点习惯 (各标点出现次数)
- 高频词 top-10 (ASCII 词 + 中文 bigram 近似)
- 语气词 / discourse markers (嗯/啊/呢/吧...)
- 疑问句占比

统计按天写入 ``vault/mortis-journal/expression-stats/<date>.json`` (JSON array,
每轮对话一条), 供 dream EXPRESSION_DISTILL phase 读取并 LLM 提炼表达模式。

设计要点:
- 无外部依赖 (不用 jieba) — 中文词频用 bigram 近似, 够 LLM 提炼用。
- 静默失败 — 统计写入异常不应阻断主对话流程 (由调用方 try/except)。
- 纯函数 ``extract_side_stats`` 可单测, 不依赖 vault。
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from mortis.vault.local import Vault

_logger = logging.getLogger(__name__)

# ---- 文本切分规则 ----

# 句子分隔符: 中英文句号/问号/叹号/换行/分号
_SENT_SPLIT = re.compile(r"[。！？.!?\n;；]+")
# 标点全集 (统计习惯用) — 注意不含逗号会丢失重要信号, 故含
_PUNCTUATION = "。！？，、；：…—.!?,;:\"'()[]（）”“’‘"
# 语气词 / discourse markers — 中文对话的高频风格信号
_DISCOURSE_MARKERS = ("嗯", "啊", "呢", "吧", "哦", "哈", "哎", "嘛", "呀", "哇", "嘿")
# ASCII 词 token (英文/数字混合)
_WORD_TOKEN = re.compile(r"[a-zA-Z][a-zA-Z0-9_\-]+")
# 中文字符范围
_CN_CHAR = re.compile(r"[\u4e00-\u9fff]")

# 统计文件目录 (相对 vault 根)
EXPRESSION_STATS_DIR = "mortis-journal/expression-stats"


# ============================================================
# 单侧统计 (user 或 mortis)
# ============================================================


@dataclass
class SideStats:
    """单侧 (user 或 mortis) 的表达统计。"""

    avg_sentence_length: float = 0.0
    punctuation_habits: dict[str, int] = field(default_factory=dict)
    top_words: list[tuple[str, int]] = field(default_factory=list)
    discourse_markers: dict[str, int] = field(default_factory=dict)
    question_ratio: float = 0.0
    char_count: int = 0
    sentence_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "avg_sentence_length": self.avg_sentence_length,
            "punctuation_habits": self.punctuation_habits,
            "top_words": self.top_words,
            "discourse_markers": self.discourse_markers,
            "question_ratio": self.question_ratio,
            "char_count": self.char_count,
            "sentence_count": self.sentence_count,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SideStats:
        return cls(
            avg_sentence_length=d.get("avg_sentence_length", 0.0),
            punctuation_habits=d.get("punctuation_habits", {}),
            top_words=[tuple(t) for t in d.get("top_words", [])],
            discourse_markers=d.get("discourse_markers", {}),
            question_ratio=d.get("question_ratio", 0.0),
            char_count=d.get("char_count", 0),
            sentence_count=d.get("sentence_count", 0),
        )


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]


def _extract_tokens(text: str) -> list[str]:
    """提取词 token: ASCII 词 + 中文 bigram (近似中文词)。"""
    tokens: list[str] = list(_WORD_TOKEN.findall(text))
    cn_chars = _CN_CHAR.findall(text)
    for i in range(len(cn_chars) - 1):
        tokens.append(cn_chars[i] + cn_chars[i + 1])
    return tokens


def extract_side_stats(text: str) -> SideStats:
    """从一段文本提取单侧表达统计 (纯函数, 无副作用)。

    空文本返回全零 SideStats。
    """
    if not text or not text.strip():
        return SideStats()
    sentences = _split_sentences(text)
    n_sent = len(sentences)
    avg_len = (sum(len(s) for s in sentences) / n_sent) if n_sent else 0.0
    punct = {c: text.count(c) for c in _PUNCTUATION if text.count(c) > 0}
    tokens = _extract_tokens(text)
    top = Counter(tokens).most_common(10)
    markers = {m: text.count(m) for m in _DISCOURSE_MARKERS if text.count(m) > 0}
    # issue #94: 统计原始文本中 ?/？ 出现次数 (而非句子末尾) — 因为 _SENT_SPLIT
    # 把 ?/？ 当作分隔符吃掉, 分隔后的句子永远不以 ? 结尾, 旧实现 question_ratio 恒为 0。
    q_count = text.count("?") + text.count("？")
    q_ratio = (q_count / n_sent) if n_sent else 0.0
    return SideStats(
        avg_sentence_length=round(avg_len, 2),
        punctuation_habits=punct,
        top_words=top,
        discourse_markers=markers,
        question_ratio=round(q_ratio, 3),
        char_count=len(text),
        sentence_count=n_sent,
    )


# ============================================================
# 单轮对话统计
# ============================================================


@dataclass
class TurnStats:
    """一轮对话 (user → mortis) 的双侧统计。"""

    timestamp: str
    user_stats: SideStats
    mortis_stats: SideStats

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "user_stats": self.user_stats.to_dict(),
            "mortis_stats": self.mortis_stats.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TurnStats:
        return cls(
            timestamp=d.get("timestamp", ""),
            user_stats=SideStats.from_dict(d.get("user_stats", {})),
            mortis_stats=SideStats.from_dict(d.get("mortis_stats", {})),
        )


def build_turn_stats(user_text: str, mortis_text: str) -> TurnStats:
    """构造一轮对话的统计 (纯函数)。"""
    return TurnStats(
        timestamp=datetime.now(tz=timezone.utc).isoformat(),
        user_stats=extract_side_stats(user_text),
        mortis_stats=extract_side_stats(mortis_text),
    )


# ============================================================
# vault 读写 (按天 JSON array)
# ============================================================


def _stats_rel(date_str: str) -> str:
    """统计文件相对路径: mortis-journal/expression-stats/<date>.json。"""
    return f"{EXPRESSION_STATS_DIR}/{date_str}.json"


def record_turn_stats(
    vault: Vault,
    user_text: str,
    mortis_text: str,
    *,
    now: datetime | None = None,
) -> TurnStats | None:
    """追加一轮对话统计到当天的 stats 文件。

    文件格式: JSON array, 每轮一条。不存在则新建。
    静默失败 — 任何异常记 warning 并返回 None, 不阻断对话。

    Args:
        vault: Vault 实例。
        user_text: 用户侧文本。
        mortis_text: Mortis 侧回复文本。
        now: 可选时间戳 (测试注入)。

    Returns:
        构造的 TurnStats, 失败返回 None。
    """
    try:
        ts = build_turn_stats(user_text, mortis_text)
        if now is not None:
            ts = TurnStats(
                timestamp=now.isoformat(),
                user_stats=ts.user_stats,
                mortis_stats=ts.mortis_stats,
            )
        date_str = ts.timestamp[:10]
        rel = _stats_rel(date_str)
        existing: list[dict[str, Any]] = []
        if vault.exists(rel):
            try:
                entry = vault.read(rel)
                data = json.loads(entry.content)
                if isinstance(data, list):
                    existing = data
            except (json.JSONDecodeError, ValueError) as e:
                _logger.warning("expression stats: corrupt %s, resetting: %s", rel, e)
                existing = []
        existing.append(ts.to_dict())
        vault.write(
            rel,
            json.dumps(existing, ensure_ascii=False, indent=2),
            whitelist=None,
        )
        return ts
    except Exception as e:
        _logger.warning("record expression stats failed: %s", e)
        return None


def load_recent_stats(vault: Vault, days: int = 7) -> list[TurnStats]:
    """读最近 N 天的 expression-stats 文件, 返回所有 turn 统计。

    按时间顺序 (旧 → 新)。文件缺失或损坏跳过。
    """
    today = datetime.now(tz=timezone.utc).date()
    cutoff = today - timedelta(days=days - 1)
    all_turns: list[TurnStats] = []
    for offset in range(days):
        d = cutoff + timedelta(days=offset)
        rel = _stats_rel(d.isoformat())
        if not vault.exists(rel):
            continue
        try:
            entry = vault.read(rel)
            data = json.loads(entry.content)
            if not isinstance(data, list):
                continue
            for item in data:
                if isinstance(item, dict):
                    all_turns.append(TurnStats.from_dict(item))
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            _logger.warning("load expression stats %s failed: %s", rel, e)
            continue
    return all_turns


# ============================================================
# 聚合格式化 (给 LLM distill 用)
# ============================================================


def format_stats_for_prompt(turns: list[TurnStats]) -> str:
    """把多轮统计聚合成文本块, 喂给 LLM 提炼表达模式。

    聚合维度:
    - 用户侧: 平均句长 (跨轮均值), 总语气词分布, 总疑问占比, top 词
    - Mortis 侧: 平均句长, 总语气词分布
    - 轮次数

    空列表返回空串。
    """
    if not turns:
        return ""

    def _avg(items: list[SideStats], attr: str) -> float:
        vals = [getattr(s, attr) for s in items if getattr(s, attr)]
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    def _sum_dicts(items: list[SideStats], attr: str) -> dict[str, int]:
        agg: dict[str, int] = {}
        for s in items:
            for k, v in getattr(s, attr).items():
                agg[k] = agg.get(k, 0) + v
        return dict(sorted(agg.items(), key=lambda x: -x[1]))

    user_sides = [t.user_stats for t in turns]
    mortis_sides = [t.mortis_stats for t in turns]

    user_avg_len = _avg(user_sides, "avg_sentence_length")
    mortis_avg_len = _avg(mortis_sides, "avg_sentence_length")
    user_markers = _sum_dicts(user_sides, "discourse_markers")
    mortis_markers = _sum_dicts(mortis_sides, "discourse_markers")
    user_punct = _sum_dicts(user_sides, "punctuation_habits")
    user_q_ratio = _avg(user_sides, "question_ratio")

    # 聚合用户 top 词
    user_word_counter: Counter = Counter()
    for s in user_sides:
        for w, c in s.top_words:
            user_word_counter[w] += c
    user_top_words = user_word_counter.most_common(10)

    lines: list[str] = [
        f"轮次数: {len(turns)}",
        f"用户平均句长: {user_avg_len} 字/句",
        f"Mortis 平均句长: {mortis_avg_len} 字/句",
        f"用户疑问句占比: {user_q_ratio}",
    ]
    if user_markers:
        mk = ", ".join(f"{k}×{v}" for k, v in list(user_markers.items())[:6])
        lines.append(f"用户语气词: {mk}")
    if mortis_markers:
        mk = ", ".join(f"{k}×{v}" for k, v in list(mortis_markers.items())[:6])
        lines.append(f"Mortis 语气词: {mk}")
    if user_punct:
        pk = ", ".join(f"{k}×{v}" for k, v in list(user_punct.items())[:6])
        lines.append(f"用户标点习惯: {pk}")
    if user_top_words:
        wk = ", ".join(f"{w}({c})" for w, c in user_top_words[:6])
        lines.append(f"用户高频词: {wk}")
    return "\n".join(lines)


__all__ = [
    "SideStats",
    "TurnStats",
    "extract_side_stats",
    "build_turn_stats",
    "record_turn_stats",
    "load_recent_stats",
    "format_stats_for_prompt",
    "EXPRESSION_STATS_DIR",
]

"""Mortis dream — LightDreamer: 浅梦 4 phase。

issue #22: 每天一次的浅梦,把 pending reflections + 最近 session 结晶成
confidence=0.3 的 growth 候选。

phase 流水线 (Light = 4 phase):
  1. RECALL: 扫描 vault 的 mortis-journal/sessions/,取最近 2 天 session;
             按情绪加权采样 k=5 条
  2. ASSOCIATE: 调 LLM 找共同模式
  3. CRYSTALLIZE: 写 mortis-growth/<dim>/<id>.md (confidence=0.3, dream_level=LIGHT)
  4. RECONCILE: 检测新候选 vs 旧 growth 冲突,
                写 mortis-subconscious/conflicts/<id>.md (whitelist=None 跳过强检查)

设计要点:
- 只动 vault 的 mortis-growth/ + mortis-subconscious/conflicts/,不读旧 growth 改值
- 浅梦不写 mortis-dream-log/(#23 才有)
- 浅梦不实现 MEDIUM/DEEP(NotImplementedError 在 #23 才有子类)
- MEDIUM/DEEP 不在 #22 范围 — 当前模块只有 LightDreamer
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mortis.dream.associate import associate
from mortis.dream.crystallize import (
    average_emotion,
    infer_dimension,
    make_candidate,
)
from mortis.dream.phases import DreamLevel, DreamPhase
from mortis.dream.pipeline import DreamPipeline, DreamResult, PhaseTrace
from mortis.dream.recall import emotion_weighted_sample
from mortis.growth.model import Dimension, Growth
from mortis.memory import Session, Thread
from mortis.provider.base import LLMProviderProtocol
from mortis.reflect.emotion import score_emotion
from mortis.vault.local import Vault


_logger = logging.getLogger(__name__)


# 默认配置
DEFAULT_RECALL_K = 5
DEFAULT_RECALL_DAYS = 2


@dataclass
class Conflict:
    """候选 growth 与旧 growth 冲突的记录。"""
    candidate_id: str
    candidate_body: str
    existing_growth_id: str
    existing_growth_body: str
    reason: str
    created_at: str


class LightDreamer(DreamPipeline):
    """浅梦执行器。"""

    level: DreamLevel = DreamLevel.LIGHT

    def __init__(
        self,
        vault: Vault,
        provider: LLMProviderProtocol,
        *,
        k: int = DEFAULT_RECALL_K,
        days: int = DEFAULT_RECALL_DAYS,
        rng: random.Random | None = None,
    ) -> None:
        """构造浅梦执行器。

        Args:
            vault: vault 根 (vault.root = Path)
            provider: LLM provider
            k: RECALL 采样数量
            days: 取最近几天的 session
            rng: 可选随机数生成器(默认 random.Random() — 不保证可复现)
        """
        self.vault = vault
        self.provider = provider
        self.k = k
        self.days = days
        self.rng = rng if rng is not None else random.Random()

        # RECALL phase 的中间结果,后续 phase 复用
        self._recalled: list[Session | Thread] = []
        self._recall_weights: list[tuple[float, float]] = []  # (v, a) per session
        self._candidate: Growth | None = None

    # ===========================================================
    # RECALL: 情绪加权采样
    # ===========================================================

    def phase_recall(self) -> PhaseTrace:
        """扫描最近 N 天 session → 调 score_emotion → emotion_weighted_sample。"""
        sessions = self._load_recent_sessions()
        if not sessions:
            return PhaseTrace(
                phase=DreamPhase.RECALL.value,
                ok=True,
                detail={"reason": "no_sessions", "loaded": 0, "sampled": 0},
            )

        # 给每条 session 打 emotion(用 score_emotion 缓存)
        items: list[tuple[Session | Thread, float, float]] = []
        session_texts: list[str] = []
        for s in sessions:
            # cache key — Thread 用 thread_id, Session 用 session_id
            path = getattr(s, "thread_id", None) or getattr(s, "session_id", "")
            text = self._summarize_session(s)
            v, a = score_emotion(self.provider, str(path), text)
            items.append((s, v, a))
            session_texts.append(text)

        sampled = emotion_weighted_sample(items, k=self.k, rng=self.rng)
        self._recalled = list(sampled)
        # 用 id 映射找 session_texts 中对应的索引
        idx_map = {id(items[i][0]): i for i in range(len(items))}
        self._recall_texts = []
        for s in sampled:
            i = idx_map.get(id(s))
            if i is not None:
                self._recall_texts.append(session_texts[i])

        self._recall_weights = [
            (v, a) for (s, v, a) in items if s in sampled
        ]

        return PhaseTrace(
            phase=DreamPhase.RECALL.value,
            ok=True,
            detail={
                "loaded": len(sessions),
                "sampled": len(sampled),
                "k": self.k,
            },
        )

    def _load_recent_sessions(self) -> list[Session | Thread]:
        """扫描 vault.mortis-journal/sessions/,返回最近 N 天的 Session/Thread。

        issue #92: ChatService 现在把对话写入 Thread 文件 (sessions/<date>/<thread_id>.json)。
        Thread 含 task + steps (对话历史), 是 dream 真正能消化的素材。
        老的 Session 文件 (无 thread_id/steps 字段) 仍向后兼容加载。
        """
        journal_root = Path(self.vault.root) / "mortis-journal" / "sessions"
        if not journal_root.exists():
            return []

        all_items: list[Session | Thread] = []
        # 按日期目录扫描(YYYY-MM-DD/)
        date_dirs: list[Path] = []
        for p in journal_root.iterdir():
            if p.is_dir() and len(p.name) == 10 and p.name[4] == "-":
                date_dirs.append(p)
        date_dirs.sort(reverse=True)  # 最近在前

        cutoff = self._date_cutoff()
        for d in date_dirs:
            if d.name < cutoff:
                continue
            for json_file in d.glob("*.json"):
                try:
                    import json as _json
                    data = _json.loads(json_file.read_text(encoding="utf-8"))
                    # issue #92: Thread 文件含 thread_id + steps — 优先按 Thread 解析
                    if isinstance(data, dict) and "thread_id" in data and "steps" in data:
                        all_items.append(Thread.from_dict(data))
                    else:
                        all_items.append(Session.from_dict(data))
                except (FileNotFoundError, KeyError, ValueError) as e:
                    _logger.warning("light dreamer: skip %s: %s", json_file, e)

        return all_items

    def _date_cutoff(self) -> str:
        """计算 N 天前的 YYYY-MM-DD(闭区间,含今天)。"""
        from datetime import timedelta
        today = datetime.now(tz=timezone.utc).date()
        cutoff = today - timedelta(days=self.days - 1)
        return cutoff.isoformat()

    @staticmethod
    def _summarize_session(s: Session | Thread) -> str:
        """把 Session/Thread 拼成纯文本(喂 LLM 用)。

        - Thread: 含 task + steps (对话历史) — dream 真正能消化的素材 (issue #92)
        - Session: 仅 session_id/threads/metadata — 老格式, 向后兼容
        """
        parts: list[str] = []
        if isinstance(s, Thread):
            parts.append(f"Thread {s.thread_id} @ {s.created_at}")
            if s.task:
                parts.append(f"Task: {s.task}")
            if s.status and s.status != "active":
                parts.append(f"Status: {s.status}")
            for step in s.steps:
                parts.append(f"[{step.step_type}] {step.input}")
                if step.output:
                    parts.append(f"→ {step.output}")
        else:
            parts.append(f"Session {s.session_id} @ {s.created_at}")
            if s.threads:
                parts.append(f"Threads: {', '.join(s.threads)}")
            if s.metadata:
                parts.append(f"Metadata: {s.metadata}")
        return "\n".join(parts)

    # ===========================================================
    # ASSOCIATE: LLM 找模式
    # ===========================================================

    def phase_associate(self) -> PhaseTrace:
        if not self._recalled:
            return PhaseTrace(
                phase=DreamPhase.ASSOCIATE.value,
                ok=True,
                detail={"reason": "no_recalled_sessions"},
            )

        result = associate(self.provider, self._recall_texts)
        self._associate_result = result
        return PhaseTrace(
            phase=DreamPhase.ASSOCIATE.value,
            ok=True,
            detail={
                "body_len": len(result.get("body", "")),
                "tags": result.get("tags", []),
            },
        )

    # ===========================================================
    # CRYSTALLIZE: 写 Growth 候选
    # ===========================================================

    def phase_crystallize(self) -> PhaseTrace:
        if not self._recalled or not getattr(self, "_associate_result", None):
            return PhaseTrace(
                phase=DreamPhase.CRYSTALLIZE.value,
                ok=True,
                detail={"reason": "no_inputs"},
            )

        assoc = self._associate_result
        body = assoc.get("body", "").strip()
        if not body:
            return PhaseTrace(
                phase=DreamPhase.CRYSTALLIZE.value,
                ok=True,
                detail={"reason": "empty_body"},
            )

        dimension = infer_dimension(body)
        v, a = average_emotion(self._recall_weights)
        # issue #92: _recalled 可能是 Thread 也可能是 Session — Thread 用 thread_id,
        # Session 用 session_id, 作为 source_sessions 标识 growth 来源
        source_sessions = [
            str(getattr(s, "thread_id", None) or getattr(s, "session_id", ""))
            for s in self._recalled
        ]
        candidate = make_candidate(
            body=body,
            dimension=dimension,
            source_sessions=source_sessions,
            valence=v,
            arousal=a,
        )
        # tags 从 associate 注入
        if assoc.get("tags"):
            candidate = candidate.__class__(
                **{**candidate.__dict__, "tags": tuple(assoc["tags"])}
            )

        self.vault.write_growth(candidate)
        self._candidate = candidate
        return PhaseTrace(
            phase=DreamPhase.CRYSTALLIZE.value,
            ok=True,
            detail={
                "growth_id": candidate.id,
                "dimension": candidate.dimension.value,
                "confidence": candidate.confidence,
            },
        )

    # ===========================================================
    # RECONCILE: 检测冲突,写 subconscious
    # ===========================================================

    def phase_reconcile(self) -> PhaseTrace:
        if self._candidate is None:
            return PhaseTrace(
                phase=DreamPhase.RECONCILE.value,
                ok=True,
                detail={"reason": "no_candidate"},
            )

        existing = self._candidate_existing_growths()
        if not existing:
            return PhaseTrace(
                phase=DreamPhase.RECONCILE.value,
                ok=True,
                detail={"reason": "no_existing_growths", "checked": 0, "conflicts": 0},
            )

        conflicts = self._detect_conflicts(self._candidate, existing)
        for c in conflicts:
            self._write_conflict(c)

        return PhaseTrace(
            phase=DreamPhase.RECONCILE.value,
            ok=True,
            detail={
                "checked": len(existing),
                "conflicts": len(conflicts),
                "conflict_ids": [c.candidate_id for c in conflicts],
            },
        )

    # ===========================================================
    # EXPRESSION_DISTILL: 从对话统计提炼表达模式 → tone growth (issue #94)
    # ===========================================================

    def phase_expression_distill(self) -> PhaseTrace:
        """从近期对话统计 (expression-stats) 提炼表达模式, 写 tone growth。

        issue #94 第二步:
        1. 读最近 N 天 expression-stats (由 ChatService 对话后写入)
        2. 调 LLM 提炼表达模式描述 (基于用户说话风格)
        3. 写 ``mortis-growth/tone/expression-<date>.md`` (confidence=0.3, LIGHT)

        无统计 (无对话数据) → ok=True 跳过, 不阻断 dream。
        LLM 产出空 body → ok=True 跳过。
        """
        from mortis.expression.distill import (
            DEFAULT_DISTILL_DAYS,
            distill_expression_patterns,
            expression_growth_id,
        )
        from mortis.expression.stats import load_recent_stats

        turns = load_recent_stats(self.vault, days=DEFAULT_DISTILL_DAYS)
        if not turns:
            return PhaseTrace(
                phase=DreamPhase.EXPRESSION_DISTILL.value,
                ok=True,
                detail={"reason": "no_stats", "loaded": 0},
            )

        result = distill_expression_patterns(self.provider, turns)
        body = result.get("body", "").strip()
        if not body:
            return PhaseTrace(
                phase=DreamPhase.EXPRESSION_DISTILL.value,
                ok=True,
                detail={"reason": "empty_body", "turn_count": result.get("turn_count", 0)},
            )

        # 构造 tone growth (id=expression-<date>, 同天覆盖取最新模式)
        growth_id = expression_growth_id()
        candidate = make_candidate(
            body=body,
            dimension=Dimension.TONE,
            source_sessions=[],
            valence=0.0,
            arousal=0.3,
            id=growth_id,
        )
        self.vault.write_growth(candidate)
        return PhaseTrace(
            phase=DreamPhase.EXPRESSION_DISTILL.value,
            ok=True,
            detail={
                "growth_id": growth_id,
                "dimension": Dimension.TONE.value,
                "turn_count": result.get("turn_count", 0),
                "body_len": len(body),
            },
        )

    def _candidate_existing_growths(self) -> list[Growth]:
        """列所有现有 growth(过滤掉自己刚写的 candidate)。"""
        all_rels = self.vault.list_growths()
        existing: list[Growth] = []
        candidate_id = self._candidate.id if self._candidate else None
        for rel in all_rels:
            try:
                g = self.vault.read_growth(rel)
            except Exception as e:
                _logger.warning("light dreamer: skip unreadable growth %s: %s", rel, e)
                continue
            if candidate_id and g.id == candidate_id:
                continue
            existing.append(g)
        return existing

    def _detect_conflicts(
        self, candidate: Growth, existing: list[Growth]
    ) -> list[Conflict]:
        """简单冲突检测:同 dimension 且 confidence 高 + body 含互斥关键词。"""
        # 互斥关键词(手工小集合,够 #22 用)
        mutex_pairs = [
            ("应该", "不该"),
            ("必须", "不必"),
            ("积极", "消极"),
            ("信任", "怀疑"),
        ]
        conflicts: list[Conflict] = []
        cand_body = candidate.body
        for g in existing:
            if g.dimension != candidate.dimension:
                continue
            for a, b in mutex_pairs:
                # 双向检查: 任一对中一个在 candidate,另一个在 existing → 冲突
                if (a in cand_body and b in g.body) or \
                   (b in cand_body and a in g.body):
                    if g.confidence > 0.5:
                        conflicts.append(
                            Conflict(
                                candidate_id=candidate.id,
                                candidate_body=cand_body,
                                existing_growth_id=g.id,
                                existing_growth_body=g.body,
                                reason=f"mutex_pair ({a} vs {b}) with existing high-confidence growth",
                                created_at=datetime.now(tz=timezone.utc).isoformat(),
                            )
                        )
                        break  # 一个 existing 只报一次冲突
        return conflicts

    def _write_conflict(self, conflict: Conflict) -> None:
        """写一条 conflict 到 mortis-subconscious/conflicts/<id>.md。"""
        rel = f"mortis-subconscious/conflicts/{conflict.candidate_id}.md"
        content = (
            f"---\n"
            f"type: conflict\n"
            f"created_at: {conflict.created_at}\n"
            f"candidate_id: {conflict.candidate_id}\n"
            f"existing_id: {conflict.existing_growth_id}\n"
            f"reason: {conflict.reason}\n"
            f"---\n\n"
            f"# Conflict: {conflict.candidate_id} vs {conflict.existing_growth_id}\n\n"
            f"## 候选(candidate, dream)\n\n{conflict.candidate_body}\n\n"
            f"## 现有(existing, high-confidence)\n\n{conflict.existing_growth_body}\n\n"
            f"## 原因\n\n{conflict.reason}\n"
        )
        # subconscious 不在 GROWTH_WHITELIST — 传 None 跳过强检查
        self.vault.write(rel, content, whitelist=None)
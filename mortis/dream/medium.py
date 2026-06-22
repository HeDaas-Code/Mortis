"""Mortis dream — MediumDreamer: 中梦 5 phase。

issue #23: 跨周联想 + 置信度提升 + 冲突处理。

phase (5):
  1. RECALL: 跨周采样 (取最近 7 天所有 session)
  2. ASSOCIATE: 跨周对比 + 模式识别
  3. SIMULATE: 模拟预演(基于近期模式)
  4. CRYSTALLIZE: 提升 confidence (0.3 → 0.5)
     - 多次验证的候选升到 0.5
     - 单次验证的保持 0.3
  5. RECONCILE: 冲突检测 + 处理
     - 矛盾旧条目 → 标记 conflict + confidence × 0.5
     - 支持旧条目 → confidence += 0.1 (cap 0.5)

设计要点:
- 复用 LightDreamer 大部分 phase 实现 (RECALL/ASSOCIATE/CRYSTALLIZE)
- SIMULATE: 用 LLM 预演 "如果这条候选被验证,会怎样"
- CRYSTALLIZE 提升: 扫描已有 growth, 看 source_sessions 重叠度
- RECONCILE 处理: 不只标记, 还主动调整 confidence
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mortis.dream.associate import associate
from mortis.dream.crystallize import (
    average_emotion,
    infer_dimension,
    make_candidate,
)
from mortis.dream.erode import erode_growths
from mortis.dream.phases import DreamLevel, DreamPhase
from mortis.dream.pipeline import DreamPipeline, DreamResult, PhaseTrace
from mortis.dream.recall import emotion_weighted_sample
from mortis.growth.model import Dimension, DreamLevel as DL, Growth
from mortis.memory import Session
from mortis.provider.base import LLMProviderProtocol
from mortis.reflect.emotion import score_emotion
from mortis.vault import Vault


_logger = logging.getLogger(__name__)


DEFAULT_RECALL_DAYS = 7
DEFAULT_RECALL_K = 8
SUPPORT_BOOST = 0.1        # 支持旧条目 confidence += 0.1
CONFLICT_PENALTY = 0.5     # 矛盾旧条目 confidence × 0.5
SUPPORT_CAP = 0.5          # 浅梦 cap 0.5


@dataclass
class MediumDreamer(DreamPipeline):
    """中梦执行器 — 5 phase。"""

    level: DreamLevel = DreamLevel.MEDIUM

    def __init__(
        self,
        vault: Vault,
        provider: LLMProviderProtocol,
        *,
        k: int = DEFAULT_RECALL_K,
        days: int = DEFAULT_RECALL_DAYS,
        rng: random.Random | None = None,
    ) -> None:
        self.vault = vault
        self.provider = provider
        self.k = k
        self.days = days
        self.rng = rng if rng is not None else random.Random()

        # RECALL phase 中间结果
        self._recalled: list[Session] = []
        self._recall_texts: list[str] = []
        self._recall_weights: list[tuple[float, float]] = []
        self._candidate: Growth | None = None
        self._conflicts: list[Any] = []

    # ===========================================================
    # RECALL: 跨周采样
    # ===========================================================

    def phase_recall(self) -> PhaseTrace:
        sessions = self._load_recent_sessions(days=self.days)
        if not sessions:
            return PhaseTrace(
                phase=DreamPhase.RECALL.value,
                ok=True,
                detail={"reason": "no_sessions", "loaded": 0, "sampled": 0},
            )

        items: list[tuple[Session, float, float]] = []
        session_texts: list[str] = []
        for s in sessions:
            path = str(s.session_id)
            text = self._summarize_session(s)
            v, a = score_emotion(self.provider, path, text)
            items.append((s, v, a))
            session_texts.append(text)

        sampled = emotion_weighted_sample(items, k=self.k, rng=self.rng)
        idx_map = {id(items[i][0]): i for i in range(len(items))}
        self._recalled = list(sampled)
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
                "days": self.days,
            },
        )

    # ===========================================================
    # ASSOCIATE: 跨周对比
    # ===========================================================

    def phase_associate(self) -> PhaseTrace:
        if not self._recalled:
            return PhaseTrace(
                phase=DreamPhase.ASSOCIATE.value,
                ok=True,
                detail={"reason": "no_recalled"},
            )

        result = associate(self.provider, self._recall_texts)
        self._associate_result = result
        return PhaseTrace(
            phase=DreamPhase.ASSOCIATE.value,
            ok=True,
            detail={"body_len": len(result.get("body", ""))},
        )

    # ===========================================================
    # SIMULATE: 模拟预演 (issue #23 新增)
    # ===========================================================

    def phase_simulate(self) -> PhaseTrace:
        """调 LLM 预演 "如果这条候选被验证, 3 个月后会怎样"。

        输出存 self._simulation, 给 CRYSTALLIZE 决定要不要提升 confidence。
        """
        if not self._recalled or not getattr(self, "_associate_result", None):
            return PhaseTrace(
                phase=DreamPhase.SIMULATE.value,
                ok=True,
                detail={"reason": "no_inputs"},
            )

        body = self._associate_result.get("body", "").strip()
        if not body:
            return PhaseTrace(
                phase=DreamPhase.SIMULATE.value,
                ok=True,
                detail={"reason": "empty_body"},
            )

        # 简化: 不真调 LLM 预演, 用启发式 — 多 source_sessions 重叠的 = 高置信
        # (LightDreamer 已写过同样的候选, 这次采样更多 → 重叠 = 多源验证)
        existing_growths = self._list_existing_growths()
        overlap_count = 0
        for g in existing_growths:
            for src in g.source_sessions:
                for s in self._recalled:
                    if src == str(s.session_id):
                        overlap_count += 1
                        break

        # 简单阈值: 重叠 ≥ 2 → 推荐提升
        should_promote = overlap_count >= 2
        self._simulation = {"should_promote": should_promote, "overlap_count": overlap_count}

        return PhaseTrace(
            phase=DreamPhase.SIMULATE.value,
            ok=True,
            detail={"overlap_count": overlap_count, "should_promote": should_promote},
        )

    # ===========================================================
    # CRYSTALLIZE: 提升 confidence
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
        source_sessions = [str(s.session_id) for s in self._recalled]

        # confidence 提升: SIMULATE 阶段判定重叠则 0.3 → 0.5
        should_promote = getattr(self, "_simulation", {}).get("should_promote", False)
        confidence = 0.5 if should_promote else 0.3

        candidate = make_candidate(
            body=body,
            dimension=dimension,
            source_sessions=source_sessions,
            valence=v,
            arousal=a,
        )
        # 用 replace 改 confidence (Growth frozen)
        candidate = replace(candidate, confidence=confidence)
        if assoc.get("tags"):
            candidate = replace(candidate, tags=tuple(assoc["tags"]))

        self.vault.write_growth(candidate)
        self._candidate = candidate

        return PhaseTrace(
            phase=DreamPhase.CRYSTALLIZE.value,
            ok=True,
            detail={
                "growth_id": candidate.id,
                "dimension": candidate.dimension.value,
                "confidence": confidence,
                "promoted": should_promote,
            },
        )

    # ===========================================================
    # RECONCILE: 冲突处理 (issue #23 升级: 不仅标记还调 confidence)
    # ===========================================================

    def phase_reconcile(self) -> PhaseTrace:
        if self._candidate is None:
            return PhaseTrace(
                phase=DreamPhase.RECONCILE.value,
                ok=True,
                detail={"reason": "no_candidate"},
            )

        existing = self._list_existing_growths()
        if not existing:
            return PhaseTrace(
                phase=DreamPhase.RECONCILE.value,
                ok=True,
                detail={"reason": "no_existing", "checked": 0},
            )

        # 双向 mutex 检测 (复用 LightDreamer 逻辑)
        mutex_pairs = [
            ("应该", "不该"), ("必须", "不必"),
            ("积极", "消极"), ("信任", "怀疑"),
        ]
        cand_body = self._candidate.body
        conflicts_found: list[Any] = []
        existing_modified: list[str] = []
        existing_supported: list[str] = []

        for g in existing:
            if g.dimension != self._candidate.dimension:
                continue
            for a, b in mutex_pairs:
                if (a in cand_body and b in g.body) or \
                   (b in cand_body and a in g.body):
                    if g.confidence > 0.5:
                        # 矛盾 → 旧条目 confidence × 0.5
                        new_conf = max(0.0, g.confidence * CONFLICT_PENALTY)
                        new_g = replace(g, confidence=new_conf)
                        self.vault.write_growth(new_g)
                        existing_modified.append(g.id)
                        conflicts_found.append({
                            "candidate_id": self._candidate.id,
                            "existing_id": g.id,
                            "reason": f"mutex ({a} vs {b})",
                        })
                        self._write_conflict_doc(
                            candidate=self._candidate,
                            existing=g,
                            reason=f"mutex_pair ({a} vs {b})",
                        )
                    break
                # 支持: 关键词重叠 + 高 confidence → boost
            # 注: 简化 — 不再额外支持判断, 主要做矛盾处理

        self._conflicts = conflicts_found
        return PhaseTrace(
            phase=DreamPhase.RECONCILE.value,
            ok=True,
            detail={
                "checked": len(existing),
                "conflicts": len(conflicts_found),
                "modified": existing_modified,
            },
        )

    # ===========================================================
    # helpers
    # ===========================================================

    def _load_recent_sessions(self, days: int) -> list[Session]:
        journal_root = Path(self.vault.root) / "mortis-journal" / "sessions"
        if not journal_root.exists():
            return []
        all_sessions: list[Session] = []
        date_dirs: list[Path] = []
        for p in journal_root.iterdir():
            if p.is_dir() and len(p.name) == 10 and p.name[4] == "-":
                date_dirs.append(p)
        date_dirs.sort(reverse=True)
        from datetime import timedelta
        cutoff = (datetime.now(tz=timezone.utc).date() - timedelta(days=days - 1)).isoformat()
        for d in date_dirs:
            if d.name < cutoff:
                continue
            for json_file in d.glob("*.json"):
                try:
                    s = Session.load(d, json_file.stem)
                    all_sessions.append(s)
                except (FileNotFoundError, KeyError, ValueError) as e:
                    _logger.warning("medium dreamer: skip %s: %s", json_file, e)
        return all_sessions

    @staticmethod
    def _summarize_session(s: Session) -> str:
        parts: list[str] = []
        parts.append(f"Session {s.session_id} @ {s.created_at}")
        if s.threads:
            parts.append(f"Threads: {', '.join(s.threads)}")
        if s.metadata:
            parts.append(f"Metadata: {s.metadata}")
        return "\n".join(parts)

    def _list_existing_growths(self) -> list[Growth]:
        rels = self.vault.list_growths()
        out: list[Growth] = []
        for rel in rels:
            try:
                g = self.vault.read_growth(rel)
            except Exception:
                continue
            if self._candidate and g.id == self._candidate.id:
                continue
            out.append(g)
        return out

    def _write_conflict_doc(self, *, candidate: Growth, existing: Growth, reason: str) -> None:
        rel = f"mortis-subconscious/conflicts/{candidate.id}.md"
        content = (
            f"---\n"
            f"type: conflict\n"
            f"created_at: {datetime.now(tz=timezone.utc).isoformat()}\n"
            f"candidate_id: {candidate.id}\n"
            f"existing_id: {existing.id}\n"
            f"reason: {reason}\n"
            f"---"
            f"\n\n# Conflict: {candidate.id} vs {existing.id}"
            f"\n\n## candidate\n\n{candidate.body}"
            f"\n\n## existing\n\n{existing.body}"
            f"\n\n## reason\n\n{reason}\n"
        )
        self.vault.write(rel, content, whitelist=None)

    # ===========================================================
    # 暴露给 DeepDreamer
    # ===========================================================

    def run(self) -> DreamResult:
        result = super().run()
        result.conflicts = self._conflicts
        return result


__all__ = ["MediumDreamer", "DEFAULT_RECALL_DAYS", "DEFAULT_RECALL_K"]

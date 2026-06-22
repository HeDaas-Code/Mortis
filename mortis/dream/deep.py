"""Mortis dream — DeepDreamer: 深梦 7 phase (全量)。

issue #23: 全量重读 growth → 重新校准 → 跨维度联想 → 大规模侵蚀 → drift 计算 → seed-check → owner 通知。

phase (7):
  1. RECALL: 全量重读所有 growth (不是 session, 而是已有 growth)
  2. ASSOCIATE: 跨维度联想(identity ↔ values ↔ tone 等)
  3. SIMULATE: 模拟预演(基于全部 growth)
  4. CRYSTALLIZE: 重新校准 confidence (基于多源验证)
  5. RECONCILE: 大规模冲突处理
  6. ERODE: 应用侵蚀规则 (移 archive)
  7. SEED_CHECK: 调 LLM 算 drift, 通知 owner

设计要点:
- RECALL 与 Light/Medium 不同 — 重读 growth 而不是 sessions
- ERODE 调用 erode.erode_growths 拿 (survived, to_archive)
- SEED_CHECK 调用 seed_check.seed_check 拿 DriftReport
- owner 通知只标记 needs_owner_notify, 不真发通道 (issue #24 决定)
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mortis.dream.crystallize import infer_dimension
from mortis.dream.erode import erode_growths, days_since_validated
from mortis.dream.phases import DreamLevel, DreamPhase
from mortis.dream.pipeline import DreamPipeline, DreamResult, PhaseTrace
from mortis.dream.seed_check import seed_check, DriftReport
from mortis.growth.model import Dimension, Growth
from mortis.growth.vault_layout import growth_archive_rel, growth_rel
from mortis.provider.base import LLMProviderProtocol
from mortis.seed import Seed
from mortis.vault import Vault


_logger = logging.getLogger(__name__)


@dataclass
class DeepDreamer(DreamPipeline):
    """深梦执行器 — 7 phase 全量。"""

    level: DreamLevel = DreamLevel.DEEP

    def __init__(
        self,
        vault: Vault,
        provider: LLMProviderProtocol,
        seed: Seed,
        *,
        rng: random.Random | None = None,
        drift_threshold: float = 0.7,
    ) -> None:
        self.vault = vault
        self.provider = provider
        self.seed = seed
        self.rng = rng if rng is not None else random.Random()
        self.drift_threshold = drift_threshold

        # 全量 growth 缓存 (RECALL phase 一次性加载)
        self._all_growths: list[Growth] = []
        self._drift: DriftReport | None = None
        self._conflicts: list[dict[str, str]] = []
        self._archived: list[str] = []

    # ===========================================================
    # RECALL: 全量重读 growth
    # ===========================================================

    def phase_recall(self) -> PhaseTrace:
        rels = self.vault.list_growths()
        all_g: list[Growth] = []
        for rel in rels:
            try:
                g = self.vault.read_growth(rel)
                all_g.append(g)
            except Exception as e:
                _logger.warning("deep dreamer: skip %s: %s", rel, e)

        # 过滤 archive/ (不算活跃)
        active = [g for g in all_g if "archive/" not in growth_rel(g.dimension, g.id)]

        self._all_growths = active
        return PhaseTrace(
            phase=DreamPhase.RECALL.value,
            ok=True,
            detail={"total_loaded": len(all_g), "active": len(active)},
        )

    # ===========================================================
    # ASSOCIATE: 跨维度联想
    # ===========================================================

    def phase_associate(self) -> PhaseTrace:
        if not self._all_growths:
            return PhaseTrace(
                phase=DreamPhase.ASSOCIATE.value,
                ok=True,
                detail={"reason": "no_growths"},
            )

        # 简化: 按 dimension 分组, 计算每维 count
        by_dim: dict[str, int] = {}
        for g in self._all_growths:
            by_dim[g.dimension.value] = by_dim.get(g.dimension.value, 0) + 1
        self._association = by_dim

        return PhaseTrace(
            phase=DreamPhase.ASSOCIATE.value,
            ok=True,
            detail={"by_dimension": by_dim, "growth_count": len(self._all_growths)},
        )

    # ===========================================================
    # SIMULATE: 模拟预演 (基于全量)
    # ===========================================================

    def phase_simulate(self) -> PhaseTrace:
        if not self._all_growths:
            return PhaseTrace(
                phase=DreamPhase.SIMULATE.value,
                ok=True,
                detail={"reason": "no_growths"},
            )

        # 简化: 计算平均 confidence
        avg_conf = sum(g.confidence for g in self._all_growths) / len(self._all_growths)
        self._avg_confidence = avg_conf

        return PhaseTrace(
            phase=DreamPhase.SIMULATE.value,
            ok=True,
            detail={"avg_confidence": round(avg_conf, 3)},
        )

    # ===========================================================
    # CRYSTALLIZE: 重新校准
    # ===========================================================

    def phase_crystallize(self) -> PhaseTrace:
        if not self._all_growths:
            return PhaseTrace(
                phase=DreamPhase.CRYSTALLIZE.value,
                ok=True,
                detail={"reason": "no_growths"},
            )

        # 简化: 重新校准 = 把所有 confidence ≥ 0.5 的标 last_validated=now
        # (RFC §4.4 — 多次验证 → 提升)
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        promoted: list[str] = []
        for g in self._all_growths:
            if g.confidence >= 0.5:
                new_g = replace(g, last_validated=now_iso)
                self.vault.write_growth(new_g)
                promoted.append(g.id)

        return PhaseTrace(
            phase=DreamPhase.CRYSTALLIZE.value,
            ok=True,
            detail={"recalibrated": len(promoted)},
        )

    # ===========================================================
    # RECONCILE: 大规模冲突处理
    # ===========================================================

    def phase_reconcile(self) -> PhaseTrace:
        if not self._all_growths:
            return PhaseTrace(
                phase=DreamPhase.RECONCILE.value,
                ok=True,
                detail={"reason": "no_growths"},
            )

        # 双向 mutex 检测
        mutex_pairs = [
            ("应该", "不该"), ("必须", "不必"),
            ("积极", "消极"), ("信任", "怀疑"),
        ]
        conflicts_found: list[dict[str, str]] = []
        # 同维度按 confidence 排序, 高 confidence 是"既得", 低 confidence 是"挑战"
        by_dim: dict[Dimension, list[Growth]] = {}
        for g in self._all_growths:
            by_dim.setdefault(g.dimension, []).append(g)
        for dim, gs in by_dim.items():
            gs_sorted = sorted(gs, key=lambda x: x.confidence, reverse=True)
            for i, hi in enumerate(gs_sorted):
                for lo in gs_sorted[i + 1:]:
                    if hi.confidence < 0.5 or lo.confidence < 0.3:
                        continue
                    for a, b in mutex_pairs:
                        if (a in hi.body and b in lo.body) or \
                           (b in hi.body and a in lo.body):
                            # lo (低 conf) 是被高 conf 矛盾的, lo 减半
                            new_conf = max(0.0, lo.confidence * 0.5)
                            new_lo = replace(lo, confidence=new_conf)
                            self.vault.write_growth(new_lo)
                            conflicts_found.append({
                                "high_id": hi.id,
                                "low_id": lo.id,
                                "reason": f"mutex ({a} vs {b})",
                            })
                            break
                    break  # 每个 lo 只报一次

        self._conflicts = conflicts_found
        return PhaseTrace(
            phase=DreamPhase.RECONCILE.value,
            ok=True,
            detail={"checked": len(self._all_growths), "conflicts": len(conflicts_found)},
        )

    # ===========================================================
    # ERODE: 侵蚀
    # ===========================================================

    def phase_erode(self) -> PhaseTrace:
        if not self._all_growths:
            return PhaseTrace(
                phase=DreamPhase.ERODE.value,
                ok=True,
                detail={"reason": "no_growths"},
            )

        survived, to_archive = erode_growths(self._all_growths)

        # 写回 survived (可能 confidence 已下降)
        for g in survived:
            try:
                self.vault.write_growth(g)
            except Exception as e:
                _logger.warning("deep erode: write back %s failed: %s", g.id, e)

        # 移到 archive/
        archived: list[str] = []
        for g in to_archive:
            try:
                # 写 archive 副本
                archive_rel = growth_archive_rel(g.dimension, g.id)
                from mortis.growth.writer import write_growth_obsidian
                content = write_growth_obsidian(g)
                self.vault.write(archive_rel, content, whitelist=None)
                # 删除原文件 (走 _safe_path + unlink)
                orig_rel = growth_rel(g.dimension, g.id)
                orig_path = self.vault._safe_path(orig_rel)
                if orig_path.exists():
                    orig_path.unlink()
                archived.append(g.id)
            except Exception as e:
                _logger.warning("deep erode: archive %s failed: %s", g.id, e)

        self._archived = archived
        return PhaseTrace(
            phase=DreamPhase.ERODE.value,
            ok=True,
            detail={
                "survived": len(survived),
                "archived": len(archived),
                "archived_ids": archived,
            },
        )

    # ===========================================================
    # SEED_CHECK: drift
    # ===========================================================

    def phase_seed_check(self) -> PhaseTrace:
        # 重新读 survive 后的 growth (erode 已写过)
        rels = self.vault.list_growths()
        active: list[Growth] = []
        for rel in rels:
            try:
                g = self.vault.read_growth(rel)
                if "archive/" not in rel:
                    active.append(g)
            except Exception:
                continue

        # 拼 growth 摘要 (前 200 字 per growth)
        summary_lines = []
        for g in active[:50]:  # 限 50 条避免 prompt 爆
            summary_lines.append(f"[{g.id}] {g.dimension.value}: {g.body[:200]}")
        summary = "\n".join(summary_lines) if summary_lines else "(no active growths)"

        try:
            report = seed_check(
                seed=self.seed,
                growth_summary=summary,
                provider=self.provider,
                threshold=self.drift_threshold,
            )
        except Exception as e:
            _logger.warning("deep SEED_CHECK failed: %s", e)
            return PhaseTrace(
                phase=DreamPhase.SEED_CHECK.value,
                ok=False,
                detail={"error": str(e)},
            )

        self._drift = report

        # 如果需要通知 owner, 写标记文件
        if report.needs_owner_notify:
            try:
                rel = "mortis-subconscious/owner-notify.json"
                content = (
                    f'{{"needs_notify": true, '
                    f'"drift_total": {report.total_drift}, '
                    f'"threshold": {report.threshold}, '
                    f'"reported_at": "{datetime.now(tz=timezone.utc).isoformat()}"}}'
                )
                self.vault.write(rel, content, whitelist=None)
            except Exception as e:
                _logger.warning("deep SEED_CHECK: notify write failed: %s", e)

        return PhaseTrace(
            phase=DreamPhase.SEED_CHECK.value,
            ok=True,
            detail={
                "total_drift": round(report.total_drift, 3),
                "needs_owner_notify": report.needs_owner_notify,
                "per_dim_alerts": {
                    d.value: v for d, v in report.per_dim_alerts.items() if v
                },
            },
        )

    def run(self) -> DreamResult:
        result = super().run()
        # 附加 drift + conflicts 到 result
        result.conflicts = self._conflicts
        if self._drift is not None:
            # DriftReport 暂存为 dict (result.candidates 是 list, 借用 conflict 字段)
            setattr(result, "drift", {
                "total": self._drift.total_drift,
                "per_dimension": {d.value: v for d, v in self._drift.per_dimension.items()},
                "needs_owner_notify": self._drift.needs_owner_notify,
            })
        return result


__all__ = ["DeepDreamer"]

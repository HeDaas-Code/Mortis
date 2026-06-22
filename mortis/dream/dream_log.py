"""Mortis dream — 梦境日志写入。

issue #23: 每次 dream 写日志到 mortis-dream-log/<level>/YYYY-MM-DD-<level>.md。
即使失败也记失败原因。

布局:
    mortis-dream-log/
    ├── light/2026-06-22-light.md
    ├── medium/2026-06-22-medium.md
    └── deep/2026-06-22-deep.md

日志字段 (frontmatter + body):
    level: light/medium/deep
    started_at / finished_at: ISO8601
    duration_seconds: float
    ok: bool
    phase_traces: list of {phase, ok, detail}
    candidates: list of growth id (写出的 candidate)
    conflicts: list of {candidate_id, existing_id}
    drift: dict (deep 才有)

写入: vault.write(rel, content, whitelist=None) — mortis-dream-log/ 不在 GROWTH_WHITELIST
读出 (ClockAgent 用): 扫目录按 mtime 取最近
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mortis.dream.phases import DreamLevel
from mortis.dream.pipeline import DreamResult, PhaseTrace
from mortis.vault import Vault


_logger = logging.getLogger(__name__)


DREAM_LOG_DIR = "mortis-dream-log"


@dataclass(frozen=True)
class DreamLog:
    """单次梦境日志(写入文件 + 内存返回值)。"""
    rel_path: str
    level: DreamLevel
    started_at: str
    finished_at: str
    duration_seconds: float
    ok: bool
    traces: tuple[PhaseTrace, ...] = field(default_factory=tuple)
    candidates: tuple[str, ...] = field(default_factory=tuple)
    conflicts: tuple[dict[str, str], ...] = field(default_factory=tuple)
    drift: dict[str, float] | None = None
    error: str | None = None


def dream_log_rel(level: DreamLevel, today: str | None = None) -> str:
    """生成日志相对路径:mortis-dream-log/<level>/YYYY-MM-DD-<level>.md。"""
    if today is None:
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    return f"{DREAM_LOG_DIR}/{level.value}/{today}-{level.value}.md"


def write_dream_log(
    vault: Vault,
    result: DreamResult,
    *,
    started_at: datetime,
    finished_at: datetime,
    error: str | None = None,
) -> DreamLog:
    """把 DreamResult 写成日志文件。失败也写(带 ok=False + error)。

    Args:
        vault: vault 根。
        result: DreamPipeline.run() 返回值。
        started_at: dream 开始时间(UTC)。
        finished_at: dream 结束时间(UTC)。
        error: 顶层异常(若 pipeline 在 setup 阶段就挂了)。

    Returns:
        DreamLog — 含 rel_path + 全部元数据。
    """
    level = result.level
    today = finished_at.strftime("%Y-%m-%d")
    rel = dream_log_rel(level, today)
    duration = (finished_at - started_at).total_seconds()

    # 收集 traces
    traces = tuple(result.traces)
    # 收集 candidates (growth id)
    candidates = tuple(
        c.id for c in (result.candidates or [])
    ) if result.candidates else ()
    # 收集 conflicts (按 .id 或 dict)
    conflicts: tuple[dict[str, str], ...] = ()
    if result.conflicts:
        conflicts = tuple(
            {
                "candidate_id": getattr(c, "candidate_id", ""),
                "existing_id": getattr(c, "existing_growth_id", ""),
            }
            for c in result.conflicts
        )

    body = _render_log(
        level=level,
        started_at=started_at.isoformat(),
        finished_at=finished_at.isoformat(),
        duration=duration,
        ok=result.ok and error is None,
        traces=traces,
        candidates=candidates,
        conflicts=conflicts,
        drift=getattr(result, "drift", None),
        error=error,
    )

    try:
        vault.write(rel, body, whitelist=None)
    except Exception as e:
        _logger.error("dream_log.write failed: %s", e)
        # 不抛错 — 写日志失败不阻断梦本身

    return DreamLog(
        rel_path=rel,
        level=level,
        started_at=started_at.isoformat(),
        finished_at=finished_at.isoformat(),
        duration_seconds=duration,
        ok=result.ok and error is None,
        traces=traces,
        candidates=candidates,
        conflicts=conflicts,
        drift=getattr(result, "drift", None),
        error=error,
    )


def _render_log(
    *,
    level: DreamLevel,
    started_at: str,
    finished_at: str,
    duration: float,
    ok: bool,
    traces: tuple[PhaseTrace, ...],
    candidates: tuple[str, ...],
    conflicts: tuple[dict[str, str], ...],
    drift: dict[str, float] | None,
    error: str | None,
) -> str:
    """渲染日志 markdown。"""
    parts: list[str] = []
    parts.append("---")
    parts.append(f"level: {level.value}")
    parts.append(f"started_at: {started_at}")
    parts.append(f"finished_at: {finished_at}")
    parts.append(f"duration_seconds: {duration:.2f}")
    parts.append(f"ok: {str(ok).lower()}")
    if error:
        parts.append(f"error: \"{error}\"")
    parts.append("---")
    parts.append("")
    parts.append(f"# Dream Log: {level.value} @ {started_at}")
    parts.append("")

    # traces
    parts.append("## Phase Traces")
    parts.append("")
    if traces:
        parts.append("| Phase | OK | Detail |")
        parts.append("|-------|----|----|")
        for t in traces:
            detail_str = ", ".join(f"{k}={v}" for k, v in (t.detail or {}).items())
            parts.append(f"| {t.phase} | {'✓' if t.ok else '✗'} | {detail_str} |")
    else:
        parts.append("(no traces — pipeline 未开始)")
    parts.append("")

    # candidates
    if candidates:
        parts.append("## Candidates")
        parts.append("")
        for c in candidates:
            parts.append(f"- `{c}`")
        parts.append("")

    # conflicts
    if conflicts:
        parts.append("## Conflicts")
        parts.append("")
        for c in conflicts:
            parts.append(f"- candidate `{c.get('candidate_id', '')}` vs existing `{c.get('existing_id', '')}`")
        parts.append("")

    # drift (deep 才有)
    if drift:
        parts.append("## Drift")
        parts.append("")
        for dim, val in drift.items():
            parts.append(f"- {dim}: {val:.2f}")
        parts.append("")

    return "\n".join(parts)


__all__ = [
    "DREAM_LOG_DIR",
    "DreamLog",
    "dream_log_rel",
    "write_dream_log",
]

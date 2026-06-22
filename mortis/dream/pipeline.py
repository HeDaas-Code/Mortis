"""Mortis dream — pipeline 基类。

issue #22: 公共 phase runner 框架,Light / Medium / Deep 都继承。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from mortis.dream.phases import DreamLevel, PHASES_BY_LEVEL


_logger = logging.getLogger(__name__)


@dataclass
class PhaseTrace:
    """单次 phase 执行的 trace — 用于调试 + 日志 + 测试断言。"""
    phase: str
    ok: bool
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class DreamResult:
    """梦境执行结果 — Light/Medium/Deep 通用返回。"""
    level: DreamLevel
    traces: list[PhaseTrace] = field(default_factory=list)
    candidates: list[Any] = field(default_factory=list)   # Growth 候选
    conflicts: list[Any] = field(default_factory=list)    # Conflict 记录(写入 subconscious)

    @property
    def ok(self) -> bool:
        return all(t.ok for t in self.traces)

    def trace_for(self, phase: str) -> PhaseTrace | None:
        for t in self.traces:
            if t.phase == phase:
                return t
        return None


class DreamPipeline:
    """梦境流水线基类。

    子类(目前只有 LightDreamer, #22 范围)实现具体的 phase 步骤;
    基类负责按 PHASES_BY_LEVEL 顺序调用 phase_<name>() 方法。
    """

    level: DreamLevel = DreamLevel.LIGHT  # 子类覆盖

    def run(self) -> DreamResult:
        result = DreamResult(level=self.level)
        for phase in PHASES_BY_LEVEL[self.level]:
            method_name = f"phase_{phase.value}"
            method = getattr(self, method_name, None)
            if method is None:
                _logger.warning(
                    "dream pipeline: phase %s not implemented on %s, skipping",
                    phase.value,
                    type(self).__name__,
                )
                result.traces.append(
                    PhaseTrace(phase=phase.value, ok=False, detail={"reason": "not_implemented"})
                )
                continue
            try:
                trace = method()
                result.traces.append(trace)
            except Exception as e:
                _logger.exception("dream pipeline: phase %s failed: %s", phase.value, e)
                result.traces.append(
                    PhaseTrace(phase=phase.value, ok=False, detail={"error": str(e)})
                )
                # 失败 phase 后续跳过 — 整条流水线视为失败
                break
        return result
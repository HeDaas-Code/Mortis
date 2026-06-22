"""Mortis dream — SEED-CHECK phase: drift 计算。

issue #23: 计算 growth 层与 seed 的距离。LLM 自评(按 RFC-001-open-questions §1)。

设计要点:
- provider 输出每个 Dimension 的 drift [0.0, 1.0]
- 总 drift = 加权平均 (per-dimension max 权重 = 1.0)
- 任一维度 drift > 0.5 → 标记 (per_dim_alert)
- 总体 drift > 阈值 (默认 0.7) → needs_owner_notify

纯计算 + 单次 LLM 调用 — 不写 vault, 只返回 DriftReport dataclass。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from mortis.growth.model import Dimension
from mortis.provider.base import LLMProviderProtocol
from mortis.seed import Seed


_logger = logging.getLogger(__name__)


DEFAULT_DRIFT_THRESHOLD = 0.7
PER_DIM_ALERT_THRESHOLD = 0.5


@dataclass(frozen=True)
class DriftReport:
    """drift 检测报告 — SEED-CHECK phase 输出。"""
    per_dimension: dict[Dimension, float]   # 7 维度各自 drift (0.0-1.0)
    total_drift: float                      # 加权平均 (max per-dim)
    per_dim_alerts: dict[Dimension, bool]   # dim > 0.5 → True
    needs_owner_notify: bool                # total > 阈值
    threshold: float                        # 触发通知的阈值
    raw_response: str                       # LLM 原文(调试用)

    def summary(self) -> str:
        """一行字符串摘要 — 写 dream-log 用。"""
        high = [d.value for d, v in self.per_dimension.items() if v > self.per_dim_alerts[d.value if False else Dimension.IDENTITY]]
        # 简化为 max-dim
        if self.per_dimension:
            max_dim = max(self.per_dimension.items(), key=lambda kv: kv[1])
            return f"drift={self.total_drift:.2f} max_dim={max_dim[0].value}={max_dim[1]:.2f}"
        return f"drift={self.total_drift:.2f}"


# ============================================================
# Prompt
# ============================================================


_DRIFT_PROMPT = """请评估 mortis 主人格当前 growth 记忆相对 seed 的人格"漂移"程度。

按以下 7 个维度分别打分 (0.0 完全一致, 1.0 完全偏离):
{seven_dims}

要求:
1. 严格输出 JSON: {{"identity": <num>, "values": <num>, "tone": <num>, "agency": <num>, "relations": <num>, "creativity": <num>, "mortality": <num>}}
2. 数字 ∈ [0.0, 1.0],保留 1 位小数
3. 不要 markdown 包裹,不要解释

seed (人格基础):
\"\"\"
{seed_text}
\"\"\"

最近 growth 摘要:
\"\"\"
{growth_summary}
\"\"\"
"""


# ============================================================
# 解析
# ============================================================


def _parse_drift(raw: str) -> dict[Dimension, float]:
    """从 LLM 响应解析 7 维 drift dict。失败回退全 0。"""
    if not raw:
        _logger.warning("seed_check: empty response, fallback to all 0")
        return {d: 0.0 for d in Dimension}

    # 策略 1: 严格 JSON
    try:
        data = json.loads(raw.strip())
        if isinstance(data, dict):
            return _extract_dim_floats(data)
    except (json.JSONDecodeError, ValueError):
        pass

    # 策略 2: regex 抓每个维度
    result: dict[Dimension, float] = {}
    for d in Dimension:
        m = re.search(rf'"{d.value}"\s*:\s*([\d.]+)', raw)
        if m:
            try:
                result[d] = max(0.0, min(1.0, float(m.group(1))))
            except ValueError:
                result[d] = 0.0
        else:
            result[d] = 0.0

    if not result:
        _logger.warning("seed_check: failed to parse, fallback to all 0")
        return {d: 0.0 for d in Dimension}

    return result


def _extract_dim_floats(data: dict) -> dict[Dimension, float]:
    """从 dict 里抽 7 维数字。"""
    result: dict[Dimension, float] = {}
    for d in Dimension:
        v = data.get(d.value, 0.0)
        try:
            result[d] = max(0.0, min(1.0, float(v)))
        except (ValueError, TypeError):
            result[d] = 0.0
    return result


# ============================================================
# 主 API
# ============================================================


def seed_check(
    seed: Seed,
    growth_summary: str,
    provider: LLMProviderProtocol,
    *,
    threshold: float = DEFAULT_DRIFT_THRESHOLD,
    per_dim_alert: float = PER_DIM_ALERT_THRESHOLD,
) -> DriftReport:
    """计算 growth 层与 seed 的距离。

    Args:
        seed: mortis seed (人格基础)
        growth_summary: 已有 growth 的摘要文本 (由调用方准备)
        provider: LLM provider
        threshold: 总 drift 阈值,超过 → needs_owner_notify (默认 0.7)
        per_dim_alert: 单维度 drift 阈值,超过 → per_dim_alerts[dim]=True (默认 0.5)

    Returns:
        DriftReport — 含 per-dim drift + total + alerts + raw。
    """
    seven_dims = ", ".join(d.value for d in Dimension)
    seed_text = _seed_to_text(seed)
    prompt = (
        _DRIFT_PROMPT
        .replace("{seven_dims}", seven_dims)
        .replace("{seed_text}", seed_text)
        .replace("{growth_summary}", growth_summary)
    )
    raw = provider.generate_text(prompt)
    per_dim = _parse_drift(raw)

    # total = max per-dim (简单最大 — owner 看最偏离那一维)
    total = max(per_dim.values()) if per_dim else 0.0

    alerts = {d: (v > per_dim_alert) for d, v in per_dim.items()}

    return DriftReport(
        per_dimension=per_dim,
        total_drift=total,
        per_dim_alerts=alerts,
        needs_owner_notify=total > threshold,
        threshold=threshold,
        raw_response=raw,
    )


def _seed_to_text(seed: Seed) -> str:
    """把 seed 序列化为 prompt 用的纯文本(7 维度内容拼一起)。"""
    parts: list[str] = []
    for d in Dimension:
        content = seed.get_dimension(d.value)
        if content:
            parts.append(f"## {d.value}\n{content}")
    return "\n\n".join(parts) if parts else "(empty seed)"


__all__ = [
    "DEFAULT_DRIFT_THRESHOLD",
    "PER_DIM_ALERT_THRESHOLD",
    "DriftReport",
    "seed_check",
]

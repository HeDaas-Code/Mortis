"""Mortis seed — 七维度 schema 定义。"""

from __future__ import annotations

# 七维度 schema 硬编码（契约）。改这里 = 改人格契约，要先开 ADR。
SEVEN_DIMENSIONS: tuple[str, ...] = (
    "identity",
    "values",
    "tone",
    "agency",
    "relations",
    "creativity",
    "mortality",
)

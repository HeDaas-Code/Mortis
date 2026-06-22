"""Mortis toolagent — VaultStatsAgent: vault 维度/置信度统计。

issue #25: vault 只读 Agent。统计文件数、维度分布、置信度直方图。

输入 schema (input dict):
    dimension: str | None = None   # 可选维度过滤

输出 schema (ToolResult.data dict):
    total_files: int
    by_dimension: dict[str, int]   # dimension_name -> count
    confidence_histogram: list[int]  # 10 桶 [0-0.1, 0.1-0.2, ..., 0.9-1.0]
"""

from __future__ import annotations

from collections import Counter

from mortis.toolagent.base import ToolResult
from mortis.vault import Vault


CONFIDENCE_BUCKETS = 10  # 0.0-1.0 分 10 桶


class VaultStatsAgent:
    """vault 统计 — 总数 / 维度分布 / 置信度直方图。"""

    agent_id: str = "vault:stats"

    def __init__(self, vault: Vault) -> None:
        self.vault = vault

    def execute(self, input: dict) -> ToolResult:
        dimension_filter = input.get("dimension")
        try:
            rels = self.vault.list_growths()  # 所有 growth 路径
        except Exception as e:  # noqa: BLE001
            return ToolResult(success=False, data=None, error=str(e))

        by_dimension: Counter[str] = Counter()
        histogram = [0] * CONFIDENCE_BUCKETS
        total = 0
        for rel in rels:
            try:
                g = self.vault.read_growth(rel)
            except Exception:
                continue
            by_dimension[g.dimension.value] += 1
            bucket = min(int(g.confidence * CONFIDENCE_BUCKETS), CONFIDENCE_BUCKETS - 1)
            if bucket < 0:
                bucket = 0
            histogram[bucket] += 1
            total += 1

        if dimension_filter:
            # 过滤后 total = by_dimension[dimension_filter]
            total = by_dimension.get(dimension_filter, 0)

        return ToolResult(
            success=True,
            data={
                "total_files": total,
                "by_dimension": dict(by_dimension),
                "confidence_histogram": histogram,
            },
            error=None,
        )


__all__ = ["VaultStatsAgent"]

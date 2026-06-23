"""Mortis toolagent — VaultStatsAgent: vault 维度/置信度统计 + LLM 分析。

issue #25: vault 只读 Agent。统计文件数、维度分布、置信度直方图。

issue #63: 新增 LLM 分析能力 — 对统计结果进行解读和洞察分析。

输入 schema (input dict):
    dimension: str | None = None   # 可选维度过滤
    analyze: bool = False          # 是否启用 LLM 分析 (issue #63)

输出 schema (ToolResult.data dict):
    total_files: int
    by_dimension: dict[str, int]   # dimension_name -> count
    confidence_histogram: list[int]  # 10 桶 [0-0.1, 0.1-0.2, ..., 0.9-1.0]
    analysis: str | None            # analyze=True 时的 LLM 分析结果
"""

from __future__ import annotations

from collections import Counter

from mortis.provider.base import LLMProviderProtocol
from mortis.toolagent.base import ToolResult
from mortis.vault import Vault


CONFIDENCE_BUCKETS = 10  # 0.0-1.0 分 10 桶


class VaultStatsAgent:
    """vault 统计 — 总数 / 维度分布 / 置信度直方图 + LLM 分析。"""

    agent_id: str = "vault:stats"

    def __init__(self, vault: Vault, provider: LLMProviderProtocol | None = None) -> None:
        self.vault = vault
        self.provider = provider

    def execute(self, input: dict) -> ToolResult:
        dimension_filter = input.get("dimension")
        analyze = bool(input.get("analyze", False))
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

        # LLM 分析 (issue #63)
        analysis: str | None = None
        if analyze and self.provider:
            analysis = self._analyze_stats(total, dict(by_dimension), histogram)

        return ToolResult(
            success=True,
            data={
                "total_files": total,
                "by_dimension": dict(by_dimension),
                "confidence_histogram": histogram,
                "analysis": analysis,
            },
            error=None,
        )

    def _analyze_stats(
        self,
        total_files: int,
        by_dimension: dict[str, int],
        histogram: list[int],
    ) -> str | None:
        """通过 LLM 分析统计数据 (issue #63)。

        Args:
            total_files: 总文件数。
            by_dimension: 维度分布。
            histogram: 置信度直方图。

        Returns:
            LLM 分析结果,或 None (无 provider 或失败)。
        """
        if not self.provider:
            return None

        dimension_list = "\n".join([
            f"- {dim}: {count} 条" for dim, count in sorted(by_dimension.items())
        ])

        histogram_str = "\n".join([
            f"- {i * 0.1:.1f}-{(i + 1) * 0.1:.1f}: {count} 条"
            for i, count in enumerate(histogram)
        ])

        system_prompt = """你是一个数据分析助手。请分析以下 vault 统计数据,提供洞察和建议。

输出要点:
1. 总体概览
2. 维度分布分析
3. 置信度分布分析
4. 改进建议
"""

        user_prompt = f"""vault 统计数据:

总文件数: {total_files}

维度分布:
{dimension_list}

置信度分布 (0.0-1.0, 分 10 桶):
{histogram_str}

请进行分析并提供建议。"""

        try:
            return self.provider.generate_text(user_prompt, system=system_prompt)
        except Exception:  # noqa: BLE001
            return None


__all__ = ["VaultStatsAgent"]

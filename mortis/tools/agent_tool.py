"""Mortis tools agent — ToolAgent 的 ToolProtocol 包装器 (issue #64)。

将 5 个内置 ToolAgent 包装成 ToolProtocol，注册到 ToolRegistry，
由 LLM 通过 tool calling 自发调用，替代原来的关键词路由。
"""

from __future__ import annotations

from typing import Any

from .base import ToolProtocol, ToolResult
from mortis.provider.base import LLMProviderProtocol
from mortis.vault import Vault
from mortis.toolagent import (
    VaultReadAgent,
    VaultSearchAgent,
    VaultStatsAgent,
    MarkdownRenderAgent,
    ClockAgent,
)


class VaultReadToolAgent(ToolProtocol):
    """vault:read_agent — 通过 VaultReadAgent 读取文件 + 可选摘要。"""

    def __init__(self, vault: Vault, provider: LLMProviderProtocol | None = None) -> None:
        self.vault = vault
        self.provider = provider
        self._agent = VaultReadAgent(vault=vault, provider=provider)

    @property
    def name(self) -> str:
        return "vault:read_agent"

    @property
    def description(self) -> str:
        return (
            "读取 vault 内的文件内容，可选生成摘要。"
            "参数: rel_path（相对路径）, resolve_links（是否解析双链，默认false）,"
            "summarize（是否生成摘要，默认false）, summary_length（摘要长度，默认100）。"
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "rel_path": {
                    "type": "string",
                    "description": "相对 vault 根的路径，如 mortis-growth/identity/self.md",
                },
                "resolve_links": {
                    "type": "boolean",
                    "description": "是否解析 Obsidian 双链",
                },
                "summarize": {
                    "type": "boolean",
                    "description": "是否生成 LLM 摘要",
                },
                "summary_length": {
                    "type": "integer",
                    "description": "摘要长度（字符数）",
                },
            },
            "required": ["rel_path"],
        }

    def execute(
        self,
        rel_path: str,
        resolve_links: bool = False,
        summarize: bool = False,
        summary_length: int = 100,
    ) -> ToolResult:
        result = self._agent.execute({
            "rel_path": rel_path,
            "resolve_links": resolve_links,
            "summarize": summarize,
            "summary_length": summary_length,
        })
        if result.success:
            content = result.data.get("content", "")
            if result.data.get("summary"):
                content += f"\n\n---\n摘要: {result.data['summary']}"
            return ToolResult.ok(self.name, content)
        return ToolResult.err(self.name, result.error or "unknown error")


class VaultSearchToolAgent(ToolProtocol):
    """vault:search_agent — 通过 VaultSearchAgent 搜索 vault。"""

    def __init__(self, vault: Vault, provider: LLMProviderProtocol | None = None) -> None:
        self.vault = vault
        self.provider = provider
        self._agent = VaultSearchAgent(vault=vault, provider=provider)

    @property
    def name(self) -> str:
        return "vault:search_agent"

    @property
    def description(self) -> str:
        return (
            "搜索 vault 内的 growth 文件，支持关键词搜索、标签过滤、双链图遍历和语义搜索。"
            "参数: query（搜索关键词）, tags（标签列表）, traverse_links（是否遍历双链）,"
            "max_depth（BFS深度，默认2）, semantic（是否语义搜索，默认false）, top_k（返回数量，默认10）。"
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词（可选）",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "标签过滤列表（可选）",
                },
                "traverse_links": {
                    "type": "boolean",
                    "description": "是否遍历双链图",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "BFS 遍历深度",
                },
                "semantic": {
                    "type": "boolean",
                    "description": "是否启用语义搜索排序",
                },
                "top_k": {
                    "type": "integer",
                    "description": "返回结果数量限制",
                },
            },
        }

    def execute(
        self,
        query: str | None = None,
        tags: list[str] | None = None,
        traverse_links: bool = False,
        max_depth: int = 2,
        semantic: bool = False,
        top_k: int = 10,
    ) -> ToolResult:
        result = self._agent.execute({
            "query": query,
            "tags": tags,
            "traverse_links": traverse_links,
            "max_depth": max_depth,
            "semantic": semantic,
            "top_k": top_k,
        })
        if result.success:
            matches = result.data.get("matches", [])
            lines = []
            for m in matches:
                score = m.get("score", 0.0)
                lines.append(f"- [{m.get('title', m.get('rel_path', ''))}] (score: {score:.2f})")
                if m.get("snippet"):
                    lines.append(f"  {m['snippet']}")
            content = "\n".join(lines) if lines else "(no matches)"
            if result.data.get("semantic_summary"):
                content += f"\n\n---\n语义摘要: {result.data['semantic_summary']}"
            return ToolResult.ok(self.name, content)
        return ToolResult.err(self.name, result.error or "unknown error")


class VaultStatsToolAgent(ToolProtocol):
    """vault:stats_agent — 通过 VaultStatsAgent 统计 vault。"""

    def __init__(self, vault: Vault, provider: LLMProviderProtocol | None = None) -> None:
        self.vault = vault
        self.provider = provider
        self._agent = VaultStatsAgent(vault=vault, provider=provider)

    @property
    def name(self) -> str:
        return "vault:stats_agent"

    @property
    def description(self) -> str:
        return (
            "统计 vault 内 growth 文件的数量、维度分布和置信度分布。"
            "参数: dimension（维度过滤，可选）, analyze（是否启用 LLM 分析，默认false）。"
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "dimension": {
                    "type": "string",
                    "description": "维度过滤（可选）",
                },
                "analyze": {
                    "type": "boolean",
                    "description": "是否启用 LLM 分析",
                },
            },
        }

    def execute(
        self,
        dimension: str | None = None,
        analyze: bool = False,
    ) -> ToolResult:
        result = self._agent.execute({
            "dimension": dimension,
            "analyze": analyze,
        })
        if result.success:
            data = result.data
            lines = [
                f"总文件数: {data.get('total_files', 0)}",
                "",
                "维度分布:",
            ]
            for dim, count in sorted(data.get("by_dimension", {}).items()):
                lines.append(f"- {dim}: {count}")
            lines.append("")
            lines.append("置信度分布 (0.0-1.0):")
            histogram = data.get("confidence_histogram", [])
            for i, count in enumerate(histogram):
                lines.append(f"- {i * 0.1:.1f}-{(i + 1) * 0.1:.1f}: {count}")
            content = "\n".join(lines)
            if data.get("analysis"):
                content += f"\n\n---\n分析报告:\n{data['analysis']}"
            return ToolResult.ok(self.name, content)
        return ToolResult.err(self.name, result.error or "unknown error")


class MarkdownRenderToolAgent(ToolProtocol):
    """markdown:render — 通过 MarkdownRenderAgent 解析 markdown。"""

    def __init__(self) -> None:
        self._agent = MarkdownRenderAgent()

    @property
    def name(self) -> str:
        return "markdown:render"

    @property
    def description(self) -> str:
        return (
            "解析 Obsidian 风格的 markdown，提取双链、标签、嵌入等。"
            "参数: content（markdown 内容）。"
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "markdown 内容",
                },
            },
            "required": ["content"],
        }

    def execute(self, content: str) -> ToolResult:
        result = self._agent.execute({"content": content})
        if result.success:
            data = result.data
            lines = []
            if data.get("wikilinks"):
                lines.append("双链链接:")
                lines.extend(f"- {link}" for link in data["wikilinks"])
            if data.get("tags"):
                lines.append("")
                lines.append("标签:")
                lines.extend(f"- {tag}" for tag in data["tags"])
            if data.get("embeds"):
                lines.append("")
                lines.append("嵌入文件:")
                lines.extend(f"- {embed}" for embed in data["embeds"])
            content = "\n".join(lines) if lines else "(no structured content)"
            return ToolResult.ok(self.name, content)
        return ToolResult.err(self.name, result.error or "unknown error")


class ClockToolAgent(ToolProtocol):
    """clock — 通过 ClockAgent 获取时间信息。"""

    def __init__(self, vault: Vault) -> None:
        self.vault = vault
        self._agent = ClockAgent(vault=vault)

    @property
    def name(self) -> str:
        return "clock"

    @property
    def description(self) -> str:
        return (
            "获取当前时间、逻辑时钟相位和上次 dream 时间。"
            "参数: timezone（时区，可选）。"
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "description": "时区（如 Asia/Shanghai，可选）",
                },
            },
        }

    def execute(self, timezone: str | None = None) -> ToolResult:
        result = self._agent.execute({"timezone": timezone})
        if result.success:
            data = result.data
            lines = [
                f"当前时间: {data.get('current_time', 'N/A')}",
                f"逻辑时钟相位: {data.get('phase', 'N/A')}",
                f"上次 dream: {data.get('last_dream', 'N/A')}",
            ]
            if "hours_awake" in data:
                lines.append(f"清醒时长: {data['hours_awake']} 小时")
            if "sleep_debt" in data:
                lines.append(f"睡眠不足: {data['sleep_debt']} 小时")
            content = "\n".join(lines)
            return ToolResult.ok(self.name, content)
        return ToolResult.err(self.name, result.error or "unknown error")


__all__ = [
    "VaultReadToolAgent",
    "VaultSearchToolAgent",
    "VaultStatsToolAgent",
    "MarkdownRenderToolAgent",
    "ClockToolAgent",
]

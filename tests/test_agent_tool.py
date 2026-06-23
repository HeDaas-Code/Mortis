"""Test mortis.tools.agent_tool — ToolAgent 的 ToolProtocol 包装器 (#64)。

issue #64 验收: ToolAgent 已注册为 ToolProtocol，由 LLM 通过 tool calling 自发调用。
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from mortis.tools.agent_tool import (
    VaultReadToolAgent,
    VaultSearchToolAgent,
    VaultStatsToolAgent,
    MarkdownRenderToolAgent,
    ClockToolAgent,
)
from mortis.tools.base import ToolResult
from mortis.growth.model import Dimension, DreamLevel, Growth
from mortis.provider.mock import MockProvider
from mortis.vault import Vault


@pytest.fixture
def vault_dir() -> Path:
    with tempfile.TemporaryDirectory(prefix="mortis-agent-tool-") as td:
        d = Path(td)
        (d / "mortis-journal" / "sub-outputs").mkdir(parents=True)
        (d / "mortis-growth" / "identity").mkdir(parents=True)
        (d / "mortis-journal" / "notes").mkdir(parents=True)
        yield d


def _write_growth(vault: Vault, id: str, body: str, tags: tuple[str, ...] = ()) -> None:
    now = datetime.now(tz=timezone.utc).isoformat()
    g = Growth(
        id=id, dimension=Dimension.IDENTITY, confidence=0.5,
        created_at=now, last_validated=now,
        source_sessions=(), dream_level=DreamLevel.LIGHT,
        emotional_valence=0.0, emotional_arousal=0.0,
        tags=tags, body=body,
    )
    vault.write_growth(g)


# ============================================================
# VaultReadToolAgent
# ============================================================


class TestVaultReadToolAgent:
    """issue #64: VaultReadToolAgent 实现 ToolProtocol。"""

    def test_name(self, vault_dir: Path):
        tool = VaultReadToolAgent(vault=Vault(vault_dir))
        assert tool.name == "vault:read_agent"

    def test_description(self, vault_dir: Path):
        tool = VaultReadToolAgent(vault=Vault(vault_dir))
        assert "read" in tool.description.lower() or "vault" in tool.description.lower()

    def test_input_schema(self, vault_dir: Path):
        tool = VaultReadToolAgent(vault=Vault(vault_dir))
        schema = tool.input_schema
        assert schema["type"] == "object"
        assert "rel_path" in schema["properties"]

    def test_execute_success(self, vault_dir: Path):
        (vault_dir / "test.md").write_text("hello world", encoding="utf-8")
        tool = VaultReadToolAgent(vault=Vault(vault_dir))
        r = tool.execute(rel_path="test.md")
        assert r.success is True
        assert "hello world" in r.content

    def test_execute_with_summarize(self, vault_dir: Path):
        (vault_dir / "test.md").write_text("long content", encoding="utf-8")
        mock = MockProvider(responses=["summary"])
        tool = VaultReadToolAgent(vault=Vault(vault_dir), provider=mock)
        r = tool.execute(rel_path="test.md", summarize=True)
        assert r.success is True
        assert "summary" in r.content.lower()

    def test_execute_blocked_steiner(self, vault_dir: Path):
        steiner = vault_dir / "mortis-steiner"
        steiner.mkdir(parents=True, exist_ok=True)
        (steiner / "x.md").write_text("x", encoding="utf-8")
        tool = VaultReadToolAgent(vault=Vault(vault_dir))
        r = tool.execute(rel_path="mortis-steiner/x.md")
        assert r.success is False
        assert "denied" in r.error.lower()


# ============================================================
# VaultSearchToolAgent
# ============================================================


class TestVaultSearchToolAgent:
    """issue #64: VaultSearchToolAgent 实现 ToolProtocol。"""

    def test_name(self, vault_dir: Path):
        tool = VaultSearchToolAgent(vault=Vault(vault_dir))
        assert tool.name == "vault:search_agent"

    def test_description(self, vault_dir: Path):
        tool = VaultSearchToolAgent(vault=Vault(vault_dir))
        # description 包含中文 "搜索" 或英文 "search"
        assert "搜索" in tool.description or "search" in tool.description.lower()

    def test_input_schema(self, vault_dir: Path):
        tool = VaultSearchToolAgent(vault=Vault(vault_dir))
        schema = tool.input_schema
        assert schema["type"] == "object"
        assert "query" in schema["properties"]
        assert "tags" in schema["properties"]
        assert "semantic" in schema["properties"]

    def test_execute_success(self, vault_dir: Path):
        v = Vault(vault_dir)
        _write_growth(v, "g1", "alpha content")
        tool = VaultSearchToolAgent(vault=v)
        r = tool.execute(query="alpha")
        assert r.success is True
        assert "g1" in r.content

    def test_execute_no_matches(self, vault_dir: Path):
        v = Vault(vault_dir)
        tool = VaultSearchToolAgent(vault=v)
        r = tool.execute(query="nothing")
        assert r.success is True
        assert "no matches" in r.content.lower()

    def test_execute_with_semantic(self, vault_dir: Path):
        v = Vault(vault_dir)
        _write_growth(v, "g1", "alpha")
        mock = MockProvider(responses=[
            "SCORE: 1 0.9\nSUMMARY: relevant."
        ])
        tool = VaultSearchToolAgent(vault=v, provider=mock)
        r = tool.execute(query="alpha", semantic=True)
        assert r.success is True
        # 内容应该包含 "语义摘要" 或 "relevant"
        content_lower = r.content.lower()
        assert "语义摘要" in r.content or "relevant" in content_lower

    def test_execute_with_tags(self, vault_dir: Path):
        v = Vault(vault_dir)
        _write_growth(v, "g1", "x", tags=("urgent",))
        _write_growth(v, "g2", "y", tags=("low",))
        tool = VaultSearchToolAgent(vault=v)
        r = tool.execute(tags=["urgent"])
        assert r.success is True
        assert "g1" in r.content
        assert "g2" not in r.content

    def test_execute_with_top_k(self, vault_dir: Path):
        v = Vault(vault_dir)
        for i in range(10):
            _write_growth(v, f"g{i}", f"content {i}")
        tool = VaultSearchToolAgent(vault=v)
        r = tool.execute(query="content", top_k=3)
        assert r.success is True
        # 应该有 3 条结果
        assert r.content.count("[g") == 3


# ============================================================
# VaultStatsToolAgent
# ============================================================


class TestVaultStatsToolAgent:
    """issue #64: VaultStatsToolAgent 实现 ToolProtocol。"""

    def test_name(self, vault_dir: Path):
        tool = VaultStatsToolAgent(vault=Vault(vault_dir))
        assert tool.name == "vault:stats_agent"

    def test_description(self, vault_dir: Path):
        tool = VaultStatsToolAgent(vault=Vault(vault_dir))
        assert "stats" in tool.description.lower() or "统计" in tool.description

    def test_input_schema(self, vault_dir: Path):
        tool = VaultStatsToolAgent(vault=Vault(vault_dir))
        schema = tool.input_schema
        assert "dimension" in schema["properties"]
        assert "analyze" in schema["properties"]

    def test_execute_success(self, vault_dir: Path):
        v = Vault(vault_dir)
        _write_growth(v, "g1", "test")
        tool = VaultStatsToolAgent(vault=v)
        r = tool.execute()
        assert r.success is True
        assert "总文件数" in r.content

    def test_execute_with_analyze(self, vault_dir: Path):
        v = Vault(vault_dir)
        _write_growth(v, "g1", "test")
        mock = MockProvider(responses=["Analysis report."])
        tool = VaultStatsToolAgent(vault=v, provider=mock)
        r = tool.execute(analyze=True)
        assert r.success is True
        assert "分析" in r.content or "analysis" in r.content.lower()

    def test_execute_with_dimension_filter(self, vault_dir: Path):
        v = Vault(vault_dir)
        _write_growth(v, "g1", "test")
        tool = VaultStatsToolAgent(vault=v)
        r = tool.execute(dimension="identity")
        assert r.success is True


# ============================================================
# MarkdownRenderToolAgent
# ============================================================


class TestMarkdownRenderToolAgent:
    """issue #64: MarkdownRenderToolAgent 实现 ToolProtocol。"""

    def test_name(self):
        tool = MarkdownRenderToolAgent()
        assert tool.name == "markdown:render"

    def test_description(self):
        tool = MarkdownRenderToolAgent()
        assert "render" in tool.description.lower() or "markdown" in tool.description.lower()

    def test_input_schema(self):
        tool = MarkdownRenderToolAgent()
        schema = tool.input_schema
        assert "content" in schema["properties"]
        assert "content" in schema["required"]

    def test_execute_success(self):
        tool = MarkdownRenderToolAgent()
        r = tool.execute(content="链接 [[test]] 文本 #tag")
        assert r.success is True
        assert "test" in r.content

    def test_execute_empty_content(self):
        tool = MarkdownRenderToolAgent()
        r = tool.execute(content="")
        assert r.success is True


# ============================================================
# ClockToolAgent
# ============================================================


class TestClockToolAgent:
    """issue #64: ClockToolAgent 实现 ToolProtocol。"""

    def test_name(self, vault_dir: Path):
        tool = ClockToolAgent(vault=Vault(vault_dir))
        assert tool.name == "clock"

    def test_description(self, vault_dir: Path):
        tool = ClockToolAgent(vault=Vault(vault_dir))
        assert "clock" in tool.description.lower() or "时间" in tool.description

    def test_input_schema(self, vault_dir: Path):
        tool = ClockToolAgent(vault=Vault(vault_dir))
        schema = tool.input_schema
        assert "timezone" in schema["properties"]

    def test_execute_success(self, vault_dir: Path):
        tool = ClockToolAgent(vault=Vault(vault_dir))
        r = tool.execute()
        assert r.success is True
        assert "当前时间" in r.content or "current" in r.content.lower()

    def test_execute_with_timezone(self, vault_dir: Path):
        tool = ClockToolAgent(vault=Vault(vault_dir))
        r = tool.execute(timezone="Asia/Shanghai")
        assert r.success is True

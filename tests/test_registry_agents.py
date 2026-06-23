"""Test mortis.tools.registry — ToolAgent 注册 + provider 注入 (#64)。

issue #64 验收: ToolRegistry 注册 ToolAgent。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from mortis.tools.registry import ToolRegistry, make_default_registry
from mortis.tools.agent_tool import (
    VaultReadToolAgent,
    VaultSearchToolAgent,
    VaultStatsToolAgent,
    MarkdownRenderToolAgent,
    ClockToolAgent,
)
from mortis.provider.mock import MockProvider
from mortis.vault import Vault


@pytest.fixture
def vault_dir() -> Path:
    with tempfile.TemporaryDirectory(prefix="mortis-registry-") as td:
        d = Path(td)
        (d / "mortis-journal" / "sub-outputs").mkdir(parents=True)
        yield d


@pytest.fixture
def vault(vault_dir: Path) -> Vault:
    return Vault(vault_dir)


class TestMakeDefaultRegistry:
    """issue #64: make_default_registry 注册 ToolAgent。"""

    def test_registry_with_agents(self, vault: Vault):
        """vault 有值时应注册 ToolAgent。"""
        registry = make_default_registry(vault=vault)
        names = registry.names()
        # 基础工具
        assert "vault:read" in names
        assert "vault:list" in names
        assert "vault:write" in names
        assert "vault:exists" in names
        # ToolAgent 包装器
        assert "vault:read_agent" in names
        assert "vault:search_agent" in names
        assert "vault:stats_agent" in names
        assert "markdown:render" in names
        assert "clock" in names

    def test_registry_without_vault_no_agents(self):
        """vault 为 None 时不注册 ToolAgent。"""
        registry = make_default_registry(vault=None, include_agents=False)
        names = registry.names()
        assert len(names) == 0

    def test_registry_with_provider(self, vault: Vault):
        """可以传入 provider。"""
        mock = MockProvider()
        registry = make_default_registry(vault=vault, provider=mock)
        # ToolAgent 应该已经注册
        assert "vault:read_agent" in registry.names()
        assert "vault:search_agent" in registry.names()

    def test_registry_exclude_agents(self, vault: Vault):
        """include_agents=False 时不注册 ToolAgent。"""
        registry = make_default_registry(vault=vault, include_agents=False)
        names = registry.names()
        # 只有基础工具
        assert "vault:read" in names
        assert "vault:list" in names
        assert "vault:write" in names
        assert "vault:exists" in names
        # Agent 包装器不应该在列表中
        assert "vault:read_agent" not in names
        assert "vault:search_agent" not in names


class TestToolRegistryWithAgents:
    """ToolRegistry 与 ToolAgent 集成测试。"""

    def test_execute_vault_read_agent(self, vault_dir: Path):
        """可以执行 vault:read_agent。"""
        (vault_dir / "test.md").write_text("hello", encoding="utf-8")
        registry = make_default_registry(vault=Vault(vault_dir))
        r = registry.execute("vault:read_agent", {"rel_path": "test.md"})
        assert r.success is True
        assert "hello" in r.content

    def test_execute_vault_search_agent(self, vault_dir: Path):
        """可以执行 vault:search_agent。"""
        vault = Vault(vault_dir)
        # 创建 growth 文件
        growth_dir = vault_dir / "mortis-growth" / "identity"
        growth_dir.mkdir(parents=True)
        (growth_dir / "test.md").write_text("---\nid: test\n---\ntest content", encoding="utf-8")
        registry = make_default_registry(vault=vault)
        r = registry.execute("vault:search_agent", {"query": "test"})
        assert r.success is True

    def test_execute_markdown_render(self, vault: Vault):
        """可以执行 markdown:render。"""
        registry = make_default_registry(vault=vault)
        r = registry.execute("markdown:render", {"content": "链接 [[test]]"})
        assert r.success is True
        assert "test" in r.content

    def test_execute_clock(self, vault: Vault):
        """可以执行 clock。"""
        registry = make_default_registry(vault=vault)
        r = registry.execute("clock", {})
        assert r.success is True
        assert "当前时间" in r.content or "current" in r.content.lower()

    def test_tool_schemas_includes_agents(self, vault: Vault):
        """tool_schemas 应包含 ToolAgent。"""
        registry = make_default_registry(vault=vault)
        schemas = registry.tool_schemas()
        names = [s["function"]["name"] for s in schemas]
        assert "vault:read" in names
        assert "vault:read_agent" in names
        assert "vault:search_agent" in names
        assert "vault:stats_agent" in names
        assert "markdown:render" in names
        assert "clock" in names


class TestRegistryAgentProvider:
    """验证 provider 注入到 ToolAgent。"""

    def test_agent_has_provider(self, vault: Vault):
        """ToolAgent 包装器应该有 provider。"""
        registry = make_default_registry(vault=vault, provider=MockProvider())
        # 获取 search agent
        search = registry.get("vault:search_agent")
        assert search is not None
        assert hasattr(search, "provider")

    def test_agent_provider_none_by_default(self, vault: Vault):
        """默认没有 provider。"""
        registry = make_default_registry(vault=vault)
        search = registry.get("vault:search_agent")
        assert search is not None
        assert search.provider is None

    def test_multiple_registrations_raise(self, vault: Vault):
        """重复注册应报错。"""
        registry = make_default_registry(vault=vault)
        with pytest.raises(ValueError, match="already registered"):
            registry.register(VaultReadToolAgent(vault))

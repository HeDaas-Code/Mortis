"""Test mortis.toolagent.vault_read — 摘要功能 (#63)。

issue #63 验收: VaultReadAgent 支持 LLM 摘要。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from mortis.toolagent.vault_read import VaultReadAgent
from mortis.vault import Vault
from mortis.provider.mock import MockProvider


@pytest.fixture
def vault_dir() -> Path:
    with tempfile.TemporaryDirectory(prefix="mortis-vread-summary-") as td:
        d = Path(td)
        (d / "mortis-journal" / "sub-outputs").mkdir(parents=True)
        (d / "mortis-journal" / "notes").mkdir(parents=True)
        yield d


@pytest.fixture
def seeded_vault(vault_dir: Path) -> Vault:
    """创建测试用的 vault。"""
    (vault_dir / "test.md").write_text(
        "这是一个测试文件。包含一些内容用于验证摘要功能。"
        "文件可以包含多行内容和不同的段落。",
        encoding="utf-8",
    )
    return Vault(vault_dir)


class TestVaultReadSummarize:
    """issue #63: 摘要功能。"""

    def test_summarize_false_no_llm_call(self, vault_dir: Path):
        """summarize=False 时不调用 LLM。"""
        (vault_dir / "test.md").write_text("test content", encoding="utf-8")
        v = Vault(vault_dir)
        mock = MockProvider()
        agent = VaultReadAgent(v, provider=mock)
        r = agent.execute({"rel_path": "test.md", "summarize": False})
        assert r.success is True
        assert r.data.get("summary") is None

    def test_summarize_true_without_provider(self, vault_dir: Path):
        """summarize=True 但无 provider 时降级处理。"""
        (vault_dir / "test.md").write_text("test content", encoding="utf-8")
        v = Vault(vault_dir)
        agent = VaultReadAgent(v, provider=None)
        r = agent.execute({"rel_path": "test.md", "summarize": True})
        assert r.success is True
        assert r.data.get("summary") is None

    def test_summarize_true_with_provider(self, vault_dir: Path):
        """summarize=True 且有 provider 时调用 LLM。"""
        (vault_dir / "test.md").write_text("test content", encoding="utf-8")
        v = Vault(vault_dir)
        mock = MockProvider(responses=["这是一个测试文件的摘要。"])
        agent = VaultReadAgent(v, provider=mock)
        r = agent.execute({"rel_path": "test.md", "summarize": True})
        assert r.success is True
        assert r.data.get("summary") is not None

    def test_summarize_respects_length(self, vault_dir: Path):
        """摘要应尊重 summary_length 参数。"""
        (vault_dir / "test.md").write_text("test content", encoding="utf-8")
        v = Vault(vault_dir)
        mock = MockProvider(responses=["这是一个比较长的摘要内容。" * 10])
        agent = VaultReadAgent(v, provider=mock)
        r = agent.execute({"rel_path": "test.md", "summarize": True, "summary_length": 20})
        assert r.success is True
        assert len(r.data.get("summary", "")) <= 20

    def test_summarize_with_resolve_links(self, vault_dir: Path):
        """summarize 可以与 resolve_links 组合使用。"""
        (vault_dir / "test.md").write_text(
            "链接 [[another]] 到其他文件。",
            encoding="utf-8",
        )
        v = Vault(vault_dir)
        mock = MockProvider(responses=["摘要内容。"])
        agent = VaultReadAgent(v, provider=mock)
        r = agent.execute({
            "rel_path": "test.md",
            "resolve_links": True,
            "summarize": True,
        })
        assert r.success is True
        assert r.data.get("links") == ["another"]
        assert r.data.get("summary") is not None

    def test_summarize_minimum_length(self, vault_dir: Path):
        """summary_length 最小值处理。"""
        (vault_dir / "test.md").write_text("test", encoding="utf-8")
        v = Vault(vault_dir)
        mock = MockProvider(responses=["摘要"])
        agent = VaultReadAgent(v, provider=mock)
        r = agent.execute({"rel_path": "test.md", "summarize": True, "summary_length": 5})
        assert r.success is True
        # summary_length < 20 时应该使用默认值 100

    def test_summarize_exception_returns_none(self, vault_dir: Path):
        """provider 抛异常时 summary 为 None。"""

        class BadProvider:
            def generate_text(self, prompt, system="", **kwargs):
                raise RuntimeError("summary failed")

        (vault_dir / "test.md").write_text("test", encoding="utf-8")
        v = Vault(vault_dir)
        agent = VaultReadAgent(v, provider=BadProvider())
        r = agent.execute({"rel_path": "test.md", "summarize": True})
        assert r.success is True
        assert r.data.get("summary") is None

    def test_summarize_empty_content(self, vault_dir: Path):
        """空内容不调用 LLM。"""
        (vault_dir / "empty.md").write_text("", encoding="utf-8")
        v = Vault(vault_dir)
        mock = MockProvider()
        agent = VaultReadAgent(v, provider=mock)
        r = agent.execute({"rel_path": "empty.md", "summarize": True})
        assert r.success is True
        assert r.data.get("summary") is None


class TestVaultReadProvider:
    """issue #63: VaultReadAgent 支持 provider 注入。"""

    def test_provider_field_exists(self, vault_dir: Path):
        """VaultReadAgent 应该有 provider 字段。"""
        v = Vault(vault_dir)
        agent = VaultReadAgent(v, provider=None)
        assert hasattr(agent, "provider")
        assert agent.provider is None

    def test_provider_can_be_set(self, vault_dir: Path):
        """provider 可以被传入。"""
        v = Vault(vault_dir)
        mock = MockProvider()
        agent = VaultReadAgent(v, provider=mock)
        assert agent.provider is mock

    def test_provider_with_blocked_prefix(self, vault_dir: Path):
        """provider 不影响 blocked_prefix 安全检查。"""
        v = Vault(vault_dir)
        steiner_dir = vault_dir / "mortis-steiner"
        steiner_dir.mkdir(parents=True, exist_ok=True)
        (steiner_dir / "test.md").write_text("test", encoding="utf-8")
        mock = MockProvider()
        agent = VaultReadAgent(v, provider=mock)
        r = agent.execute({"rel_path": "mortis-steiner/test.md"})
        assert r.success is False
        assert "access denied" in (r.error or "").lower()

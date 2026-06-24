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


class TestVaultReadSummarizeRedact:
    """审计 CRITICAL-1 回归: _summarize 发 LLM 前必须 redact 私密字段。

    VaultReadAgent._summarize 把文件 content 发给外部 LLM 做摘要。
    若 content 含 owner 私密字段 (dream callouts / emotion 标签 /
    subconscious / emotional_*), 必须先 redact 再发, 否则违反
    HARNESS.md '数据不外流' 原则。

    本测试用捕获型 provider 记录实际发给 LLM 的 prompt, 反断言私密值不在其中。
    """

    def _build_capture_provider(self):
        """构造 provider, 捕获 generate_text 收到的 prompt。"""
        captured = {"prompts": []}

        class _CaptureProvider:
            def generate_text(self, prompt, system="", **kw):
                captured["prompts"].append(prompt)
                return "mock summary"

            def generate(self, messages, **kw):
                from mortis.provider.base import Message
                return Message(role="assistant", content="mock")

        return _CaptureProvider(), captured

    def test_summarize_redacts_dream_callout(self, vault_dir: Path):
        """dream callout 内容不泄漏给 LLM。"""
        (vault_dir / "test.md").write_text(
            "> [!dream] 我最深层的秘密飞行梦境", encoding="utf-8"
        )
        v = Vault(vault_dir)
        provider, cap = self._build_capture_provider()
        agent = VaultReadAgent(v, provider=provider)
        agent.execute({"rel_path": "test.md", "summarize": True})
        prompt = cap["prompts"][0]
        assert "最深层的秘密" not in prompt
        assert "REDACTED" in prompt

    def test_summarize_redacts_emotion_tag(self, vault_dir: Path):
        """emotion 标签值不泄漏给 LLM。"""
        (vault_dir / "test.md").write_text(
            "今天很开心 [emotion:joy@0.9] 真好", encoding="utf-8"
        )
        v = Vault(vault_dir)
        provider, cap = self._build_capture_provider()
        agent = VaultReadAgent(v, provider=provider)
        agent.execute({"rel_path": "test.md", "summarize": True})
        prompt = cap["prompts"][0]
        assert "joy" not in prompt
        assert "REDACTED" in prompt

    def test_summarize_redacts_subconscious(self, vault_dir: Path):
        """subconscious 注释不泄漏给 LLM。"""
        (vault_dir / "test.md").write_text(
            "公开内容 %%subconscious%% 隐藏的潜意识想法 %%/subconscious%% 结束",
            encoding="utf-8",
        )
        v = Vault(vault_dir)
        provider, cap = self._build_capture_provider()
        agent = VaultReadAgent(v, provider=provider)
        agent.execute({"rel_path": "test.md", "summarize": True})
        prompt = cap["prompts"][0]
        assert "隐藏的潜意识想法" not in prompt
        assert "REDACTED" in prompt

    def test_summarize_redacts_emotional_valence(self, vault_dir: Path):
        """frontmatter emotional_valence 值不泄漏给 LLM。"""
        (vault_dir / "test.md").write_text(
            "---\nemotional_valence: 0.85\n---\n正文", encoding="utf-8"
        )
        v = Vault(vault_dir)
        provider, cap = self._build_capture_provider()
        agent = VaultReadAgent(v, provider=provider)
        agent.execute({"rel_path": "test.md", "summarize": True})
        prompt = cap["prompts"][0]
        assert "0.85" not in prompt
        assert "REDACTED" in prompt

    def test_summarize_redacts_all_combined(self, vault_dir: Path):
        """综合: 4 类私密字段同时出现, 全部 redact。"""
        (vault_dir / "test.md").write_text(
            "---\nemotional_valence: 0.9\n---\n"
            "> [!dream] 秘密梦境\n"
            "[emotion:joy] 开心\n"
            "%%subconscious%% 潜意识 %%/subconscious%%\n"
            "公开正文",
            encoding="utf-8",
        )
        v = Vault(vault_dir)
        provider, cap = self._build_capture_provider()
        agent = VaultReadAgent(v, provider=provider)
        agent.execute({"rel_path": "test.md", "summarize": True})
        prompt = cap["prompts"][0]
        assert "秘密梦境" not in prompt
        assert "joy" not in prompt
        assert "潜意识" not in prompt
        assert "0.9" not in prompt
        assert "公开正文" in prompt  # 非私密保留

    def test_summarize_redacts_uppercase_variants(self, vault_dir: Path):
        """大小写变体也 redact (CRITICAL-1 + CRITICAL-2 联合)。"""
        (vault_dir / "test.md").write_text(
            "> [!DREAM] UPPER SECRET\n[Emotion:joy] mixed case",
            encoding="utf-8",
        )
        v = Vault(vault_dir)
        provider, cap = self._build_capture_provider()
        agent = VaultReadAgent(v, provider=provider)
        agent.execute({"rel_path": "test.md", "summarize": True})
        prompt = cap["prompts"][0]
        assert "UPPER SECRET" not in prompt
        assert "joy" not in prompt
        assert "REDACTED" in prompt

"""Test mortis.toolagent.vault_search — VaultSearchAgent。

issue #25 验收: 全文 + 标签 + 双链图遍历。
"""

from __future__ import annotations

import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest

from mortis.growth.model import Dimension, DreamLevel, Growth
from mortis.provider.base import Message
from mortis.toolagent.vault_search import (
    VaultSearchAgent,
    _redact_snippet,
)
from mortis.vault import Vault
from mortis.vault.local import VaultAccessDenied


@pytest.fixture
def vault_dir() -> Path:
    with tempfile.TemporaryDirectory(prefix="mortis-vsearch-") as td:
        d = Path(td)
        (d / "mortis-journal" / "sub-outputs").mkdir(parents=True)
        (d / "mortis-journal" / "notes").mkdir(parents=True)
        yield d


def _write_growth(vault: Vault, id: str, body: str, tags: tuple[str, ...] = (), dimension: Dimension = Dimension.IDENTITY) -> None:
    now = datetime.now(tz=timezone.utc).isoformat()
    g = Growth(
        id=id, dimension=dimension, confidence=0.5,
        created_at=now, last_validated=now,
        source_sessions=(), dream_level=DreamLevel.LIGHT,
        emotional_valence=0.0, emotional_arousal=0.0,
        tags=tags, body=body,
    )
    vault.write_growth(g)


class TestVaultSearchAgent:
    def test_search_all_no_query(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        _write_growth(v, "g1", "alpha")
        _write_growth(v, "g2", "beta")
        agent = VaultSearchAgent(v)
        r = agent.execute({})
        assert r.success is True
        assert len(r.data["matches"]) == 2

    def test_search_by_query(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        _write_growth(v, "g1", "alpha bravo")
        _write_growth(v, "g2", "charlie")
        agent = VaultSearchAgent(v)
        r = agent.execute({"query": "alpha"})
        assert len(r.data["matches"]) == 1
        assert r.data["matches"][0]["rel_path"].endswith("g1.md")

    def test_search_by_tag(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        _write_growth(v, "g1", "x", tags=("urgent",))
        _write_growth(v, "g2", "y", tags=("low",))
        agent = VaultSearchAgent(v)
        r = agent.execute({"tags": ["urgent"]})
        assert len(r.data["matches"]) == 1

    def test_search_case_insensitive(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        _write_growth(v, "g1", "Hello World")
        agent = VaultSearchAgent(v)
        r = agent.execute({"query": "hello"})
        assert len(r.data["matches"]) == 1

    def test_traverse_links_disabled_by_default(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        _write_growth(v, "g1", "see [[g2]]")
        _write_growth(v, "g2", "linked from g1")
        agent = VaultSearchAgent(v)
        r = agent.execute({})
        assert r.data["graph"] is None

    def test_traverse_links_depth_1(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        _write_growth(v, "g1", "alpha links to [[g2]]")
        _write_growth(v, "g2", "linked from g1")
        agent = VaultSearchAgent(v)
        r = agent.execute({"query": "alpha", "traverse_links": True, "max_depth": 1})
        assert r.data["graph"] is not None
        # g1 → g2 link captured (g1 body contains [[g2]])
        # target may be raw "g2" or resolved rel_path
        assert any("g2" in k for k in r.data["graph"].keys())
        # source rel_path points to g1
        sources = next(iter(r.data["graph"].values()))
        assert any("g1" in s for s in sources)

    def test_traverse_links_depth_2(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        _write_growth(v, "g1", "alpha links to [[g2]]")
        _write_growth(v, "g2", "links to [[g3]]")
        _write_growth(v, "g3", "deep")
        agent = VaultSearchAgent(v)
        r = agent.execute({"query": "alpha", "traverse_links": True, "max_depth": 2})
        # depth 2 should cover g2 (depth 1 from g1) + g3 (depth 2 from g2)
        assert r.data["graph"] is not None
        assert any("g2" in k for k in r.data["graph"].keys())
        assert any("g3" in k for k in r.data["graph"].keys())

    def test_no_matches_empty(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        agent = VaultSearchAgent(v)
        r = agent.execute({"query": "nothing"})
        assert r.success is True
        assert r.data["matches"] == []


# ============================================================
# issue #73 MEDIUM-I — semantic rerank redact 私密字段
# ============================================================


class TestRedactSnippet:
    """_redact_snippet 必须过滤 owner 私密字段, 防止发给外部 LLM。

    反断言: 私密字段 (emotional_valence / dream / subconscious / emotion 标签)
    任何一条漏过滤都会让 owner 私密数据外流, 立即失败。
    """

    def test_redact_emotional_valence_frontmatter(self):
        """frontmatter emotional_valence 字段被 REDACTED。"""
        text = "---\ntitle: x\nemotional_valence: 0.85\n---\nbody"
        out = _redact_snippet(text)
        assert "0.85" not in out, "emotional_valence 值必须 redact"
        assert "REDACTED" in out

    def test_redact_emotional_arousal_frontmatter(self):
        """frontmatter emotional_arousal 字段被 REDACTED。"""
        text = "---\nemotional_arousal: 0.42\n---\nbody"
        out = _redact_snippet(text)
        assert "0.42" not in out
        assert "REDACTED" in out

    def test_redact_dream_level_frontmatter(self):
        """frontmatter dream_level 字段被 REDACTED。"""
        text = "---\ndream_level: deep\n---\nbody"
        out = _redact_snippet(text)
        assert "deep" not in out or "REDACTED" in out
        # 至少不能直接出现 "dream_level: deep"

    def test_redact_inline_emotion_tag(self):
        """行内 [emotion:joy] 标签被 REDACTED。"""
        text = "I feel great today [emotion:joy@0.8] really good"
        out = _redact_snippet(text)
        assert "[emotion:joy" not in out
        assert "joy" not in out  # 强烈隐私
        assert "REDACTED" in out

    def test_redact_subconscious_inline_comment(self):
        """%%subconscious%% ... %% 注释被 REDACTED。"""
        text = "public text %%subconscious%% owner private dream %%/subconscious%% public again"
        out = _redact_snippet(text)
        assert "owner private dream" not in out
        assert "REDACTED" in out
        assert "public text" in out  # 非私密保留
        assert "public again" in out

    def test_redact_sub_alias(self):
        """%%sub%% ... %% 短别名也被 redact。"""
        text = "before %%sub%% private %%/sub%% after"
        out = _redact_snippet(text)
        assert "private" not in out
        assert "REDACTED" in out

    def test_redact_dream_callout_block(self):
        """> [!dream] callout 整段被 REDACTED。"""
        text = """Public summary.

> [!dream] Owner had a vivid dream about flying over mountains.
> The landscape was detailed and emotional.
> Felt peaceful.

Next public paragraph."""
        out = _redact_snippet(text)
        assert "flying over mountains" not in out
        assert "vivid dream" not in out
        assert "REDACTED" in out
        assert "Public summary" in out
        assert "Next public paragraph" in out

    def test_redact_warning_callout_block(self):
        """> [!warning] callout 被 REDACTED。"""
        text = """Normal text.

> [!warning] Sensitive owner information here.

More normal text."""
        out = _redact_snippet(text)
        assert "Sensitive owner information" not in out
        assert "REDACTED" in out
        assert "Normal text" in out

    def test_redact_secret_callout_block(self):
        """> [!secret] callout 被 REDACTED。"""
        text = """OK.

> [!secret] API key: sk-test-1234567890

End."""
        out = _redact_snippet(text)
        assert "sk-test-1234567890" not in out
        assert "REDACTED" in out

    def test_redact_private_callout_block(self):
        """> [!private] callout 被 REDACTED。"""
        text = """Before.

> [!private] owner-private diary entry

After."""
        out = _redact_snippet(text)
        assert "owner-private diary" not in out

    def test_redact_confidential_callout_block(self):
        """> [!confidential] callout 被 REDACTED。"""
        text = """Before.

> [!confidential] secret strategy notes

After."""
        out = _redact_snippet(text)
        assert "secret strategy" not in out

    def test_redact_preserves_normal_content(self):
        """非私密内容完全保留 — 不误伤。"""
        text = """This is a normal growth record about public identity facts.
[[wikilink]] reference and #public-tag should pass through.
Some normal emotional language: \"I felt happy about this milestone\".
emotional (lowercase, not a tag) is fine."""
        out = _redact_snippet(text)
        assert "normal growth record" in out
        assert "[[wikilink]]" in out
        assert "#public-tag" in out
        assert "I felt happy" in out
        assert "REDACTED" not in out  # 无私密字段, 不应有 REDACTED

    def test_redact_empty_or_none(self):
        """空串 / None 必须安全处理 (不抛错)。"""
        assert _redact_snippet("") == ""
        # None 防御 (虽然类型标注是 str, 但调用方可能传 None)
        assert _redact_snippet(None) is None  # type: ignore[arg-type]

    def test_redact_combined_all_patterns(self):
        """综合场景: 5 类私密字段同时出现, 全部 redact。"""
        text = """---
emotional_valence: 0.9
emotional_arousal: 0.7
dream_level: deep
---

Public intro.

[emotion:joy@0.9] inline emotion.

%%subconscious%% private thought %%/subconscious%%

> [!dream] vivid dream content here
> more dream text

> [!secret] API key sk-abc-123

Normal ending text."""
        out = _redact_snippet(text)
        # 私密字段值全部消失
        assert "0.9" not in out
        assert "0.7" not in out
        assert "deep" not in out
        assert "joy" not in out
        assert "private thought" not in out
        assert "vivid dream content" not in out
        assert "sk-abc-123" not in out
        # 占位符存在
        assert out.count("REDACTED") >= 3
        # 非私密保留
        assert "Public intro" in out
        assert "Normal ending text" in out


class TestVaultSearchAgentRedactSensitive:
    """VaultSearchAgent.redact_sensitive 参数控制 LLM prompt 数据流。"""

    def _build_provider_with_capture(self):
        """构造 provider, 捕获所有 generate_text 调用的 prompt。"""
        captured = {"prompts": []}

        class _P:
            def generate_text(self, prompt, system="", **_):
                captured["prompts"].append((prompt, system))
                return ""

            def generate(self, messages, **_):
                return Message(role="assistant", content="")

        return _P(), captured

    def _make_growth_with_sensitive_content(self, vault: Vault) -> Vault:
        """写一个含 owner 私密字段的 growth, 返回 vault (链式)。"""
        body = """---
emotional_valence: 0.85
emotional_arousal: 0.42
dream_level: deep
---

Public summary about Mortis identity.

[emotion:joy@0.9] feels great.

%%subconscious%% owner dream content %%/subconscious%%

> [!dream] vivid private dream about flying

Normal text."""
        now = datetime.now(tz=timezone.utc).isoformat()
        g = Growth(
            id="sensitive", dimension=Dimension.IDENTITY, confidence=0.5,
            created_at=now, last_validated=now, source_sessions=(),
            dream_level=DreamLevel.LIGHT,
            emotional_valence=0.0, emotional_arousal=0.0,
            tags=(), body=body,
        )
        vault.write_growth(g)
        return vault

    def test_default_redact_sensitive_true_strips_private_fields(self, vault_dir: Path):
        """默认 redact_sensitive=True — 私密字段不出现在 LLM prompt。"""
        v = Vault(vault_dir)
        self._make_growth_with_sensitive_content(v)
        provider, captured = self._build_provider_with_capture()

        agent = VaultSearchAgent(v, provider=provider)  # type: ignore[arg-type]  # _P 不严格匹配 Protocol 但运行正确
        r = agent.execute({"query": "Mortis", "semantic": True})

        assert r.success is True
        assert len(captured["prompts"]) == 1, "语义 rerank 必须调一次 LLM"
        prompt, system = captured["prompts"][0]
        # 关键反断言: 私密字段值不在 prompt 里
        assert "0.85" not in prompt, "emotional_valence 值泄漏到 LLM"
        assert "0.42" not in prompt, "emotional_arousal 值泄漏到 LLM"
        assert "vivid private dream" not in prompt, "dream callout 泄漏到 LLM"
        assert "owner dream content" not in prompt, "subconscious 泄漏到 LLM"
        assert "joy" not in prompt, "emotion tag 泄漏到 LLM"
        # 占位符存在
        assert "REDACTED" in prompt

    def test_redact_sensitive_false_warns_and_sends_raw(self, vault_dir: Path, caplog):
        """redact_sensitive=False — log warning + 私密字段原样发 LLM。"""
        v = Vault(vault_dir)
        self._make_growth_with_sensitive_content(v)
        provider, captured = self._build_provider_with_capture()

        with caplog.at_level(logging.WARNING, logger="mortis.toolagent.vault_search"):
            agent = VaultSearchAgent(v, provider=provider, redact_sensitive=False)  # type: ignore[arg-type]

        # log warning 必须产生
        warns = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("redact_sensitive=False" in r.getMessage() for r in warns)

        # 私密字段**会**发 LLM (这是 owner 主动关闭后的预期行为)
        r = agent.execute({"query": "Mortis", "semantic": True})
        prompt, _ = captured["prompts"][0]
        # 没有 redact — 私密字段在 prompt 里 (但这是 owner 决策)
        assert "0.85" in prompt or "REDACTED" not in prompt

    def test_redact_sensitive_default_is_true(self):
        """redact_sensitive 默认 True (HARNESS.md '数据不外流')。"""
        v = Mock(spec=Vault)
        agent = VaultSearchAgent(v)
        assert agent.redact_sensitive is True


# ============================================================
# issue #71 MEDIUM-D — 异常分类 (在 fix/73 联合修复中)
# ============================================================


class TestVaultSearchAgentExceptionClassification:
    """vault_search 必须分类处理 read_growth 异常, VaultAccessDenied 必须 log。"""

    def _build_vault_with_rels(self, rels: list[str]) -> Vault:
        """构造 vault, list_growths 返回指定 rels (Mock 绕过真实 IO)。"""
        v: Vault = Mock(spec=Vault)  # type: ignore[assignment]
        v.list_growths.return_value = rels  # type: ignore[attr-defined]
        return v

    def test_vault_access_denied_logs_warning(self, caplog):
        """VaultAccessDenied → log warning 含 'blocked by whitelist' + rel_path。

        关键反断言: log 必须包含, 否则攻击者可通过 matches 差异枚举被拒路径。
        """
        v = self._build_vault_with_rels(["mortis-journal/sub-outputs/leak.md"])
        v.read_growth.side_effect = VaultAccessDenied("blocked by whitelist")  # type: ignore[attr-defined]
        agent = VaultSearchAgent(v)

        with caplog.at_level(logging.WARNING, logger="mortis.toolagent.vault_search"):
            r = agent.execute({"query": "anything"})

        assert r.success is True
        assert r.data["matches"] == []
        warns = [rec for rec in caplog.records if rec.levelno == logging.WARNING]
        assert len(warns) >= 1, "VaultAccessDenied 必须 log warning, 不能静默"
        assert any("blocked by whitelist" in rec.getMessage() for rec in warns)
        assert any("mortis-journal/sub-outputs/leak.md" in rec.getMessage() for rec in warns)

    def test_file_not_found_silent_skip(self, caplog):
        """FileNotFoundError → 静默 skip, 不 log warning (文件被删是常态)。"""
        v = self._build_vault_with_rels(["deleted.md"])
        v.read_growth.side_effect = FileNotFoundError("no such file")  # type: ignore[attr-defined]
        agent = VaultSearchAgent(v)

        with caplog.at_level(logging.WARNING, logger="mortis.toolagent.vault_search"):
            r = agent.execute({"query": "anything"})

        assert r.success is True
        assert r.data["matches"] == []
        warns = [rec for rec in caplog.records if rec.levelno == logging.WARNING]
        assert len(warns) == 0

    def test_other_exception_logs_warning_with_type(self, caplog):
        """其他 Exception → log warning 含异常类型 (便于调试)。"""
        v = self._build_vault_with_rels(["corrupted.md"])
        v.read_growth.side_effect = RuntimeError("disk full")  # type: ignore[attr-defined]
        agent = VaultSearchAgent(v)

        with caplog.at_level(logging.WARNING, logger="mortis.toolagent.vault_search"):
            r = agent.execute({"query": "anything"})

        assert r.success is True
        assert r.data["matches"] == []
        warns = [rec for rec in caplog.records if rec.levelno == logging.WARNING]
        assert len(warns) >= 1
        assert any("RuntimeError" in rec.getMessage() for rec in warns)
        assert any("disk full" in rec.getMessage() for rec in warns)

    def test_bfs_links_vault_access_denied_logs_warning(self, caplog):
        """BFS 双链遍历同样分类处理 — VaultAccessDenied 必须 log。"""
        v = self._build_vault_with_rels(["seed.md"])
        v.read_growth.side_effect = VaultAccessDenied("blocked by whitelist")  # type: ignore[attr-defined]
        agent = VaultSearchAgent(v)

        with caplog.at_level(logging.WARNING, logger="mortis.toolagent.vault_search"):
            r = agent.execute({"query": "anything", "traverse_links": True})

        assert r.success is True
        warns = [rec for rec in caplog.records if rec.levelno == logging.WARNING]
        assert len(warns) >= 1
        assert any(
            "bfs_links" in rec.getMessage() or "search" in rec.getMessage()
            for rec in warns
        )

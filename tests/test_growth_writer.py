"""Test growth Obsidian-Native writer — RFC §12.3 完整格式 + 自动双链。

issue #19 acceptance:
- 写入 → 读回 → 解析 → Growth dataclass 一致(round-trip)
- Obsidian 解析准确率 100%
- 自动生成 ## 来源 / ## 关联 / > [!note] callout / %%潜意识%% 段
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mortis.growth import (
    Dimension,
    DreamLevel,
    Growth,
    growth_rel,
    write_growth_obsidian,
    parse_growth_file,
)
from mortis.growth.frontmatter import serialize_growth_file
from mortis.growth.writer import (
    extract_tags_inline_from_body,
    extract_wikilinks_from_body,
)
from mortis.vault.local import Vault


def _make_growth(**overrides) -> Growth:
    defaults = dict(
        id="growth-2026-06-22-001",
        dimension=Dimension.TONE,
        confidence=0.6,
        created_at="2026-06-22T10:00:00+00:00",
        last_validated="2026-06-22T10:00:00+00:00",
        source_sessions=("session-a", "session-b"),
        dream_level=DreamLevel.MEDIUM,
        emotional_valence=0.5,
        emotional_arousal=0.3,
        tags=("沟通策略", "已验证"),
        body="技术讨论中先给结论再解释，更有效。",
    )
    defaults.update(overrides)
    return Growth(**defaults)


class TestWriterBasics(unittest.TestCase):
    """write_growth_obsidian 基础结构。"""

    def test_emits_frontmatter(self) -> None:
        g = _make_growth()
        out = write_growth_obsidian(g)
        assert out.startswith("---\n")
        assert "id: growth-2026-06-22-001" in out
        assert "dimension: tone" in out
        assert "confidence: 0.6" in out
        assert out.count("---") >= 2  # 收尾的 ---

    def test_emits_h1_title(self) -> None:
        g = _make_growth(body="先给结论。")
        out = write_growth_obsidian(g)
        assert "# 先给结论。" in out

    def test_emits_source_section(self) -> None:
        g = _make_growth(source_sessions=("session-a", "session-b"))
        out = write_growth_obsidian(g)
        assert "## 来源" in out
        assert "[[session-a]]" in out
        assert "[[session-b]]" in out

    def test_omits_source_when_empty(self) -> None:
        g = _make_growth(source_sessions=())
        out = write_growth_obsidian(g)
        assert "## 来源" not in out

    def test_emits_related_section_with_wikilinks(self) -> None:
        g = _make_growth()
        related = _make_growth(id="growth-other-001", dimension=Dimension.VALUES)
        out = write_growth_obsidian(g, related_growths=[related])
        assert "## 关联" in out
        assert "[[growth-other-001]]" in out

    def test_omits_related_when_empty(self) -> None:
        g = _make_growth()
        out = write_growth_obsidian(g)
        assert "## 关联" not in out

    def test_emits_callout(self) -> None:
        g = _make_growth(callout="这条经验与效率优先相关")
        out = write_growth_obsidian(g)
        assert "> [!note]" in out
        assert "这条经验与效率优先相关" in out

    def test_omits_callout_when_none(self) -> None:
        g = _make_growth(callout=None)
        out = write_growth_obsidian(g)
        assert "> [!note]" not in out

    def test_emits_subconscious(self) -> None:
        g = _make_growth(subconscious="其实我不确定这个判断")
        out = write_growth_obsidian(g)
        assert "%%" in out
        assert "其实我不确定这个判断" in out

    def test_omits_subconscious_when_none(self) -> None:
        g = _make_growth(subconscious=None)
        out = write_growth_obsidian(g)
        # 不应有 %% 块(单行/折叠都没有)
        # 唯一可能是巧合 — 实际写两次以确保
        out2 = write_growth_obsidian(g)
        # 严格:不应出现 `%%` 边界
        assert out.count("%%") == 0


class TestRoundTrip:
    """write → read → parse → Growth 一致性。"""

    def test_minimal_growth_roundtrip(self) -> None:
        g = _make_growth()
        text = write_growth_obsidian(g)
        # 解析能成功 + 基础字段一致
        loaded = parse_growth_file(text)
        assert loaded.id == g.id
        assert loaded.dimension == g.dimension
        assert loaded.confidence == g.confidence
        assert loaded.body == g.body  # body 字段是用户原文
        assert loaded.tags == g.tags
        assert loaded.source_sessions == g.source_sessions

    def test_full_growth_roundtrip(self) -> None:
        """全字段 + 关联 growth 的 round-trip。"""
        g = _make_growth(
            callout="元认知提醒:这条经验很稳定",
            subconscious="第三次用对方觉得我太直接",
        )
        related = _make_growth(id="growth-x-002", dimension=Dimension.IDENTITY)
        text = write_growth_obsidian(g, related_growths=[related])
        loaded = parse_growth_file(text)
        # 基础字段
        assert loaded.id == g.id
        assert loaded.dimension == g.dimension
        assert loaded.body == g.body
        # Obsidian 字段(由 vault._enrich_growth_with_obsidian 在 read_growth 时回填 —
        # 这里只验证 frontmatter 段不被破坏)
        assert loaded.tags == g.tags


class TestVaultIntegration:
    """vault.write_growth → vault.read_growth 走完整 Obsidian 体系。"""

    def test_write_read_obsidian_fields_enriched(self) -> None:
        """写完再读,Obsidian 字段(wikilinks/tags_inline/callout/subconscious)被自动回填。"""
        with tempfile.TemporaryDirectory(prefix="mortis-growth-writer-") as tmp:
            vault = Vault(Path(tmp))
            g = _make_growth(
                callout="这条经验在效率优先中也有体现",
                subconscious="第三次用对方觉得我太直接了",
                body="正文包含 [[session-x]] 和 #inlinetag 标签。",
            )
            vault.write_growth(g)
            loaded = vault.read_growth(growth_rel(g.dimension, g.id))
            # frontmatter 字段
            assert loaded.id == g.id
            assert loaded.dimension == g.dimension
            # Obsidian 字段(从 vault 原文回填)
            assert "session-x" in loaded.wikilinks
            assert "#inlinetag" in loaded.tags_inline
            assert loaded.callout == "这条经验在效率优先中也有体现"
            assert loaded.subconscious == "第三次用对方觉得我太直接了"
            # body 字段是用户原文(被 Obsidian 剥离后保留)
            assert "[[session-x]]" in loaded.body
            assert "#inlinetag" in loaded.body

    def test_wikilinks_extracted_from_body(self) -> None:
        body = "this links to [[a]] and [[b]] and again [[a]]"
        result = extract_wikilinks_from_body(body)
        # 去重保序
        assert result == ("a", "b")

    def test_tags_extracted_from_body(self) -> None:
        body = "discussed #topic1 and #topic2 then #topic1 again"
        result = extract_tags_inline_from_body(body)
        assert result == ("#topic1", "#topic2")

    def test_serialize_growth_file_legacy_preserved(self) -> None:
        """旧版 serialize_growth_file 行为保持(纯 frontmatter + body) — 不动 #18 合约。"""
        g = _make_growth()
        out = serialize_growth_file(g)
        assert out.startswith("---\n")
        assert "id: growth-2026-06-22-001" in out
        # 不应有 Obsidian 结构
        assert "# " not in out
        assert "## 来源" not in out
        assert "> [!note]" not in out
        assert "%%" not in out

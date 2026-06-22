"""Test subconscious 注释剥离/保留 — issue #19 acceptance。

关键合约:
- `%%潜意识%%` 默认不读入 prompt(读 prompt 时走 subconscious 字段,不走 body)
- 解析时注释从 body 剥离,存到 ParsedObsidian.comments / .foldable_sections
- vault.read_growth 时 subconscious 字段被自动回填
- body 字段不再含 `%%...%%` 文本
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
)
from mortis.vault.local import Vault
from mortis.vault.obsidian import (
    parse as parse_obsidian,
    render_subconscious,
)


def _make_growth(**overrides) -> Growth:
    defaults = dict(
        id="g-subconscious-001",
        dimension=Dimension.TONE,
        confidence=0.6,
        created_at="2026-06-22T10:00:00+00:00",
        last_validated="2026-06-22T10:00:00+00:00",
        source_sessions=(),
        dream_level=None,
        emotional_valence=0.0,
        emotional_arousal=0.0,
        tags=(),
        body="public opinion",
    )
    defaults.update(overrides)
    return Growth(**defaults)


class TestSubconsciousStripFromBody:
    """解析时注释从 body 剥离。"""

    def test_inline_comment_removed_from_body(self) -> None:
        body = "公开观点 %%其实我不太确定%% 但还是说了"
        parsed = parse_obsidian(body)
        assert "其实我不太确定" not in parsed.body
        assert "公开观点" in parsed.body
        assert "但还是说了" in parsed.body
        assert parsed.comments == ("其实我不太确定",)

    def test_fold_block_removed_from_body(self) -> None:
        body = "before\n%%\n压抑的记忆\n详细描述\n%%\nafter"
        parsed = parse_obsidian(body)
        assert "压抑的记忆" not in parsed.body
        assert "详细描述" not in parsed.body
        assert "before" in parsed.body
        assert "after" in parsed.body
        assert len(parsed.foldable_sections) == 1
        assert "压抑的记忆" in parsed.foldable_sections[0].body

    def test_subconscious_aggregated(self) -> None:
        """多个注释 + 折叠块都进 subconscious 字段(用 \\n\\n 连接)。"""
        body = "%%first%%\n和公开内容\n%%\nfold1\nfold2\n%%\n更多公开"
        parsed = parse_obsidian(body)
        # comments + foldable_sections 都进 subconscious
        all_sub = "\n\n".join(parsed.comments + tuple(f.body for f in parsed.foldable_sections))
        assert "first" in all_sub
        assert "fold1" in all_sub


class TestSubconsciousNotReadIntoPrompt:
    """默认 subconscious 不读入 prompt — body 字段不含注释。"""

    def test_body_excludes_subconscious(self) -> None:
        with tempfile.TemporaryDirectory(prefix="mortis-subconscious-") as tmp:
            vault = Vault(Path(tmp))
            g = _make_growth(
                body="这条经验成立。%%其实我有保留意见%% 但还是写下来。",
                subconscious="其实我有保留意见",
            )
            vault.write_growth(g)
            loaded = vault.read_growth(growth_rel(g.dimension, g.id))
            # body 不应包含潜意识内容
            assert "其实我有保留意见" not in loaded.body
            # subconscious 字段包含
            assert loaded.subconscious == "其实我有保留意见"

    def test_subconscious_preserved_across_roundtrip(self) -> None:
        """write → read → 潜意识内容不丢。"""
        with tempfile.TemporaryDirectory(prefix="mortis-subconscious-rt-") as tmp:
            vault = Vault(Path(tmp))
            secret = "这条经验第三次用时对方觉得太直接"
            g = _make_growth(
                body="公开经验正文",
                subconscious=secret,
            )
            vault.write_growth(g)
            loaded = vault.read_growth(growth_rel(g.dimension, g.id))
            assert loaded.subconscious == secret


class TestSubconsciousRender:
    """render_subconscious 单行 / 多行。"""

    def test_render_single_line(self) -> None:
        assert render_subconscious("hidden") == "%%\nhidden\n%%"

    def test_render_multiline(self) -> None:
        result = render_subconscious("line1\nline2")
        assert result.startswith("%%\n")
        assert "line1" in result
        assert "line2" in result
        assert result.endswith("\n%%")


class TestSubconsciousAbsentIsNone:
    """无注释时 subconscious 字段为 None(不空字符串)。"""

    def test_no_subconscious_returns_none(self) -> None:
        body = "public only"
        parsed = parse_obsidian(body)
        assert parsed.comments == ()
        assert parsed.foldable_sections == ()

    def test_vault_growth_no_subconscious_field_none(self) -> None:
        with tempfile.TemporaryDirectory(prefix="mortis-subconscious-none-") as tmp:
            vault = Vault(Path(tmp))
            g = _make_growth(body="纯公开内容", subconscious=None)
            vault.write_growth(g)
            loaded = vault.read_growth(growth_rel(g.dimension, g.id))
            assert loaded.subconscious is None
            assert loaded.callout is None
            assert loaded.wikilinks == ()
            assert loaded.tags_inline == ()

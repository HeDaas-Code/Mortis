"""Test growth frontmatter — 自写 YAML 子集解析。

issue #18 决定：自写 frontmatter 解析，不引 PyYAML（零依赖）。
覆盖：简单 / 嵌套 / 列表 / 多行 / roundtrip / 错误处理。
"""
from __future__ import annotations

import pytest

from mortis.growth import (
    Dimension,
    DreamLevel,
    FrontmatterError,
    Growth,
    parse_frontmatter,
    parse_growth_file,
    serialize_frontmatter,
    serialize_growth_file,
)


class TestParseFrontmatter:
    """parse_frontmatter — 文本 → (dict, body)。"""

    def test_parse_simple_key_value(self) -> None:
        """单 key: value 解析为 dict。"""
        text = "---\nid: g-001\n---\nbody here"
        meta, body = parse_frontmatter(text)
        assert meta == {"id": "g-001"}
        assert body == "body here"

    def test_parse_multiple_keys(self) -> None:
        """多个 key 都在 dict 里。"""
        text = "---\nid: g-001\ndimension: tone\nconfidence: 0.6\n---\nbody"
        meta, body = parse_frontmatter(text)
        assert meta["id"] == "g-001"
        assert meta["dimension"] == "tone"
        assert meta["confidence"] == 0.6
        assert body == "body"

    def test_parse_inline_list(self) -> None:
        """key: [a, b, c] 解析为 list[str]。"""
        text = "---\ntags: [foo, bar, baz]\n---\n"
        meta, _ = parse_frontmatter(text)
        assert meta["tags"] == ["foo", "bar", "baz"]

    def test_parse_block_list(self) -> None:
        """key: + 缩进 dash 多行解析为 list[str]。"""
        text = "---\nsource_sessions:\n  - session-abc\n  - session-def\n---\n"
        meta, _ = parse_frontmatter(text)
        assert meta["source_sessions"] == ["session-abc", "session-def"]

    def test_parse_numbers_int_and_float(self) -> None:
        """数字自动转 int / float。"""
        text = "---\nint_val: 42\nfloat_val: 0.5\n---\n"
        meta, _ = parse_frontmatter(text)
        assert meta["int_val"] == 42
        assert isinstance(meta["int_val"], int)
        assert meta["float_val"] == 0.5
        assert isinstance(meta["float_val"], float)

    def test_parse_empty_value_is_none(self) -> None:
        """key: 后面空值（block list 起始判断先于 None 判断）。"""
        text = "---\ndream_level:\n---\n"
        meta, _ = parse_frontmatter(text)
        assert meta["dream_level"] is None

    def test_parse_missing_frontmatter_raises(self) -> None:
        """无 --- 起始 → FrontmatterError。"""
        text = "no frontmatter here\nbody"
        with pytest.raises(FrontmatterError, match="frontmatter"):
            parse_frontmatter(text)

    def test_parse_malformed_frontmatter_raises(self) -> None:
        """--- 起始但未正确闭合 → FrontmatterError。"""
        text = "---\nid: g-001\nbody without closing fence"
        with pytest.raises(FrontmatterError):
            parse_frontmatter(text)


class TestSerializeRoundtrip:
    """serialize / parse roundtrip。"""

    def test_serialize_simple(self) -> None:
        """serialize_frontmatter 输出标准格式。"""
        out = serialize_frontmatter({"id": "g-001", "confidence": 0.6}, "the body")
        assert out.startswith("---\n")
        assert "id: g-001" in out
        assert "confidence: 0.6" in out
        assert "the body" in out

    def test_growth_roundtrip(self) -> None:
        """Growth → serialize → parse → Growth 一致。"""
        g = Growth(
            id="growth-2026-06-21-001",
            dimension=Dimension.TONE,
            confidence=0.6,
            created_at="2026-06-21T23:30:00+00:00",
            last_validated="2026-07-01T23:30:00+00:00",
            source_sessions=("session-abc", "session-def"),
            dream_level=DreamLevel.MEDIUM,
            emotional_valence=0.7,
            emotional_arousal=0.5,
            tags=("沟通策略", "已验证"),
            body="技术讨论中先给结论。",
        )
        text = serialize_growth_file(g)
        g2 = parse_growth_file(text)
        assert g2 == g

    def test_growth_roundtrip_no_dream_level(self) -> None:
        """dream_level=None 的 Growth roundtrip 正确。"""
        g = Growth(
            id="g-002",
            dimension=Dimension.IDENTITY,
            confidence=0.3,
            created_at="2026-06-22T00:00:00+00:00",
            last_validated="2026-06-22T00:00:00+00:00",
            source_sessions=(),
            dream_level=None,
            emotional_valence=0.0,
            emotional_arousal=0.2,
            tags=(),
            body="REFLECT 写的反思。",
        )
        text = serialize_growth_file(g)
        g2 = parse_growth_file(text)
        assert g2 == g
        assert g2.dream_level is None

    def test_parse_growth_file_missing_field_raises(self) -> None:
        """缺关键字段 → FrontmatterError。"""
        text = "---\nid: g-001\n---\nbody"
        with pytest.raises(FrontmatterError, match="missing"):
            parse_growth_file(text)

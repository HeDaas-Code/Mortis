"""Test Obsidian 解析层 — 双链/标签/嵌入/callout/注释/折叠/代码块。

issue #19: 解析层是 round-trip 契约的一半 — 解析正确,反序列化才能用。
"""
from __future__ import annotations

from mortis.vault.obsidian import (
    Callout,
    Fold,
    ParsedObsidian,
    Wikilink,
    parse,
    render_callout,
    render_embed,
    render_subconscious,
    render_wikilink,
)


class TestWikilinkExtraction:
    """`[[双链]]` 与 `![[嵌入]]` 提取。"""

    def test_single_wikilink(self) -> None:
        p = parse("hello [[foo]] world")
        assert p.wikilinks == (Wikilink(target="foo", alias=None, is_embed=False),)
        assert p.embed_links == ()

    def test_multiple_wikilinks_ordered(self) -> None:
        p = parse("[[a]] and [[b]] and [[c]]")
        assert [w.target for w in p.wikilinks] == ["a", "b", "c"]

    def test_wikilink_with_alias(self) -> None:
        p = parse("see [[session-abc|the first meeting]]")
        assert p.wikilinks == (
            Wikilink(target="session-abc", alias="the first meeting", is_embed=False),
        )

    def test_embed_marked(self) -> None:
        p = parse("reference ![[growth-007]] inline")
        assert p.embed_links == (Wikilink(target="growth-007", alias=None, is_embed=True),)
        assert p.wikilinks == ()

    def test_embed_with_alias(self) -> None:
        p = parse("![[growth-007|old values]]")
        assert p.embed_links == (
            Wikilink(target="growth-007", alias="old values", is_embed=True),
        )

    def test_no_wikilinks_returns_empty_tuple(self) -> None:
        p = parse("plain text with no links")
        assert p.wikilinks == ()
        assert p.embed_links == ()

    def test_wikilink_render_roundtrip(self) -> None:
        """解析后的 Wikilink.render() 应还原原文(单条)。"""
        original = "[[foo|bar]]"
        p = parse(f"x {original} y")
        assert p.wikilinks[0].render() == original

    def test_render_wikilink_helper(self) -> None:
        assert render_wikilink("foo") == "[[foo]]"
        assert render_wikilink("foo", "bar") == "[[foo|bar]]"
        assert render_embed("foo") == "[[!foo]]" or render_embed("foo") == "![[foo]]"


class TestTagExtraction:
    """`#tag` 提取(frontmatter 外)。"""

    def test_single_tag(self) -> None:
        p = parse("discussion about #沟通策略 today")
        assert p.tags_inline == ("#沟通策略",)

    def test_multiple_tags(self) -> None:
        p = parse("#a #b and #c")
        assert p.tags_inline == ("#a", "#b", "#c")

    def test_tag_after_punctuation(self) -> None:
        p = parse("hello, #world")
        assert p.tags_inline == ("#world",)

    def test_tag_at_line_start(self) -> None:
        p = parse("#important first line")
        assert p.tags_inline == ("#important",)

    def test_tag_inside_code_block_excluded(self) -> None:
        p = parse("before\n```\n#notatag\n```\nafter #real")
        assert p.tags_inline == ("#real",)

    def test_no_tags(self) -> None:
        p = parse("nothing tagged here")
        assert p.tags_inline == ()


class TestCalloutExtraction:
    """`> [!kind] ...` callout 块提取。"""

    def test_simple_callout(self) -> None:
        p = parse("> [!note] this is a note")
        assert len(p.callouts) == 1
        c = p.callouts[0]
        assert c.kind == "note"
        assert c.body == "this is a note"

    def test_callout_body_includes_head_rest(self) -> None:
        """head 行 `> [!kind] 之后的内容` 算 body 第一行(title 暂未单独提取)。"""
        p = parse("> [!warning] Be careful\n> here be dragons")
        c = p.callouts[0]
        assert c.kind == "warning"
        assert c.body == "Be careful\nhere be dragons"
        assert c.title is None  # title 字段保留为 None — 见 parser 注释

    def test_multiple_callouts_ordered(self) -> None:
        p = parse("> [!note] first\n\n> [!tip] second")
        assert [c.kind for c in p.callouts] == ["note", "tip"]

    def test_render_callout_roundtrip(self) -> None:
        original = "> [!note] this is a note"
        rendered = render_callout("note", "this is a note")
        assert rendered == original

    def test_render_callout_with_multiline_body(self) -> None:
        """多行 callout — head 独立一行,body 各行加 > 前缀。"""
        rendered = render_callout("warning", "line one\nline two")
        # head 与 body 第一行分开(多行模式)
        assert rendered.startswith("> [!warning]\n")
        assert "> line one" in rendered
        assert "> line two" in rendered


class TestCommentExtraction:
    """`%%...%%` 单行注释提取。"""

    def test_inline_comment(self) -> None:
        p = parse("公开观点 %%其实我不太确定%% 但还是说了")
        assert p.comments == ("其实我不太确定",)
        # 注释从 body 中剥离
        assert "其实我不太确定" not in p.body
        assert "公开观点" in p.body

    def test_multiple_inline_comments(self) -> None:
        p = parse("%%first%% and %%second%% end")
        assert p.comments == ("first", "second")

    def test_render_subconscious(self) -> None:
        assert render_subconscious("hidden thought") == "%%\nhidden thought\n%%"


class TestFoldableSection:
    """`%%\\n...\\n%%` 折叠块提取。"""

    def test_block_fold(self) -> None:
        p = parse("text\n%%\n折叠的内容\n多行\n%%\nmore text")
        assert len(p.foldable_sections) == 1
        assert "折叠的内容" in p.foldable_sections[0].body
        assert "多行" in p.foldable_sections[0].body

    def test_fold_removed_from_body(self) -> None:
        p = parse("before\n%%\n隐藏内容\n%%\nafter")
        assert "隐藏内容" not in p.body
        assert "before" in p.body
        assert "after" in p.body


class TestCodeBlockFence:
    """代码块围栏 — 内部语法不解析。"""

    def test_fenced_code_preserved(self) -> None:
        p = parse("intro\n```\n[[not_a_wikilink]]\n#not_a_tag\n%%not_comment%%\n```\nend")
        assert p.wikilinks == ()
        assert p.tags_inline == ()
        assert p.comments == ()


class TestEmptyAndEdgeCases:
    """空文本 / 边界情况。"""

    def test_empty_string(self) -> None:
        p = parse("")
        assert p.body == ""
        assert p.wikilinks == ()
        assert p.callouts == ()
        assert p.comments == ()

    def test_only_whitespace(self) -> None:
        p = parse("   \n\n  \n")
        assert p.body == ""

    def test_unicode_content(self) -> None:
        p = parse("中文内容 #中文标签 [[中文链接]] end")
        assert any(w.target == "中文链接" for w in p.wikilinks)
        assert "#中文标签" in p.tags_inline

    def test_complex_mix(self) -> None:
        """真实场景: 标签 + 双链 + 注释 + callout 混排。"""
        text = (
            "正文 #主标签\n"
            "引用 [[session-1]]\n"
            "%%潜意识%%\n"
            "> [!note] 元认知提醒\n"
        )
        p = parse(text)
        assert "#主标签" in p.tags_inline
        assert any(w.target == "session-1" for w in p.wikilinks)
        assert p.comments == ("潜意识",)
        assert len(p.callouts) == 1
        assert p.callouts[0].kind == "note"


class TestParsedObsidianShape:
    """ParsedObsidian 字段类型契约。"""

    def test_fields_are_tuples(self) -> None:
        """所有 list 字段都是 tuple — frozen dataclass 兼容。"""
        p = parse("[[a]] [[b]] #t1 #t2 %%c1%%")
        assert isinstance(p.wikilinks, tuple)
        assert isinstance(p.embed_links, tuple)
        assert isinstance(p.tags_inline, tuple)
        assert isinstance(p.callouts, tuple)
        assert isinstance(p.comments, tuple)
        assert isinstance(p.foldable_sections, tuple)

    def test_body_is_string(self) -> None:
        p = parse("hello")
        assert isinstance(p.body, str)

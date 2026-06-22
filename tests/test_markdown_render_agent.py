"""Test mortis.toolagent.markdown_render — MarkdownRenderAgent."""

from __future__ import annotations

import pytest

from mortis.toolagent.markdown_render import MarkdownRenderAgent


SAMPLE = """\
---
title: 测试文档
tags:
  - alpha
  - beta
count: 3
active: true
---

正文 [[target-page]] 和 ![[embedded.md]] 的链接。
标签 #inline-tag 应该被识别。
"""


class TestMarkdownRenderAgent:
    def test_basic_extract(self):
        agent = MarkdownRenderAgent()
        r = agent.execute({"content": SAMPLE})
        assert r.success is True
        d = r.data
        assert "target-page" in d["wikilinks"]
        assert "embedded.md" in d["embed_links"]
        # tags_inline 包含 # 前缀 (Obsidian 解析层行为)
        assert any("inline-tag" in t for t in d["tags"])

    def test_frontmatter_parsed(self):
        agent = MarkdownRenderAgent()
        r = agent.execute({"content": SAMPLE})
        fm = r.data["frontmatter"]
        assert fm["title"] == "测试文档"
        assert fm["tags"] == ["alpha", "beta"]
        assert fm["count"] == 3
        assert fm["active"] is True

    def test_no_frontmatter(self):
        agent = MarkdownRenderAgent()
        r = agent.execute({"content": "无 frontmatter 的纯文本"})
        assert r.success is True
        assert r.data["frontmatter"] == {}
        assert r.data["wikilinks"] == []

    def test_callouts_parsed(self):
        agent = MarkdownRenderAgent()
        content = """> [!warning] 注意
> 这是警告内容"""
        r = agent.execute({"content": content})
        assert r.success is True
        assert len(r.data["callouts"]) == 1
        assert r.data["callouts"][0]["kind"] == "warning"
        assert "警告" in r.data["callouts"][0]["body"]

    def test_missing_content(self):
        agent = MarkdownRenderAgent()
        r = agent.execute({})
        assert r.success is False
        assert "content" in (r.error or "")

    def test_invalid_content_type(self):
        agent = MarkdownRenderAgent()
        r = agent.execute({"content": 12345})  # type: ignore[dict-item]
        assert r.success is False

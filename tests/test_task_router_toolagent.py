"""Test mortis.toolagent.router — TaskRouter."""

from __future__ import annotations

import pytest

from mortis.toolagent.router import TaskRouter, RouteDecision, TOOL_KEYWORDS


class TestTaskRouter:
    def test_route_to_read(self):
        r = TaskRouter()
        d = r.route("读一下 mortis-growth/identity/x.md")
        assert isinstance(d, RouteDecision)
        assert d.agent_id == "vault:read"
        assert "task" in d.input

    def test_route_to_search(self):
        r = TaskRouter()
        d = r.route("搜索所有 identity 维度的 growth")
        assert d.agent_id == "vault:search"

    def test_route_to_stats(self):
        r = TaskRouter()
        d = r.route("统计 vault 里有多少 growth")
        assert d.agent_id == "vault:stats"

    def test_route_to_markdown(self):
        r = TaskRouter()
        d = r.route("解析这段 Obsidian markdown")
        assert d.agent_id == "markdown:render"

    def test_route_to_clock(self):
        r = TaskRouter()
        d = r.route("现在几点?")
        assert d.agent_id == "clock"

    def test_no_match(self):
        r = TaskRouter()
        d = r.route("Mortis 你怎么看这件事?")  # 价值观判断
        assert d.agent_id is None
        assert "no tool keyword" in d.reason

    def test_longer_keyword_priority(self):
        """'读取 vault' 应优先于 '读' (防误匹配)。"""
        r = TaskRouter()
        d = r.route("读取 vault 里 identity 维度的 growth")
        assert d.agent_id == "vault:read"

    def test_case_insensitive(self):
        r = TaskRouter()
        d = r.route("Search for identity growth")  # 英文
        assert d.agent_id == "vault:search"

    def test_custom_keywords(self):
        r = TaskRouter(keywords={"foo": "custom:agent"})
        d = r.route("foo this thing")
        assert d.agent_id == "custom:agent"

    def test_default_keywords_loaded(self):
        assert "读" in TOOL_KEYWORDS or "读 vault" in TOOL_KEYWORDS

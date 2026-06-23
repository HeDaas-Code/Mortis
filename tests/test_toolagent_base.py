"""Test mortis.toolagent.base — ToolAgent 基础类 + ToolResult + from_tool 工厂。

issue #25 验收 #1。
"""

from __future__ import annotations

import importlib

import pytest

from mortis.toolagent.base import ToolAgent, ToolResult
from mortis.tools.base import ToolResult as ToolLayerResult


# ============================================================
# ToolResult 字段
# ============================================================


class TestToolResult:
    def test_success_construction(self):
        r = ToolResult(success=True, data={"x": 1}, error=None)
        assert r.success is True
        assert r.data == {"x": 1}
        assert r.error is None

    def test_failure_construction(self):
        r = ToolResult(success=False, data=None, error="boom")
        assert r.success is False
        assert r.data is None
        assert r.error == "boom"

    def test_frozen(self):
        r = ToolResult(success=True, data=1, error=None)
        with pytest.raises(Exception):  # FrozenInstanceError
            r.success = False  # type: ignore[misc]


# ============================================================
# ToolAgentProtocol / ToolAgent
# ============================================================


class _FakeTool:
    """最小 ToolProtocol 实现 — 测试用。"""

    def __init__(self, name: str = "fake:tool", result: ToolLayerResult | None = None,
                 raise_exc: Exception | None = None):
        self.name = name
        self._result = result
        self._raise = raise_exc
        self.calls: list[dict] = []

    @property
    def description(self) -> str:
        return "fake tool for testing"

    @property
    def input_schema(self) -> dict:
        return {"type": "object", "properties": {}}

    def execute(self, **kwargs) -> ToolLayerResult:
        self.calls.append(kwargs)
        if self._raise is not None:
            raise self._raise
        assert self._result is not None
        return self._result


class TestToolAgentExecute:
    def test_translate_success(self):
        tool = _FakeTool(result=ToolLayerResult.ok("fake", "hello"))
        agent = ToolAgent(tool=tool)
        r = agent.execute({"x": 1})
        assert r.success is True
        assert r.data == "hello"
        assert r.error is None

    def test_translate_failure(self):
        tool = _FakeTool(result=ToolLayerResult.err("fake", "fail"))
        agent = ToolAgent(tool=tool)
        r = agent.execute({})
        assert r.success is False
        assert r.data is None
        assert r.error == "fail"

    def test_translate_exception(self):
        tool = _FakeTool(raise_exc=ValueError("bad input"))
        agent = ToolAgent(tool=tool)
        r = agent.execute({})
        assert r.success is False
        assert r.data is None
        assert "bad input" in (r.error or "")

    def test_kwargs_passed_through(self):
        tool = _FakeTool(result=ToolLayerResult.ok("t", "ok"))
        agent = ToolAgent(tool=tool)
        agent.execute({"a": 1, "b": "x"})
        assert tool.calls == [{"a": 1, "b": "x"}]


class TestToolAgentFactory:
    def test_from_tool_default_agent_id(self):
        tool = _FakeTool(name="my:tool")
        agent = ToolAgent.from_tool(tool)
        assert agent.agent_id == "my:tool"

    def test_from_tool_override_agent_id(self):
        tool = _FakeTool(name="my:tool")
        agent = ToolAgent.from_tool(tool, agent_id="custom")
        assert agent.agent_id == "custom"

    def test_timeout_default_30(self):
        tool = _FakeTool()
        agent = ToolAgent(tool=tool)
        assert agent.timeout == 30


# ============================================================
# issue #72 MEDIUM-G — TaskRouter 已删除, 不应再导出
# ============================================================


class TestTaskRouterRemoved:
    """回归保护: toolagent.TaskRouter / RouteDecision / TOOL_KEYWORDS 已删除。

    防止未来有人重新引入这些类 — issue #72 修复后, 路由决策由 LLM 通过
    ToolRegistry tool calling 自发决定 (见 issue #64)。
    """

    def test_toolagent_package_does_not_export_task_router(self):
        """mortis.toolagent 不再导出 TaskRouter / RouteDecision / TOOL_KEYWORDS。"""
        import mortis.toolagent
        assert not hasattr(mortis.toolagent, "TaskRouter"), (
            "issue #72: TaskRouter 已删除, 不应再导出 — "
            "路由改由 LLM 通过 ToolRegistry 决定 (issue #64)"
        )
        assert not hasattr(mortis.toolagent, "RouteDecision"), (
            "issue #72: RouteDecision 已删除, 不应再导出"
        )
        assert not hasattr(mortis.toolagent, "TOOL_KEYWORDS"), (
            "issue #72: TOOL_KEYWORDS 已删除, 不应再导出"
        )

    def test_toolagent_router_module_removed(self):
        """mortis.toolagent.router 模块已删除 — ImportError 是预期行为。

        这是反断言: 如果未来有人把 router 加回来 (且没走 legacy 子包),
        此测试立即失败提醒。
        """
        with pytest.raises(ImportError):
            importlib.import_module("mortis.toolagent.router")

    def test_pipeline_task_router_preserved(self):
        """pipeline.TaskRouter 是不同类 (简单/复杂任务路由), 必须保留。"""
        from mortis.pipeline.router import TaskRouter as PipelineTaskRouter
        from mortis.pipeline.router import RouteDecision as PipelineRouteDecision

        # 验证是不同类 (来自 mortis.pipeline 而非 mortis.toolagent)
        assert PipelineTaskRouter.__module__ == "mortis.pipeline.router"
        assert PipelineRouteDecision.__module__ == "mortis.pipeline.router"

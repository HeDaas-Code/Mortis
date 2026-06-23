"""Test mortis.toolagent.base — ToolAgent provider 注入 (#63)。

issue #63 验收: ToolAgent 基类支持 provider 注入和 LLM 调用。
"""

from __future__ import annotations

import pytest

from mortis.toolagent.base import ToolAgent
from mortis.tools.base import ToolResult as ToolLayerResult
from mortis.provider.mock import MockProvider


class _FakeTool:
    """最小 ToolProtocol 实现 — 测试用。"""

    def __init__(self, name: str = "fake:tool", result: ToolLayerResult | None = None):
        self.name = name
        self._result = result or ToolLayerResult.ok(name, "ok")

    @property
    def description(self) -> str:
        return "fake tool"

    @property
    def input_schema(self) -> dict:
        return {"type": "object", "properties": {}}

    def execute(self, **kwargs) -> ToolLayerResult:
        return self._result


class TestToolAgentProvider:
    """issue #63: ToolAgent 支持 provider 注入。"""

    def test_provider_field_exists(self):
        """ToolAgent 应该有 provider 字段。"""
        tool = _FakeTool()
        agent = ToolAgent(tool=tool, provider=None)
        assert hasattr(agent, "provider")
        assert agent.provider is None

    def test_provider_can_be_set(self):
        """provider 可以被传入。"""
        tool = _FakeTool()
        mock = MockProvider()
        agent = ToolAgent(tool=tool, provider=mock)
        assert agent.provider is mock

    def test_provider_from_tool(self):
        """from_tool 工厂方法也支持 provider。"""
        tool = _FakeTool()
        mock = MockProvider()
        agent = ToolAgent.from_tool(tool=tool, provider=mock)
        assert agent.provider is mock

    def test_provider_from_tool_default_none(self):
        """from_tool 默认 provider 为 None。"""
        tool = _FakeTool()
        agent = ToolAgent.from_tool(tool=tool)
        assert agent.provider is None


class TestToolAgentLlmGenerate:
    """issue #63: ToolAgent._llm_generate() 方法。"""

    def test_llm_generate_no_provider_returns_none(self):
        """无 provider 时 _llm_generate 返回 None。"""
        tool = _FakeTool()
        agent = ToolAgent(tool=tool, provider=None)
        result = agent._llm_generate("hello")
        assert result is None

    def test_llm_generate_with_provider(self):
        """有 provider 时 _llm_generate 调用 provider。"""
        tool = _FakeTool()
        mock = MockProvider(responses=["test response"])
        agent = ToolAgent(tool=tool, provider=mock)
        result = agent._llm_generate("hello")
        assert result == "test response"

    def test_llm_generate_with_system_prompt(self):
        """_llm_generate 支持 system 参数。"""
        tool = _FakeTool()
        mock = MockProvider(responses=["response with system"])
        agent = ToolAgent(tool=tool, provider=mock)
        result = agent._llm_generate("user prompt", system="system prompt")
        assert result == "response with system"

    def test_llm_generate_exception_returns_none(self):
        """provider 抛异常时 _llm_generate 返回 None。"""

        class BadProvider:
            def generate_text(self, prompt, system="", **kwargs):
                raise RuntimeError("provider error")

        tool = _FakeTool()
        agent = ToolAgent(tool=tool, provider=BadProvider())
        result = agent._llm_generate("hello")
        assert result is None

    def test_llm_generate_passes_extra_kwargs(self):
        """_llm_generate 透传额外参数。"""
        tool = _FakeTool()
        received_kwargs = {}

        class InspectProvider:
            def generate_text(self, prompt, system="", **kwargs):
                received_kwargs.update(kwargs)
                return "ok"

        agent = ToolAgent(tool=tool, provider=InspectProvider())
        agent._llm_generate("test", temperature=0.5, max_tokens=100)
        assert "temperature" in received_kwargs
        assert received_kwargs["temperature"] == 0.5


class TestToolAgentBackwardCompat:
    """向后兼容性测试。"""

    def test_execute_still_works_without_provider(self):
        """无 provider 时 execute 方法仍正常工作。"""
        tool = _FakeTool(result=ToolLayerResult.ok("fake", "content"))
        agent = ToolAgent(tool=tool)
        r = agent.execute({"key": "value"})
        assert r.success is True
        assert r.data == "content"

    def test_execute_still_works_with_provider(self):
        """有 provider 时 execute 方法仍正常工作。"""
        tool = _FakeTool(result=ToolLayerResult.ok("fake", "content"))
        mock = MockProvider()
        agent = ToolAgent(tool=tool, provider=mock)
        r = agent.execute({})
        assert r.success is True
        assert r.data == "content"

"""Test mortis.toolagent.base — ToolAgent 基础类 + ToolResult + from_tool 工厂。

issue #25 验收 #1。
"""

from __future__ import annotations

import logging

import pytest

from mortis.provider.base import LLMProviderProtocol, Message
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
# _llm_generate (issue #70 MEDIUM-E)
# ============================================================


class _FakeProvider(LLMProviderProtocol):
    """最小 LLMProviderProtocol — 测试用,可注入异常或文本。"""

    def __init__(self, text: str | None = "ok", raise_exc: Exception | None = None):
        self._text = text
        self._raise = raise_exc
        self.calls: list[tuple[str, str]] = []

    def generate(
        self, messages, *, temperature=0.7, max_tokens=None,
    ) -> Message:
        return Message(role="assistant", content=self._text or "")

    def generate_text(
        self, prompt: str, system: str = "", *, temperature=0.7, max_tokens=None,
    ) -> str:
        self.calls.append((prompt, system))
        if self._raise is not None:
            raise self._raise
        assert self._text is not None
        return self._text


class TestToolAgentLlmGenerate:
    """issue #70 — _llm_generate 不再静默吞错, 所有失败路径均 log warning。"""

    def _build(self, provider):
        tool = _FakeTool(result=ToolLayerResult.ok("t", "ok"))
        return ToolAgent(tool=tool, provider=provider)

    def test_no_provider_returns_none(self):
        """无 provider → 返回 None, 不抛错 (与原行为一致)。"""
        agent = self._build(provider=None)
        assert agent._llm_generate("hi") is None

    def test_success_returns_text(self):
        """provider 正常返回 → 透传文本。"""
        agent = self._build(provider=_FakeProvider(text="hello"))
        assert agent._llm_generate("hi", system="sys") == "hello"

    def test_timeout_logged_and_returns_none(self, caplog):
        """TimeoutError → 降级 None + log WARNING。"""
        provider = _FakeProvider(raise_exc=TimeoutError("network slow"))
        agent = self._build(provider=provider)
        with caplog.at_level(logging.WARNING, logger="mortis.toolagent.base"):
            result = agent._llm_generate("hi")
        assert result is None
        # 验证 warning 至少 1 条 + 含 "timed out" 关键词
        warns = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warns) >= 1
        assert any("timed out" in r.getMessage() for r in warns)

    def test_rate_limit_logged_and_returns_none(self, caplog):
        """rate limit (provider 自定义异常) → 降级 None + log WARNING。"""
        provider = _FakeProvider(raise_exc=RuntimeError("rate limit exceeded"))
        agent = self._build(provider=provider)
        with caplog.at_level(logging.WARNING, logger="mortis.toolagent.base"):
            result = agent._llm_generate("hi")
        assert result is None
        warns = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warns) >= 1
        assert any("LLM generate failed" in r.getMessage() for r in warns)
        # 含异常类型名 — 便于运维快速定位
        assert any("RuntimeError" in r.getMessage() for r in warns)

    def test_auth_fail_logged_and_returns_none(self, caplog):
        """auth fail → 降级 None + log WARNING (原行为静默, 现可观测)。"""
        provider = _FakeProvider(raise_exc=PermissionError("invalid api key"))
        agent = self._build(provider=provider)
        with caplog.at_level(logging.WARNING, logger="mortis.toolagent.base"):
            result = agent._llm_generate("hi")
        assert result is None
        warns = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warns) >= 1
        assert any("PermissionError" in r.getMessage() for r in warns)

    def test_no_silent_swallow_any_exception(self, caplog):
        """任意 Exception (非 TimeoutError) 都必须产生 WARNING log。"""
        for exc in [
            ValueError("bad response"),
            ConnectionError("refused"),
            OSError("disk full"),
        ]:
            caplog.clear()
            provider = _FakeProvider(raise_exc=exc)
            agent = self._build(provider=provider)
            with caplog.at_level(logging.WARNING, logger="mortis.toolagent.base"):
                result = agent._llm_generate("hi")
            assert result is None, f"{type(exc).__name__} 应降级 None"
            warns = [r for r in caplog.records if r.levelno == logging.WARNING]
            assert len(warns) >= 1, (
                f"{type(exc).__name__} 必须产生 WARNING, "
                f"否则等于回到原 MEDIUM-E 静默吞错状态"
            )

    def test_log_includes_prompt_length(self, caplog):
        """WARNING log 含 prompt_len, 便于追踪 LLM 流量 (与 MEDIUM-I 审计配合)。"""
        provider = _FakeProvider(raise_exc=RuntimeError("boom"))
        agent = self._build(provider=provider)
        long_prompt = "x" * 1234
        with caplog.at_level(logging.WARNING, logger="mortis.toolagent.base"):
            agent._llm_generate(long_prompt)
        warns = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("prompt_len=1234" in r.getMessage() for r in warns)

    def test_log_includes_provider_class_name(self, caplog):
        """WARNING log 含 provider 类名, 便于多 provider 场景定位。"""
        provider = _FakeProvider(raise_exc=RuntimeError("boom"))
        agent = self._build(provider=provider)
        with caplog.at_level(logging.WARNING, logger="mortis.toolagent.base"):
            agent._llm_generate("hi")
        warns = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("_FakeProvider" in r.getMessage() for r in warns)

    def test_kwargs_passed_through_to_provider(self):
        """temperature/max_tokens 等 kwargs 透传给 provider.generate_text。"""
        provider = _FakeProvider(text="ok")
        agent = self._build(provider=provider)
        agent._llm_generate("hi", temperature=0.1, max_tokens=512)
        assert len(provider.calls) == 1
        assert provider.calls[0] == ("hi", "")

    def test_system_prompt_passed_through(self):
        """system 提示词透传。"""
        provider = _FakeProvider(text="ok")
        agent = self._build(provider=provider)
        agent._llm_generate("hi", system="you are a search reranker")
        assert provider.calls[0][1] == "you are a search reranker"

"""Test issue #93: provider.generate 支持 tools 参数 (function calling)。

验收链路:
- ToolRegistry.to_openai_schemas() 产出 OpenAI 兼容 schema
- MockProvider 模拟 function calling 响应 (Message.tool_calls)
- Step._extract_function_calls 解析 tool_calls
- Step._call_provider 透传 tools + 执行工具 + 回灌消息历史再生成
- 韧性层 (RetryProvider) 透传 tools 到内部 provider
- tools=None 时保持向后兼容 (不传 tools kwarg)
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from mortis.memory import Session, Thread
from mortis.pipeline.step import ActStep, Step
from mortis.provider import MockProvider
from mortis.provider.base import Message
from mortis.provider.resilience import RetryProvider
from mortis.runtime import RuntimeContext
from mortis.seed import Seed
from mortis.tools import ToolRegistry
from mortis.tools.base import ToolResult
from mortis.vault import Vault


# ============================================================
# 测试用工具 — 最小 ToolProtocol 实现
# ============================================================


class _ListDirTool:
    """模拟 vault:list 工具 — 返回固定目录列表。"""

    name = "vault:list"
    calls: list[dict] = []

    @property
    def description(self) -> str:
        return "列出 vault 目录下的文件"

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        }

    def execute(self, **kwargs) -> ToolResult:
        self.calls.append(kwargs)
        return ToolResult.ok("vault:list", "growth-001.md\ngrowth-002.md")


class _EmptySchemaTool:
    """input_schema 为空 — 验证 to_openai_schemas 的鲁棒占位。"""

    name = "clock:now"

    @property
    def description(self) -> str:
        return "返回当前时间"

    @property
    def input_schema(self) -> dict:
        return {}

    def execute(self, **kwargs) -> ToolResult:
        return ToolResult.ok("clock:now", "2026-06-30T12:00:00Z")


def _make_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(_ListDirTool())
    return reg


def _make_ctx(provider, tools=None) -> RuntimeContext:
    seed = Seed(
        identity="test", values="v", tone="t", agency="a",
        relations="r", creativity="c", mortality="m",
    )
    vault = Vault(tempfile.mkdtemp())
    session = Session(session_id="s1")
    thread = Thread(thread_id="t1", session_id="s1", task="列出 growth")
    return RuntimeContext(
        seed=seed, vault=vault, provider=provider,
        session=session, thread=thread, tools=tools,
    )


# ============================================================
# ToolRegistry.to_openai_schemas
# ============================================================


class TestToOpenaiSchemas:
    def test_produces_openai_format(self):
        reg = _make_registry()
        schemas = reg.to_openai_schemas()
        assert len(schemas) == 1
        s = schemas[0]
        assert s["type"] == "function"
        assert s["function"]["name"] == "vault:list"
        assert s["function"]["description"] == "列出 vault 目录下的文件"
        assert s["function"]["parameters"]["type"] == "object"
        assert "path" in s["function"]["parameters"]["properties"]

    def test_empty_schema_gets_minimal_object_placeholder(self):
        reg = ToolRegistry()
        reg.register(_EmptySchemaTool())
        schemas = reg.to_openai_schemas()
        assert len(schemas) == 1
        params = schemas[0]["function"]["parameters"]
        # 空 schema 应被填成最小合法 object schema
        assert params == {"type": "object", "properties": {}}

    def test_tool_schemas_delegates_to_to_openai_schemas(self):
        reg = _make_registry()
        # tool_schemas() 应与 to_openai_schemas() 等价 (向后兼容)
        assert reg.tool_schemas() == reg.to_openai_schemas()


# ============================================================
# MockProvider tool_calls 响应
# ============================================================


class TestMockProviderToolCalls:
    def test_mock_returns_tool_calls_when_configured(self):
        tool_calls = [{
            "id": "call_1",
            "type": "function",
            "function": {"name": "vault:list", "arguments": {"path": "mortis-growth/identity"}},
        }]
        provider = MockProvider(
            responses=[""],
            tool_calls_responses=[tool_calls],
        )
        msg = provider.generate([Message(role="user", content="hi")], tools=[{"type": "function"}])
        assert msg.tool_calls is not None
        assert msg.tool_calls[0]["function"]["name"] == "vault:list"

    def test_mock_without_tool_calls_returns_none(self):
        provider = MockProvider(responses=["hello"])
        msg = provider.generate([Message(role="user", content="hi")])
        assert msg.tool_calls is None


# ============================================================
# Step._extract_function_calls
# ============================================================


class TestExtractFunctionCalls:
    def test_parses_message_tool_calls(self):
        provider = MockProvider()
        ctx = _make_ctx(provider)
        step = ActStep("s1", ctx)
        msg = Message(
            role="assistant", content="",
            tool_calls=[{
                "id": "call_x",
                "type": "function",
                "function": {"name": "vault:list", "arguments": {"path": "x"}},
            }],
        )
        calls = step._extract_function_calls(msg)
        assert len(calls) == 1
        assert calls[0].name == "vault:list"
        assert calls[0].id == "call_x"
        assert calls[0].arguments == {"path": "x"}

    def test_returns_empty_when_no_tool_calls(self):
        provider = MockProvider()
        ctx = _make_ctx(provider)
        step = ActStep("s1", ctx)
        assert step._extract_function_calls(Message(role="assistant", content="hi")) == []


# ============================================================
# Step._call_provider 端到端: tools 透传 + 执行 + 回灌
# ============================================================


class TestCallProviderFunctionCalling:
    def test_executes_tool_call_and_regenerates(self):
        """完整链路: provider 返回 tool_calls → 执行工具 → 回灌 → 二次生成最终回复。"""
        tool = _ListDirTool()
        reg = ToolRegistry()
        reg.register(tool)

        tool_calls_resp = [{
            "id": "call_1",
            "type": "function",
            "function": {"name": "vault:list", "arguments": {"path": "mortis-growth"}},
        }]
        # 第 1 次返回 tool_calls, 第 2 次返回最终文本
        provider = MockProvider(
            responses=["", "找到 2 个 growth 文件"],
            tool_calls_responses=[tool_calls_resp, None],
        )
        ctx = _make_ctx(provider, tools=reg)
        step = ActStep("s1", ctx)

        messages = [Message(role="user", content="列出 growth")]
        resp, tool_results = step._call_provider(messages, reg)

        # 工具被执行
        assert len(tool_results) == 1
        assert tool_results[0]["name"] == "vault:list"
        assert "growth-001.md" in tool_results[0]["result"]
        # 最终回复是二次生成的文本
        assert resp.content == "找到 2 个 growth 文件"
        # 消息历史含: user → assistant(tool_calls) → tool(result)
        roles = [m.role for m in messages]
        assert roles == ["user", "assistant", "tool"]

    def test_no_tools_no_passthrough(self):
        """tools=None 时不传 tools kwarg (向后兼容老 provider 签名)。"""
        reg = _make_registry()
        provider = MockProvider(responses=["plain reply"])
        ctx = _make_ctx(provider, tools=reg)
        step = ActStep("s1", ctx)

        # 用一个不记录 tools 的 provider 验证不传 tools — MockProvider 接受 tools=None
        messages = [Message(role="user", content="hi")]
        resp, tool_results = step._call_provider(messages, None)
        assert resp.content == "plain reply"
        assert tool_results == []


# ============================================================
# 韧性层透传 tools
# ============================================================


class TestResilienceToolsPassthrough:
    def test_retry_provider_passes_tools_to_inner(self):
        """RetryProvider 透传 tools 到内部 MockProvider.generate。"""
        received_tools = []

        class _CaptureProvider(MockProvider):
            def generate(self, messages, *, temperature=0.7, max_tokens=None, tools=None):
                received_tools.append(tools)
                return super().generate(
                    messages, temperature=temperature, max_tokens=max_tokens,
                    **({"tools": tools} if tools is not None else {}),
                )

        inner = _CaptureProvider(responses=["ok"])
        retry = RetryProvider(inner, max_retries=1)
        tools_schema = [{"type": "function", "function": {"name": "x"}}]
        msg = retry.generate([Message(role="user", content="hi")], tools=tools_schema)
        assert msg.content == "ok"
        assert received_tools == [tools_schema]

    def test_retry_provider_omits_tools_when_none(self):
        """tools=None 时不传 tools kwarg, 兼容不接受 tools 的 provider。"""

        class _StrictProvider:
            """模拟老式 provider — generate 不接受 tools 参数。"""

            def __init__(self):
                self._calls = 0

            def generate(self, messages, *, temperature=0.7, max_tokens=None):
                self._calls += 1
                return Message(role="assistant", content="legacy-ok")

            def generate_text(self, prompt, system="", *, temperature=0.7, max_tokens=None):
                return "legacy-ok"

        inner = _StrictProvider()
        retry = RetryProvider(inner, max_retries=1)
        # tools=None (默认) → 不传 tools kwarg → _StrictProvider.generate 正常工作
        msg = retry.generate([Message(role="user", content="hi")])
        assert msg.content == "legacy-ok"
        assert inner._calls == 1

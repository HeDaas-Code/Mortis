"""Test async provider 接口 (issue #46)。

验收 issue #46:
- MockProvider.async_generate_text 返回正确结果
- MockProvider.async_generate 返回正确 Message
- MinimaxProvider.async_generate_text (mock urlopen)
- run_in_executor helper

注意: 项目未安装 pytest-asyncio, 故用 ``asyncio.run()`` 在同步测试中驱动协程,
避免引入额外依赖。
"""
from __future__ import annotations

import asyncio
import json
import threading
from unittest.mock import MagicMock, patch

import pytest

from mortis.provider.base import Message, run_in_executor
from mortis.provider.minimax import MinimaxProvider
from mortis.provider.mock import MockProvider


def _user_msg(content: str) -> list[Message]:
    return [Message(role="user", content=content)]


def _mock_urlopen_ok(content: str):
    """构造一个 urlopen 成功返回的 mock (与 test_providers.py 保持一致)。"""
    payload = json.dumps({
        "choices": [{"message": {"content": content}}],
    }).encode("utf-8")
    mock = MagicMock()
    mock.__enter__.return_value.read.return_value = payload
    return mock


# ============================================================
# MockProvider 异步接口
# ============================================================


class TestMockProviderAsync:
    """issue #46 — MockProvider 异步接口。"""

    def test_async_generate_text_returns_correct_result(self):
        """async_generate_text 返回与同步 generate_text 一致的结果。"""
        p = MockProvider()
        result = asyncio.run(p.async_generate_text("hello world"))
        expected = p.generate_text("hello world")
        assert result == expected
        assert "[mock:" in result

    def test_async_generate_text_uses_first_line(self):
        """async_generate_text 取 prompt 首行作为 snippet。"""
        p = MockProvider()
        result = asyncio.run(p.async_generate_text("line one\nline two"))
        assert "line one" in result

    def test_async_generate_text_with_responses(self):
        """async_generate_text 透传 responses 列表, 按调用顺序返回。"""
        p = MockProvider(responses=["resp-a", "resp-b"])
        a = asyncio.run(p.async_generate_text("prompt"))
        b = asyncio.run(p.async_generate_text("prompt"))
        assert a == "resp-a"
        assert b == "resp-b"

    def test_async_generate_text_passes_system(self):
        """async_generate_text 透传 system 参数 (不报错)。"""
        p = MockProvider()
        result = asyncio.run(p.async_generate_text("prompt", system="sys"))
        assert "[mock:" in result

    def test_async_generate_returns_correct_message(self):
        """async_generate 返回正确 Message (role=assistant)。"""
        p = MockProvider()
        result = asyncio.run(p.async_generate(_user_msg("hello")))
        assert isinstance(result, Message)
        assert result.role == "assistant"
        assert "hello" in result.content

    def test_async_generate_matches_sync(self):
        """async_generate 与同步 generate 结果一致。"""
        p = MockProvider()
        msgs = _user_msg("consistency check")
        sync_result = p.generate(msgs)
        async_result = asyncio.run(p.async_generate(msgs))
        assert async_result.content == sync_result.content
        assert async_result.role == sync_result.role

    def test_async_generate_passes_temperature_and_max_tokens(self):
        """async_generate 透传 temperature / max_tokens (不报错)。"""
        p = MockProvider()
        result = asyncio.run(
            p.async_generate(_user_msg("x"), temperature=0.1, max_tokens=10)
        )
        assert isinstance(result, Message)

    def test_async_generate_text_empty_prompt(self):
        """async_generate_text 空 prompt 仍返回 [mock:empty]。"""
        p = MockProvider()
        result = asyncio.run(p.async_generate_text(""))
        assert "[mock:" in result


# ============================================================
# MinimaxProvider 异步接口 (mock urlopen)
# ============================================================


class TestMinimaxProviderAsync:
    """issue #46 — MinimaxProvider 异步接口 (mock urlopen)。"""

    def test_async_generate_text_success(self):
        """async_generate_text 成功返回 (mock urlopen)。"""
        p = MinimaxProvider(api_key="k")
        with patch("urllib.request.urlopen", return_value=_mock_urlopen_ok("async hello")):
            result = asyncio.run(p.async_generate_text("test prompt"))
        assert result == "async hello"

    def test_async_generate_success(self):
        """async_generate 成功返回 Message (mock urlopen)。"""
        p = MinimaxProvider(api_key="k")
        with patch("urllib.request.urlopen", return_value=_mock_urlopen_ok("async msg")):
            result = asyncio.run(p.async_generate(_user_msg("hi")))
        assert isinstance(result, Message)
        assert result.role == "assistant"
        assert result.content == "async msg"

    def test_async_generate_text_matches_sync(self):
        """async_generate_text 与同步 generate_text 结果一致。"""
        p = MinimaxProvider(api_key="k")
        with patch("urllib.request.urlopen", return_value=_mock_urlopen_ok("same")):
            sync_result = p.generate_text("prompt")
        with patch("urllib.request.urlopen", return_value=_mock_urlopen_ok("same")):
            async_result = asyncio.run(p.async_generate_text("prompt"))
        assert async_result == sync_result

    def test_async_generate_text_no_key_raises_auth_error(self):
        """async_generate_text 无 key 时抛 MinimaxAuthError (在 thread 中传播)。"""
        from mortis.provider import MinimaxAuthError

        p = MinimaxProvider(api_key="")
        with pytest.raises(MinimaxAuthError):
            asyncio.run(p.async_generate_text("x"))

    def test_async_generate_concurrent(self):
        """async_generate 可并发触发多个调用 (daemon 模式核心场景)。"""
        p = MinimaxProvider(api_key="k")

        async def run_many():
            coros = [
                p.async_generate(_user_msg(f"call-{i}"))
                for i in range(5)
            ]
            return await asyncio.gather(*coros)

        with patch("urllib.request.urlopen", return_value=_mock_urlopen_ok("ok")):
            results = asyncio.run(run_many())
        assert len(results) == 5
        assert all(r.content == "ok" for r in results)


# ============================================================
# run_in_executor helper
# ============================================================


class TestRunInExecutor:
    """issue #46 — run_in_executor helper (provider 未实现异步时的 fallback)。"""

    def test_returns_result(self):
        """run_in_executor 返回同步函数的结果。"""
        def add(a, b):
            return a + b
        result = asyncio.run(run_in_executor(add, 2, 3))
        assert result == 5

    def test_passes_kwargs(self):
        """run_in_executor 透传 kwargs。"""
        def greet(name, greeting="hi"):
            return f"{greeting}, {name}"
        result = asyncio.run(run_in_executor(greet, "world", greeting="hello"))
        assert result == "hello, world"

    def test_runs_in_separate_thread(self):
        """run_in_executor 在独立线程中执行 (非主线程)。"""
        main_thread = threading.get_ident()

        def get_tid():
            return threading.get_ident()

        tid = asyncio.run(run_in_executor(get_tid))
        assert tid != main_thread

    def test_wraps_provider_sync_generate_text(self):
        """run_in_executor 可包装 provider 同步 generate_text 作为 fallback。"""
        p = MockProvider()
        result = asyncio.run(run_in_executor(p.generate_text, "fallback test"))
        assert "[mock:" in result
        # 与直接同步调用结果一致
        assert result == p.generate_text("fallback test")

    def test_wraps_provider_sync_generate(self):
        """run_in_executor 可包装 provider 同步 generate。"""
        p = MockProvider()
        msgs = _user_msg("wrapped generate")
        result = asyncio.run(run_in_executor(p.generate, msgs))
        assert isinstance(result, Message)
        assert result.role == "assistant"

    def test_propagates_exception(self):
        """run_in_executor 传播同步函数抛出的异常。"""
        def boom():
            raise ValueError("kaboom")

        with pytest.raises(ValueError, match="kaboom"):
            asyncio.run(run_in_executor(boom))

    def test_concurrent_execution(self):
        """run_in_executor 可并发执行多个同步调用 (不互相阻塞)。"""
        # 用默认 MockProvider (无 responses) — 每次结果由 prompt 确定性推导,
        # 不依赖共享 _call_count, 避免并发竞态导致断言 flaky。
        p = MockProvider()

        async def run_many():
            coros = [
                run_in_executor(p.generate_text, f"prompt-{i}")
                for i in range(3)
            ]
            return await asyncio.gather(*coros)

        results = asyncio.run(run_many())
        assert len(results) == 3
        # 每个结果都含对应 prompt 首行
        assert all("[mock:" in r for r in results)
        assert results[0] == "[mock:prompt-0]"
        assert results[1] == "[mock:prompt-1]"
        assert results[2] == "[mock:prompt-2]"


# ============================================================
# 异步接口「可选」语义 — fallback 验证
# ============================================================


class TestAsyncOptionalFallback:
    """issue #46 — 异步接口为可选; provider 未实现时 fallback 到同步。"""

    def test_provider_without_async_can_fallback(self):
        """未实现异步接口的 provider 可通过 run_in_executor fallback。"""
        class SyncOnlyProvider:
            """只实现同步接口的 provider (模拟未升级的 provider)。"""

            def generate(self, messages, *, temperature=0.7, max_tokens=None):
                return Message(role="assistant", content="sync-only")

            def generate_text(self, prompt, system="", *, temperature=0.7, max_tokens=None):
                return "sync-only-text"

        p = SyncOnlyProvider()
        # 未实现 async_generate_text -> fallback 到 run_in_executor
        assert not hasattr(p, "async_generate_text")
        result = asyncio.run(run_in_executor(p.generate_text, "hi"))
        assert result == "sync-only-text"

        msg = asyncio.run(run_in_executor(p.generate, _user_msg("hi")))
        assert msg.content == "sync-only"

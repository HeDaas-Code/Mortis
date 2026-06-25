"""Tests for provider resilience layer — Retry / CircuitBreaker / Fallback."""

import pytest
import time
import asyncio

from mortis.provider.base import Message
from mortis.provider.mock import MockProvider
from mortis.provider.resilience import (
    CircuitBreakerProvider,
    CircuitOpenError,
    CircuitState,
    FallbackProvider,
    RetryProvider,
    build_resilient_provider,
)


# ----- Flaky/Failing providers for testing -----

class FlakyProvider(MockProvider):
    """Fails N times on generate/generate_text, then succeeds."""
    def __init__(self, fail_count: int = 2):
        super().__init__()
        self._fail_remaining = fail_count

    def _maybe_fail(self):
        if self._fail_remaining > 0:
            self._fail_remaining -= 1
            raise RuntimeError(f"transient failure (remaining={self._fail_remaining})")

    def generate(self, messages, *, temperature=0.7, max_tokens=None):
        self._maybe_fail()
        return super().generate(messages, temperature=temperature, max_tokens=max_tokens)

    def generate_text(self, prompt, system="", *, temperature=0.7, max_tokens=None):
        self._maybe_fail()
        return super().generate_text(prompt, system=system, temperature=temperature, max_tokens=max_tokens)


class AlwaysFailProvider(MockProvider):
    def generate(self, messages, *, temperature=0.7, max_tokens=None):
        raise RuntimeError("always fails")
    def generate_text(self, prompt, system="", *, temperature=0.7, max_tokens=None):
        raise RuntimeError("always fails")
    async def async_generate(self, messages, *, temperature=0.7, max_tokens=None):
        raise RuntimeError("always fails")
    async def async_generate_text(self, prompt, system="", *, temperature=0.7, max_tokens=None):
        raise RuntimeError("always fails")


# ----- RetryProvider -----

class TestRetryProvider:
    def test_retries_and_recovers(self):
        flaky = FlakyProvider(fail_count=2)
        retry = RetryProvider(flaky, max_retries=3, base_delay=0.001, max_delay=0.01)
        result = retry.generate([Message(role="user", content="hi")])
        assert result.content
        assert retry.stats["total_retries"] == 2
        assert retry.stats["total_recovered"] == 1

    def test_exhausted_retries_raises(self):
        always_fail = AlwaysFailProvider()
        retry = RetryProvider(always_fail, max_retries=2, base_delay=0.001, max_delay=0.01)
        with pytest.raises(RuntimeError):
            retry.generate([Message(role="user", content="hi")])
        assert retry.stats["total_retries"] == 2

    def test_no_retry_on_success(self):
        mock = MockProvider()
        retry = RetryProvider(mock, max_retries=3, base_delay=0.001)
        result = retry.generate_text("hello")
        assert result
        assert retry.stats["total_retries"] == 0

    def test_generate_text_retries(self):
        flaky = FlakyProvider(fail_count=1)
        retry = RetryProvider(flaky, max_retries=3, base_delay=0.001)
        result = retry.generate_text("hello")
        assert result
        assert retry.stats["total_retries"] == 1

    def test_async_retry(self):
        flaky = FlakyProvider(fail_count=1)
        retry = RetryProvider(flaky, max_retries=3, base_delay=0.001)
        result = asyncio.run(retry.async_generate([Message(role="user", content="hi")]))
        assert result.content
        assert retry.stats["total_retries"] == 1


# ----- CircuitBreakerProvider -----

class TestCircuitBreaker:
    def test_stays_closed_on_success(self):
        mock = MockProvider()
        breaker = CircuitBreakerProvider(mock, failure_threshold=3)
        breaker.generate([Message(role="user", content="hi")])
        assert breaker.stats["state"] == CircuitState.CLOSED.value
        assert breaker.stats["consecutive_failures"] == 0

    def test_opens_after_threshold(self):
        fail = AlwaysFailProvider()
        breaker = CircuitBreakerProvider(fail, failure_threshold=3)
        for _ in range(3):
            with pytest.raises(RuntimeError):
                breaker.generate([Message(role="user", content="hi")])
        assert breaker.stats["state"] == CircuitState.OPEN.value
        assert breaker.stats["consecutive_failures"] == 3

    def test_rejects_when_open(self):
        fail = AlwaysFailProvider()
        breaker = CircuitBreakerProvider(fail, failure_threshold=2)
        for _ in range(2):
            with pytest.raises(RuntimeError):
                breaker.generate([Message(role="user", content="hi")])
        with pytest.raises(CircuitOpenError):
            breaker.generate([Message(role="user", content="hi")])
        assert breaker.stats["total_rejections"] >= 1

    def test_recovers_after_timeout(self):
        fail = AlwaysFailProvider()
        breaker = CircuitBreakerProvider(fail, failure_threshold=2, recovery_timeout=0.1)
        for _ in range(2):
            with pytest.raises(RuntimeError):
                breaker.generate([Message(role="user", content="hi")])
        assert breaker.stats["state"] == CircuitState.OPEN.value
        time.sleep(0.15)
        breaker._inner = MockProvider()
        result = breaker.generate([Message(role="user", content="hi")])
        assert result.content
        assert breaker.stats["state"] == CircuitState.CLOSED.value

    def test_generate_text_circuit(self):
        fail = AlwaysFailProvider()
        breaker = CircuitBreakerProvider(fail, failure_threshold=2)
        for _ in range(2):
            with pytest.raises(RuntimeError):
                breaker.generate_text("hi")
        with pytest.raises(CircuitOpenError):
            breaker.generate_text("hi")


# ----- FallbackProvider -----

class TestFallbackProvider:
    def test_uses_primary_on_success(self):
        primary = MockProvider()
        fallback = MockProvider()
        fb = FallbackProvider(primary, fallback)
        result = fb.generate_text("hello")
        assert result
        assert fb.stats["total_fallbacks"] == 0

    def test_falls_back_on_failure(self):
        primary = AlwaysFailProvider()
        fallback = MockProvider()
        fb = FallbackProvider(primary, fallback)
        result = fb.generate_text("hello")
        assert result
        assert fb.stats["total_fallbacks"] == 1

    def test_generate_falls_back(self):
        primary = AlwaysFailProvider()
        fallback = MockProvider()
        fb = FallbackProvider(primary, fallback)
        result = fb.generate([Message(role="user", content="hi")])
        assert result.content
        assert fb.stats["total_fallbacks"] == 1

    def test_both_fail_raises(self):
        primary = AlwaysFailProvider()

        class AlsoFail(MockProvider):
            def generate_text(self, *a, **kw):
                raise RuntimeError("fallback also fails")

        fb = FallbackProvider(primary, AlsoFail())
        with pytest.raises(RuntimeError):
            fb.generate_text("hello")

    def test_async_fallback(self):
        primary = AlwaysFailProvider()
        fallback = MockProvider()
        fb = FallbackProvider(primary, fallback)
        result = asyncio.run(fb.async_generate_text("hello"))
        assert result
        assert fb.stats["total_fallbacks"] == 1


# ----- build_resilient_provider -----

class TestBuildResilient:
    def test_builds_full_chain(self):
        primary = MockProvider()
        fallback = MockProvider()
        provider = build_resilient_provider(
            primary, fallback,
            max_retries=2, failure_threshold=5, recovery_timeout=30,
        )
        assert isinstance(provider, RetryProvider)
        assert isinstance(provider._inner, CircuitBreakerProvider)
        assert isinstance(provider._inner._inner, FallbackProvider)

    def test_builds_without_fallback(self):
        primary = MockProvider()
        provider = build_resilient_provider(primary, max_retries=2)
        assert isinstance(provider, RetryProvider)
        assert isinstance(provider._inner, CircuitBreakerProvider)
        assert not isinstance(provider._inner._inner, FallbackProvider)

    def test_full_chain_passes_through(self):
        primary = MockProvider()
        fallback = MockProvider()
        provider = build_resilient_provider(
            primary, fallback,
            max_retries=2, failure_threshold=5, recovery_timeout=30,
        )
        result = provider.generate_text("hello")
        assert result


# ----- Streaming -----

class TestStreaming:
    def test_mock_stream(self):
        mock = MockProvider()
        chunks = list(mock.generate_stream([Message(role="user", content="hello")]))
        assert len(chunks) > 0
        assert chunks[-1].finish_reason == "stop"
        full = "".join(c.delta for c in chunks)
        assert len(full) > 0

    def test_stream_chunk_dataclass(self):
        from mortis.provider.base import StreamChunk
        c = StreamChunk(delta="hello", finish_reason=None)
        assert c.delta == "hello"
        assert c.finish_reason is None

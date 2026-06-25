"""Mortis LLM provider 韧性层 — 重试 / 熔断 / 降级。

提供三种韧性包装器, 可任意组合叠加:
- ``RetryProvider`` — 指数退避重试, 处理瞬时网络抖动 / 5xx
- ``CircuitBreaker`` — 熔断保护, 连续失败达阈值后短路, 避免雪崩
- ``FallbackProvider`` — 降级策略, 主 provider 失败后切换备用 provider

设计原则:
- 透明包装: 实现 ``LLMProviderProtocol`` 全部接口 (含异步)
- 不可变配置: 构造后参数不变, 线程安全 (状态通过锁保护)
- 审计兼容: 不干扰 ``MinimaxProvider`` 的 hash 审计链路 (issue #87)
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .base import LLMProviderProtocol, Message, run_in_executor

_logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    """熔断器状态机。"""
    CLOSED = "closed"      # 正常放行, 记录失败计数
    OPEN = "open"          # 熔断中, 直接拒绝请求不走下游
    HALF_OPEN = "half_open"  # 半开探测, 放行一次试探


@dataclass
class CircuitBreakerStats:
    """熔断器运行时统计 (线程安全)。"""
    state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = 0
    total_calls: int = 0
    total_failures: int = 0
    total_rejections: int = 0
    total_recoveries: int = 0
    last_failure_time: float = 0.0
    last_state_change: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def record_success(self) -> None:
        with self._lock:
            self.total_calls += 1
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.CLOSED
                self.total_recoveries += 1
                self.last_state_change = time.monotonic()
                _logger.info("[circuit] recovered: HALF_OPEN -> CLOSED")
            self.consecutive_failures = 0

    def record_failure(self) -> None:
        with self._lock:
            self.total_calls += 1
            self.total_failures += 1
            self.consecutive_failures += 1
            self.last_failure_time = time.monotonic()

    def try_acquire(self) -> bool:
        """尝试获取调用许可。返回 True 表示放行, False 表示熔断拒绝。"""
        with self._lock:
            if self.state == CircuitState.OPEN:
                return False
            self.total_calls += 1
            return True

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "state": self.state.value,
                "consecutive_failures": self.consecutive_failures,
                "total_calls": self.total_calls,
                "total_failures": self.total_failures,
                "total_rejections": self.total_rejections,
                "total_recoveries": self.total_recoveries,
                "last_failure_time": self.last_failure_time,
                "last_state_change": self.last_state_change,
            }


class CircuitOpenError(RuntimeError):
    """熔断器开启时抛出 — 调用被短路拒绝。"""


class RetryProvider:
    """指数退避重试包装器 — 处理瞬时故障 (网络抖动 / 5xx / 超时)。

    可重试异常类型默认为 ``MinimaxAPIError`` (网络 / 5xx),
    不可重试的 ``MinimaxAuthError`` (401/403) 直接抛出不重试。

    Args:
        inner: 被包装的 provider (实现 LLMProviderProtocol)
        max_retries: 最大重试次数 (不含首次调用), 默认 3
        base_delay: 首次重试延迟 (秒), 默认 1.0
        max_delay: 最大延迟上限 (秒), 默认 30.0
        retryable_errors: 可重试的异常类型, 默认 ``(Exception,)``
            生产环境建议精确指定为 ``(MinimaxAPIError,)``
    """

    def __init__(
        self,
        inner: LLMProviderProtocol,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        retryable_errors: tuple[type[Exception], ...] = (Exception,),
    ) -> None:
        self._inner = inner
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._retryable_errors = retryable_errors
        self._total_retries = 0
        self._total_recovered = 0

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "total_retries": self._total_retries,
            "total_recovered": self._total_recovered,
        }

    def _compute_delay(self, attempt: int) -> float:
        """指数退避 + 抖动: delay = min(base * 2^attempt, max) * (0.5 + random)。"""
        import random
        delay = min(self._base_delay * (2 ** attempt), self._max_delay)
        jitter = 0.5 + random.random()
        return delay * jitter

    def _retry(self, fn, *args, **kwargs):
        """同步重试逻辑。"""
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                result = fn(*args, **kwargs)
                if attempt > 0:
                    self._total_recovered += 1
                    _logger.info("[retry] recovered after %d attempts", attempt)
                return result
            except self._retryable_errors as e:
                last_error = e
                if attempt < self._max_retries:
                    delay = self._compute_delay(attempt)
                    self._total_retries += 1
                    _logger.warning(
                        "[retry] attempt %d/%d failed: %s, retrying in %.1fs",
                        attempt + 1, self._max_retries, e, delay,
                    )
                    time.sleep(delay)
                else:
                    _logger.error("[retry] exhausted %d retries: %s", self._max_retries, e)
        raise last_error  # type: ignore[misc]

    async def _async_retry(self, fn, *args, **kwargs):
        """异步重试逻辑。"""
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                result = await fn(*args, **kwargs)
                if attempt > 0:
                    self._total_recovered += 1
                    _logger.info("[retry] async recovered after %d attempts", attempt)
                return result
            except self._retryable_errors as e:
                last_error = e
                if attempt < self._max_retries:
                    delay = self._compute_delay(attempt)
                    self._total_retries += 1
                    _logger.warning(
                        "[retry] async attempt %d/%d failed: %s, retrying in %.1fs",
                        attempt + 1, self._max_retries, e, delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    _logger.error("[retry] async exhausted %d retries: %s", self._max_retries, e)
        raise last_error  # type: ignore[misc]

    # ---- LLMProviderProtocol 实现 ----

    def generate(self, messages, *, temperature=0.7, max_tokens=None):
        return self._retry(
            self._inner.generate, messages,
            temperature=temperature, max_tokens=max_tokens,
        )

    def generate_text(self, prompt, system="", *, temperature=0.7, max_tokens=None):
        return self._retry(
            self._inner.generate_text, prompt, system=system,
            temperature=temperature, max_tokens=max_tokens,
        )

    async def async_generate(self, messages, *, temperature=0.7, max_tokens=None):
        return await self._async_retry(
            self._inner.async_generate, messages,
            temperature=temperature, max_tokens=max_tokens,
        )

    async def async_generate_text(self, prompt, system="", *, temperature=0.7, max_tokens=None):
        return await self._async_retry(
            self._inner.async_generate_text, prompt, system=system,
            temperature=temperature, max_tokens=max_tokens,
        )


class CircuitBreakerProvider:
    """熔断器包装器 — 连续失败达阈值后短路, 保护下游服务。

    状态机:
    - CLOSED: 正常放行, 记录 consecutive_failures
    - OPEN: 连续失败 >= failure_threshold, 直接拒绝所有请求
      持续 recovery_timeout 秒后自动进入 HALF_OPEN
    - HALF_OPEN: 放行一次试探调用
      - 成功 -> CLOSED (恢复)
      - 失败 -> OPEN (重新计时)

    Args:
        inner: 被包装的 provider
        failure_threshold: 连续失败阈值, 触发熔断, 默认 5
        recovery_timeout: 熔断恢复等待时间 (秒), 默认 60
        half_open_max_calls: 半开状态最大试探调用数, 默认 1
    """

    def __init__(
        self,
        inner: LLMProviderProtocol,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 1,
    ) -> None:
        self._inner = inner
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls
        self._stats = CircuitBreakerStats()
        self._half_open_inflight = 0
        self._lock = threading.Lock()

    @property
    def stats(self) -> dict[str, Any]:
        return self._stats.to_dict()

    def _check_state(self) -> bool:
        """检查并更新状态, 返回是否允许调用。"""
        now = time.monotonic()
        with self._lock:
            if self._stats.state == CircuitState.OPEN:
                # 检查是否已过恢复期
                if now - self._stats.last_failure_time >= self._recovery_timeout:
                    self._stats.state = CircuitState.HALF_OPEN
                    self._stats.last_state_change = now
                    self._half_open_inflight = 0
                    _logger.info("[circuit] OPEN -> HALF_OPEN (recovery timeout)")
                else:
                    self._stats.total_rejections += 1
                    return False

            if self._stats.state == CircuitState.HALF_OPEN:
                if self._half_open_inflight >= self._half_open_max_calls:
                    self._stats.total_rejections += 1
                    return False
                self._half_open_inflight += 1
                return True

            return True

    def _on_success(self) -> None:
        self._stats.record_success()
        with self._lock:
            if self._stats.state == CircuitState.HALF_OPEN:
                self._half_open_inflight = 0

    def _on_failure(self) -> None:
        with self._lock:
            self._stats.record_failure()
            if self._stats.consecutive_failures >= self._failure_threshold:
                if self._stats.state != CircuitState.OPEN:
                    self._stats.state = CircuitState.OPEN
                    self._stats.last_state_change = time.monotonic()
                    _logger.error(
                        "[circuit] -> OPEN (consecutive_failures=%d >= threshold=%d)",
                        self._stats.consecutive_failures, self._failure_threshold,
                    )
            if self._stats.state == CircuitState.HALF_OPEN:
                self._half_open_inflight = 0

    def _call(self, fn, *args, **kwargs):
        if not self._check_state():
            raise CircuitOpenError(
                f"circuit breaker is OPEN — "
                f"consecutive_failures={self._stats.consecutive_failures} "
                f"threshold={self._failure_threshold}"
            )
        try:
            result = fn(*args, **kwargs)
            self._on_success()
            return result
        except Exception:
            self._on_failure()
            raise

    async def _async_call(self, fn, *args, **kwargs):
        if not self._check_state():
            raise CircuitOpenError(
                f"circuit breaker is OPEN — "
                f"consecutive_failures={self._stats.consecutive_failures} "
                f"threshold={self._failure_threshold}"
            )
        try:
            result = await fn(*args, **kwargs)
            self._on_success()
            return result
        except Exception:
            self._on_failure()
            raise

    # ---- LLMProviderProtocol 实现 ----

    def generate(self, messages, *, temperature=0.7, max_tokens=None):
        return self._call(
            self._inner.generate, messages,
            temperature=temperature, max_tokens=max_tokens,
        )

    def generate_text(self, prompt, system="", *, temperature=0.7, max_tokens=None):
        return self._call(
            self._inner.generate_text, prompt, system=system,
            temperature=temperature, max_tokens=max_tokens,
        )

    async def async_generate(self, messages, *, temperature=0.7, max_tokens=None):
        return await self._async_call(
            self._inner.async_generate, messages,
            temperature=temperature, max_tokens=max_tokens,
        )

    async def async_generate_text(self, prompt, system="", *, temperature=0.7, max_tokens=None):
        return await self._async_call(
            self._inner.async_generate_text, prompt, system=system,
            temperature=temperature, max_tokens=max_tokens,
        )


class FallbackProvider:
    """降级包装器 — 主 provider 失败时切换备用 provider。

    典型用法:
    - 主: MinimaxProvider (高质量但可能不稳定)
    - 备: MockProvider (确定性但质量低)

    降级策略:
    1. 先调用主 provider
    2. 主失败 → 记录降级事件 → 调用备用 provider
    3. 备用也失败 → 抛出原始异常

    Args:
        primary: 主 provider
        fallback: 备用 provider
        fallback_on: 触发降级的异常类型, 默认 ``(Exception,)``
    """

    def __init__(
        self,
        primary: LLMProviderProtocol,
        fallback: LLMProviderProtocol,
        fallback_on: tuple[type[Exception], ...] = (Exception,),
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._fallback_on = fallback_on
        self._total_fallbacks = 0

    @property
    def stats(self) -> dict[str, Any]:
        return {"total_fallbacks": self._total_fallbacks}

    def _call_with_fallback(self, fn_name, primary_fn, fallback_fn, *args, **kwargs):
        try:
            return primary_fn(*args, **kwargs)
        except self._fallback_on as e:
            self._total_fallbacks += 1
            _logger.warning("[fallback] primary %s failed: %s, falling back to %s",
                            fn_name, e, type(self._fallback).__name__)
            return fallback_fn(*args, **kwargs)

    async def _async_call_with_fallback(self, fn_name, primary_fn, fallback_fn, *args, **kwargs):
        try:
            return await primary_fn(*args, **kwargs)
        except self._fallback_on as e:
            self._total_fallbacks += 1
            _logger.warning("[fallback] primary %s failed: %s, falling back to %s",
                            fn_name, e, type(self._fallback).__name__)
            return await fallback_fn(*args, **kwargs)

    # ---- LLMProviderProtocol 实现 ----

    def generate(self, messages, *, temperature=0.7, max_tokens=None):
        return self._call_with_fallback(
            "generate",
            self._primary.generate, self._fallback.generate,
            messages, temperature=temperature, max_tokens=max_tokens,
        )

    def generate_text(self, prompt, system="", *, temperature=0.7, max_tokens=None):
        return self._call_with_fallback(
            "generate_text",
            self._primary.generate_text, self._fallback.generate_text,
            prompt, system=system, temperature=temperature, max_tokens=max_tokens,
        )

    async def async_generate(self, messages, *, temperature=0.7, max_tokens=None):
        return await self._async_call_with_fallback(
            "async_generate",
            self._primary.async_generate, self._fallback.async_generate,
            messages, temperature=temperature, max_tokens=max_tokens,
        )

    async def async_generate_text(self, prompt, system="", *, temperature=0.7, max_tokens=None):
        return await self._async_call_with_fallback(
            "async_generate_text",
            self._primary.async_generate_text, self._fallback.async_generate_text,
            prompt, system=system, temperature=temperature, max_tokens=max_tokens,
        )


def build_resilient_provider(
    primary: LLMProviderProtocol,
    fallback: LLMProviderProtocol | None = None,
    *,
    max_retries: int = 3,
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
    retryable_errors: tuple[type[Exception], ...] = (Exception,),
) -> LLMProviderProtocol:
    """构建韧性 provider 链: Retry → CircuitBreaker → (Fallback →) primary。

    组合顺序 (外→内):
    1. RetryProvider (最外层) — 重试瞬时故障
    2. CircuitBreakerProvider — 熔断保护
    3. FallbackProvider (可选) — 降级到备用
    4. primary (最内层) — 实际 LLM 调用

    Args:
        primary: 主 provider
        fallback: 备用 provider (可选, 不传则无降级)
        max_retries: 重试次数
        failure_threshold: 熔断阈值
        recovery_timeout: 熔断恢复时间
        retryable_errors: 可重试异常类型

    Returns:
        包装后的韧性 provider
    """
    provider = primary
    if fallback is not None:
        provider = FallbackProvider(primary, fallback, fallback_on=retryable_errors)
    provider = CircuitBreakerProvider(
        provider,
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
    )
    provider = RetryProvider(
        provider,
        max_retries=max_retries,
        retryable_errors=retryable_errors,
    )
    return provider

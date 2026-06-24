"""Mortis LLM provider base — 通用接口与消息类型。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class Message:
    """LLM 消息。"""
    role: str  # system | user | assistant | tool
    content: str
    name: str | None = None  # for tool role
    tool_call_id: str | None = None  # for tool role


class LLMProviderProtocol(Protocol):
    """LLM provider 协议。接口契约：generate(messages) -> Message。

    issue #46: 新增可选异步接口 ``async_generate`` / ``async_generate_text``。
    provider 可选择实现异步接口; 若未实现, 调用方可通过 ``run_in_executor``
    helper 在 executor 中跑同步方法作为 fallback, 让 daemon 模式可以并发
    触发多个认知周期。

    注意: Protocol 仅声明签名, 不含实现。异步方法为「可选」—— provider
    可以不实现, 调用方检测 ``hasattr(provider, 'async_generate')`` 后
    fallback 到同步 + ``run_in_executor``。
    """

    def generate(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> Message:
        """给定消息历史，生成下一条回复。

        Args:
            messages: 消息列表（包含 system/user/assistant/tool）。
            temperature: 采样温度。
            max_tokens: 最大 token 数。

        Returns:
            模型生成的回复消息。
        """
        ...

    def generate_text(
        self,
        prompt: str,
        system: str = "",
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        """简单封装 — 单轮 prompt -> 字符串（向后兼容）。"""
        ...

    # ---- 异步接口 (可选实现, issue #46) ----
    # Protocol 仅声明签名; 默认 fallback 见 run_in_executor helper。

    async def async_generate(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> Message:
        """异步 generate。可选实现; 默认 fallback: 在 executor 中跑同步 generate。"""
        ...

    async def async_generate_text(
        self,
        prompt: str,
        system: str = "",
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        """异步 generate_text。可选实现; 默认 fallback: 在 executor 中跑同步 generate_text。"""
        ...


async def run_in_executor(func: Any, *args: Any, **kwargs: Any) -> Any:
    """在 asyncio executor 中运行同步函数。

    issue #46: provider 未实现异步接口时的默认 fallback。
    用于把同步 ``generate`` / ``generate_text`` 包成协程, 让 daemon 模式
    可以并发触发多个认知周期而不阻塞事件循环。

    Args:
        func: 同步可调用 (如 ``provider.generate`` / ``provider.generate_text``)。
        *args: 位置参数, 透传给 func。
        **kwargs: 关键字参数, 透传给 func。

    Returns:
        ``func(*args, **kwargs)`` 的返回值。
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


@dataclass
class ToolCall:
    """LLM 发起的工具调用请求。"""
    id: str
    name: str
    arguments: dict  # json serializable

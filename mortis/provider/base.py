"""Mortis LLM provider base — 通用接口与消息类型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class Message:
    """LLM 消息。"""
    role: str  # system | user | assistant | tool
    content: str
    name: str | None = None  # for tool role
    tool_call_id: str | None = None  # for tool role


class LLMProviderProtocol(Protocol):
    """LLM provider 协议。接口契约：generate(messages) -> Message。"""

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


@dataclass
class ToolCall:
    """LLM 发起的工具调用请求。"""
    id: str
    name: str
    arguments: dict  # json serializable

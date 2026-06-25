"""Mortis Gateway base — 消息信封 + 渠道协议。

渠道无关的消息类型:
- ``InboundMessage``: 从外部渠道进来的用户消息 (channel + sender_id + content)。
- ``OutboundMessage``: Mortis 要发回该渠道的回复 (channel + recipient_id + content)。

``Channel`` 协议:
- ``name``: 渠道标识 (web / wechat / telegram / discord ...)。
- ``send(OutboundMessage)``: 把回复推给该渠道的用户。
- ``start()`` / ``stop()``: 生命周期 (主动轮询渠道才需要, Web 渠道可空实现)。

实现新渠道的步骤:
1. 写一个实现 ``Channel`` 协议的类。
2. 在 ``registry`` 注册 (或直接实例化传给 ``Gateway``)。
3. ``Gateway.handle_inbound`` 会自动路由消息到 ``ChatService`` 并调 ``channel.send``。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable


@dataclass
class InboundMessage:
    """从外部渠道进来的用户消息。

    Attributes:
        channel: 渠道名 (web / wechat / telegram / discord ...)。
        sender_id: 发送者在渠道内的 ID (如微信 openid / telegram chat_id)。
        content: 消息文本。
        conversation_id: 可选 — 续接已有对话。None = 按 sender 映射或新建。
        timestamp: ISO8601 时间戳。
        metadata: 渠道特有附加字段 (如附件、消息 ID)。
    """
    channel: str
    sender_id: str
    content: str
    conversation_id: str | None = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).isoformat()
    )
    metadata: dict = field(default_factory=dict)


@dataclass
class OutboundMessage:
    """Mortis 发回渠道的回复。

    Attributes:
        channel: 目标渠道名。
        recipient_id: 接收者 ID (通常 = InboundMessage.sender_id)。
        content: 回复文本。
        conversation_id: 所属对话 ID。
        timestamp: ISO8601 时间戳。
        metadata: 渠道特有附加字段。
    """
    channel: str
    recipient_id: str
    content: str
    conversation_id: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).isoformat()
    )
    metadata: dict = field(default_factory=dict)


@runtime_checkable
class Channel(Protocol):
    """对话渠道协议 — 把 Mortis 接入一个外部消息平台。

    实现者需提供:
    - ``name``: 渠道唯一标识。
    - ``send(outbound)``: 推送回复到该渠道 (如调微信/Telegram API)。
    - ``start()`` / ``stop()``: 启停 (轮询/webhook 监听等)。被动渠道可空实现。
    """

    name: str

    def send(self, outbound: OutboundMessage) -> None:
        """把一条回复推送到该渠道的用户。"""
        ...

    def start(self) -> None:
        """启动渠道 (如监听 webhook / 开始轮询)。被动渠道可空实现。"""
        ...

    def stop(self) -> None:
        """停止渠道。被动渠道可空实现。"""
        ...


__all__ = ["InboundMessage", "OutboundMessage", "Channel"]

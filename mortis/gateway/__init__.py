"""Mortis Gateway — 对话渠道抽象层。

issue #89: Gateway 模块 — 把 Mortis 对话能力接入多种外部渠道。

设计:
- ``Channel``: 渠道协议 (Web / 微信 / Telegram / Discord ...)。每个渠道实现
  ``send(OutboundMessage)`` 把消息推给该渠道的用户。
- ``InboundMessage`` / ``OutboundMessage``: 渠道无关的消息信封。
- ``Gateway``: 中央路由 — 收到 InboundMessage → 调 ChatService → 产出 OutboundMessage。
  维护「渠道:发送者 → conversation_id」映射, 让同一用户跨轮次复用对话。
- ``WebChannel``: Web 渠道实现 (被动式, 由 web server 直接驱动, send 是 no-op)。

未来扩展 (接口已定义, 实现需外部 SDK):
- ``WeChatChannel``: 微信公众号/企业微信
- ``TelegramChannel``: Telegram Bot
- ``DiscordChannel``: Discord Bot

子模块:
- base: InboundMessage / OutboundMessage / Channel 协议
- registry: 渠道注册表 (按名称注册/获取)
- web: WebChannel 实现
- gateway: Gateway 路由器
"""

from __future__ import annotations

from .base import Channel, InboundMessage, OutboundMessage
from .gateway import Gateway
from .registry import get_channel, list_channels, register_channel
from .web import WebChannel

# 自动注册内置渠道
register_channel("web", WebChannel)

__all__ = [
    # 消息类型
    "InboundMessage",
    "OutboundMessage",
    # 渠道协议 + 实现
    "Channel",
    "WebChannel",
    # 注册表
    "register_channel",
    "get_channel",
    "list_channels",
    # 路由器
    "Gateway",
]

"""Mortis Gateway 路由器 — 把外部渠道消息路由到 ChatService。

``Gateway`` 是渠道与对话服务之间的中介:

    [外部渠道] --InboundMessage--> [Gateway] --send()--> [ChatService]
                                                          |
    [外部渠道] <--send(Outbound)-- [Gateway] <--response--+

职责:
1. 维护「渠道:发送者 → conversation_id」映射, 让同一用户跨轮次复用对话。
2. 调 ``ChatService.send`` / ``stream`` 生成回复。
3. 调 ``Channel.send`` 把回复推给该渠道 (Web 渠道是 no-op)。

用法::

    from mortis.gateway import Gateway, WebChannel, InboundMessage
    gw = Gateway(chat_service)
    gw.register_channel(WebChannel())

    inbound = InboundMessage(channel="web", sender_id="user-1", content="你好")
    outbound = gw.handle_inbound(inbound)
    print(outbound.content)
"""

from __future__ import annotations

import logging
from typing import Generator

from mortis.provider import StreamChunk
from mortis.web.chat import ChatService

from .base import Channel, InboundMessage, OutboundMessage

_logger = logging.getLogger(__name__)


class Gateway:
    """对话渠道网关 — 路由外部消息到 ChatService。

    Attributes:
        chat: 对话服务 (生成回复)。
        _channels: 已注册渠道 (name → Channel)。
        _sender_map: 「渠道:发送者」→ conversation_id 映射, 跨轮次复用对话。
    """

    def __init__(self, chat_service: ChatService) -> None:
        self.chat = chat_service
        self._channels: dict[str, Channel] = {}
        self._sender_map: dict[str, str] = {}

    # ----- 渠道管理 -----

    def register_channel(self, channel: Channel) -> None:
        """注册一个渠道。重名覆盖。"""
        self._channels[channel.name] = channel
        _logger.info("gateway: registered channel %r", channel.name)

    def get_channel(self, name: str) -> Channel | None:
        return self._channels.get(name)

    def list_channels(self) -> list[str]:
        return sorted(self._channels.keys())

    def start_all(self) -> None:
        """启动所有已注册渠道 (主动渠道开始监听)。"""
        for ch in self._channels.values():
            try:
                ch.start()
            except Exception as e:
                _logger.warning("channel %s start failed: %s", ch.name, e)

    def stop_all(self) -> None:
        """停止所有已注册渠道。"""
        for ch in self._channels.values():
            try:
                ch.stop()
            except Exception as e:
                _logger.warning("channel %s stop failed: %s", ch.name, e)

    # ----- 路由 -----

    def _resolve_conversation(self, msg: InboundMessage) -> str | None:
        """解析发送者对应的对话 ID。

        优先级: msg.conversation_id > sender_map[渠道:发送者]。
        """
        if msg.conversation_id:
            return msg.conversation_id
        key = self._sender_key(msg.channel, msg.sender_id)
        return self._sender_map.get(key)

    def _sender_key(self, channel: str, sender_id: str) -> str:
        return f"{channel}:{sender_id}"

    def _remember_sender(self, channel: str, sender_id: str, conv_id: str) -> None:
        self._sender_map[self._sender_key(channel, sender_id)] = conv_id

    def handle_inbound(self, msg: InboundMessage) -> OutboundMessage:
        """处理一条入站消息 → 返回出站回复 (同步)。

        1. 解析 conversation_id (显式或按 sender 映射)。
        2. 调 ChatService.send 生成回复。
        3. 记住 sender → conversation 映射。
        4. 调 channel.send 推送 (Web 渠道 no-op)。
        """
        conv_id = self._resolve_conversation(msg)
        resp = self.chat.send(msg.content, conv_id)
        self._remember_sender(msg.channel, msg.sender_id, resp.conversation_id)

        outbound = OutboundMessage(
            channel=msg.channel,
            recipient_id=msg.sender_id,
            content=resp.message,
            conversation_id=resp.conversation_id,
            metadata={"elapsed_sec": resp.elapsed_sec},
        )
        # 推送给渠道 (Web 是 no-op; 微信/Telegram 会真正推送)
        ch = self._channels.get(msg.channel)
        if ch is not None:
            try:
                ch.send(outbound)
            except Exception as e:
                _logger.warning(
                    "channel %s send failed: %s", msg.channel, e
                )
        return outbound

    def handle_inbound_stream(
        self, msg: InboundMessage
    ) -> tuple[str, Generator[StreamChunk, None, None]]:
        """流式处理入站消息 → 返回 (conversation_id, chunk 生成器)。

        调用方需自行消费生成器; 流结束后回复已写入对话历史。
        与 ``handle_inbound`` 不同, 此方法不调 ``channel.send`` ——
        流式场景下推送由调用方负责 (如 Web SSE 直接把 chunk 写进 HTTP 响应)。

        Returns:
            (conversation_id, generator) — conv_id 在流式开始前即可知。
        """
        conv_id = self._resolve_conversation(msg)
        # 预创建对话拿 cid (与 server SSE handler 同样的模式)
        conv = self.chat.get_or_create_conversation(conv_id)
        actual_cid = conv.conversation_id
        self._remember_sender(msg.channel, msg.sender_id, actual_cid)
        gen = self.chat.stream(msg.content, actual_cid)
        return actual_cid, gen


__all__ = ["Gateway"]

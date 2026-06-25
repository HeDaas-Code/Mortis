"""Mortis Gateway Web 渠道 — Web 对话渠道实现。

WebChannel 是被动式渠道:
- 不需要 ``start`` / ``stop`` (由 web server 直接驱动, 没有轮询/webhook)。
- ``send`` 是 no-op: Web 渠道的回复通过 HTTP 响应 (SSE) 同步返回给前端,
  不需要主动推送。

其它渠道 (微信/Telegram/Discord) 需要在 ``send`` 里调对应平台的 API 把消息
推给用户 — 那是主动推送模型, 与 Web 的同步返回不同。
"""

from __future__ import annotations

import logging

from .base import OutboundMessage

_logger = logging.getLogger(__name__)


class WebChannel:
    """Web 对话渠道 — 被动式, 由 HTTP server 驱动。

    - ``send``: no-op (Web 回复通过 SSE 同步返回, 不走推送)。
    - ``start`` / ``stop``: no-op (无后台轮询)。
    """

    name = "web"

    def send(self, outbound: OutboundMessage) -> None:
        """Web 渠道无需主动推送 — 回复已通过 HTTP 响应返回。"""
        _logger.debug(
            "web channel send (no-op): conv=%s recipient=%s",
            outbound.conversation_id,
            outbound.recipient_id,
        )

    def start(self) -> None:
        """Web 渠道无后台任务 — no-op。"""
        pass

    def stop(self) -> None:
        """Web 渠道无后台任务 — no-op。"""
        pass


__all__ = ["WebChannel"]

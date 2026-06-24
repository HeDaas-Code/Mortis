"""Mortis Web UI — owner 视角的 HTTP 浏览接口。

issue #52: 简单 HTTP server (stdlib http.server, 无外部依赖)。
issue #53: growth 浏览器 + dream 日历。
issue #54: owner 通知通道 (mortis-subconscious/owner-notify.json)。

子模块:
- server: MortisWebHandler + start_web_server
- notify: send_notification / read_notifications / mark_read
"""

from __future__ import annotations

from .notify import (
    NOTIFY_FILE,
    NOTIFY_SUBDIR,
    mark_read,
    read_notifications,
    send_notification,
)
from .server import MortisWebHandler, start_web_server

__all__ = [
    # server
    "MortisWebHandler",
    "start_web_server",
    # notify
    "NOTIFY_FILE",
    "NOTIFY_SUBDIR",
    "send_notification",
    "read_notifications",
    "mark_read",
]

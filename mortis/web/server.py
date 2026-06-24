"""Mortis Web UI — 简单 HTTP server 提供 growth/dream/unease 浏览。

issue #52: Web UI server (stdlib http.server, 无外部依赖)。
issue #53: growth 浏览器 + dream 日历 (GET /growths, GET /dreams)。
issue #54: owner 通知通道 (GET /notifications)。

端口默认 8765。路由:
- GET / → 仪表盘 (phase + unease + growth 概览)
- GET /growths → growth 列表 JSON
- GET /growths/<rel_path> → growth 详情 JSON
- GET /dreams → dream log 列表
- GET /unease → unease 状态 JSON
- GET /notifications → owner 通知列表

设计要点:
- 纯 stdlib http.server, 不引入 Flask 等外部依赖
- Web UI 是 owner 视角, 可以读 unease/steiner 隐藏层
- 通知文件位置: mortis-subconscious/owner-notify.json
- dream log 位置: mortis-dream-log/<level>/*.md
- start_web_server 创建并返回 server, 由调用方 (cmd_web) 决定何时 serve_forever
"""

from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

from mortis.clock import LogicalClock
from mortis.steiner import load_unease
from mortis.vault import Vault
from mortis.web.notify import read_notifications

_logger = logging.getLogger(__name__)


class MortisWebHandler(BaseHTTPRequestHandler):
    """HTTP 请求处理器。

    vault 类变量由 start_web_server 设置 — 单进程内只有一个 vault。
    所有路由返回 JSON (application/json; charset=utf-8)。
    """

    vault: Vault = None  # type: ignore[assignment]  # 由 start_server 设置

    def do_GET(self) -> None:  # noqa: N802 — http.server 要求此方法名
        path = urlparse(self.path).path

        if path == "/" or path == "":
            self._serve_dashboard()
        elif path == "/growths":
            self._serve_growths()
        elif path.startswith("/growths/"):
            rel = path[len("/growths/"):]
            self._serve_growth_detail(rel)
        elif path == "/unease":
            self._serve_unease()
        elif path == "/notifications":
            self._serve_notifications()
        elif path == "/dreams":
            self._serve_dreams()
        else:
            self._send_json(404, {"error": "not found"})

    # ----- helpers -----

    def _send_json(self, status: int, data: dict) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        )

    # ----- routes -----

    def _serve_dashboard(self) -> None:
        """GET / → phase + unease + growth 概览。"""
        clock = LogicalClock()
        phase = clock.state()
        unease = load_unease(self.vault)
        growths = self.vault.list_growths()
        data = {
            "phase": phase.value,
            "unease_max": round(unease.max_unease(), 2),
            "growth_count": len(growths),
            "endpoints": ["/growths", "/unease", "/notifications", "/dreams"],
        }
        self._send_json(200, data)

    def _serve_growths(self) -> None:
        """GET /growths → growth 列表 (限制 50 条预览)。"""
        rels = self.vault.list_growths()
        growths = []
        for rel in rels[:50]:  # 限制 50 条
            try:
                g = self.vault.read_growth(rel)
                growths.append({
                    "rel_path": rel,
                    "id": g.id,
                    "dimension": g.dimension.value,
                    "confidence": g.confidence,
                    "body_preview": g.body[:100],
                    "tags": list(g.tags),
                })
            except Exception:
                # 解析失败的文件跳过 (与 list_growths_by_tag 一致)
                pass
        self._send_json(200, {"growths": growths, "total": len(rels)})

    def _serve_growth_detail(self, rel_path: str) -> None:
        """GET /growths/<rel_path> → 单条 growth 详情。"""
        try:
            g = self.vault.read_growth(rel_path)
            self._send_json(200, {
                "id": g.id,
                "dimension": g.dimension.value,
                "confidence": g.confidence,
                "body": g.body,
                "tags": list(g.tags),
                "source_sessions": list(g.source_sessions),
                "dream_level": g.dream_level.value if g.dream_level else None,
                "emotional_valence": g.emotional_valence,
                "emotional_arousal": g.emotional_arousal,
            })
        except Exception as e:
            self._send_json(404, {"error": str(e)})

    def _serve_unease(self) -> None:
        """GET /unease → unease 状态 (owner 视角, 可读隐藏层)。"""
        unease = load_unease(self.vault)
        data = {
            "max_unease": round(unease.max_unease(), 3),
            "per_dimension": {
                dim.value: round(val, 3)
                for dim, val in unease.per_dimension.items()
            },
            "last_decay": unease.last_decay,
        }
        self._send_json(200, data)

    def _serve_notifications(self) -> None:
        """GET /notifications → owner 通知列表。

        读取 mortis-subconscious/owner-notify.json (issue #54)。
        文件不存在 / 损坏 → 返回空列表 (不抛错)。
        """
        notifications = read_notifications(self.vault)
        self._send_json(200, {"notifications": notifications})

    def _serve_dreams(self) -> None:
        """GET /dreams → dream log 列表。

        扫 mortis-dream-log/<level>/*.md, 按 level 分组。
        每个 level 取最近 20 条 (按文件名排序)。
        """
        dream_log_dir = self.vault.root / "mortis-dream-log"
        if not dream_log_dir.exists():
            self._send_json(200, {"dreams": []})
            return
        dreams = []
        for level_dir in sorted(dream_log_dir.iterdir()):
            if not level_dir.is_dir():
                continue
            for f in sorted(level_dir.glob("*.md"))[:20]:
                dreams.append({
                    "level": level_dir.name,
                    "file": f.name,
                    "rel_path": str(f.relative_to(self.vault.root)),
                })
        self._send_json(200, {"dreams": dreams})

    # ----- logging -----

    def log_message(self, format, *args) -> None:  # noqa: A002 — shadowing ok
        """覆盖默认 stderr 输出, 改走 logging (debug 级别)。"""
        _logger.debug("web: " + format, *args)


def start_web_server(vault_path: str = "vault", port: int = 8765) -> HTTPServer:
    """启动 Web UI server。

    创建 HTTPServer 并绑定 vault 到 handler 类变量, 但**不阻塞** —
    由调用方 (cmd_web) 调 server.serve_forever() 决定何时开始服务。

    Args:
        vault_path: vault 根目录路径。
        port: 监听端口 (默认 8765)。

    Returns:
        HTTPServer 实例 (已 bind, 未 serve_forever)。
    """
    vault = Vault(vault_path)
    MortisWebHandler.vault = vault
    server = HTTPServer(("0.0.0.0", port), MortisWebHandler)
    _logger.info("Web UI started on http://localhost:%d", port)
    return server


__all__ = ["MortisWebHandler", "start_web_server"]

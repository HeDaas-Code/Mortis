"""Mortis Web UI — HTTP server 提供 growth/dream/unease 浏览。

issue #52: Web UI server (stdlib http.server, 无外部依赖)。
issue #53: growth 浏览器 + dream 日历 (GET /growths, GET /dreams)。
issue #54: owner 通知通道 (GET /notifications)。

端口默认 8765。路由:
- GET / → 仪表盘 (HTML 页面, 含 phase + unease + growth 概览)
- GET /growths → growth 列表 (HTML 页面)
- GET /growths/<rel_path> → growth 详情 (HTML 页面)
- GET /unease → unease 仪表盘 (HTML 页面, 7 维度雷达图)
- GET /notifications → owner 通知 (HTML 页面)
- GET /dreams → dream 日历 (HTML 页面)

API 端点 (返回 JSON, 前端 JS fetch 调用):
- GET /api/dashboard → JSON
- GET /api/growths → JSON
- GET /api/growths/<rel> → JSON
- GET /api/unease → JSON
- GET /api/notifications → JSON
- GET /api/dreams → JSON

设计要点:
- 纯 stdlib http.server, 不引入 Flask 等外部依赖
- HTML 页面内嵌 CSS + vanilla JS, 无构建工具
- 前端交互: pretty-print 切换 / growth 过滤 / 异步加载
- Web UI 是 owner 视角, 可以读 unease/steiner 隐藏层
"""

from __future__ import annotations

import html
import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

from mortis.clock import LogicalClock
from mortis.steiner import load_unease
from mortis.vault import Vault
from mortis.web.notify import read_notifications

_logger = logging.getLogger(__name__)


# ===== CSS =====

_CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; background: #1a1a2e; color: #e0e0e0; padding: 20px; }
h1 { color: #8be9fd; margin-bottom: 16px; font-size: 1.8em; }
h2 { color: #bd93f9; margin: 16px 0 8px; font-size: 1.3em; }
.card { background: #16213e; border-radius: 8px; padding: 16px; margin-bottom: 16px; border: 1px solid #0f3460; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; }
.stat { display: inline-block; background: #0f3460; padding: 8px 16px; border-radius: 4px; margin: 4px; }
.stat-label { color: #6272a4; font-size: 0.85em; }
.stat-value { color: #50fa7b; font-size: 1.5em; font-weight: bold; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: 8px 12px; border-bottom: 1px solid #0f3460; }
th { color: #8be9fd; font-weight: 600; }
tr:hover { background: #0f3460; }
a { color: #8be9fd; text-decoration: none; }
a:hover { text-decoration: underline; }
.btn { display: inline-block; padding: 6px 16px; background: #50fa7b; color: #1a1a2e; border: none; border-radius: 4px; cursor: pointer; font-weight: 600; }
.btn:hover { background: #6aff8c; }
.checkbox-row { display: flex; align-items: center; gap: 8px; margin: 8px 0; }
.checkbox-row input { width: 18px; height: 18px; }
.bar-chart { margin: 8px 0; }
.bar-row { display: flex; align-items: center; gap: 8px; margin: 4px 0; }
bar-label { width: 100px; color: #6272a4; font-size: 0.9em; }
.bar-track { flex: 1; height: 20px; background: #0f3460; border-radius: 2px; overflow: hidden; }
.bar-fill { height: 100%; background: #ff79c6; transition: width 0.3s; }
.bar-value { width: 50px; text-align: right; color: #f8f8f2; font-size: 0.85em; }
pre { background: #0d1117; padding: 12px; border-radius: 4px; overflow-x: auto; font-size: 0.9em; color: #f8f8f2; }
pre.compact { white-space: pre-wrap; }
.notification { padding: 12px; border-radius: 4px; margin: 8px 0; }
.notification.warning { background: #3b2317; border-left: 4px solid #ffb86c; }
.notification.info { background: #1a2332; border-left: 4px solid #8be9fd; }
.notification.error { background: #2e1a1a; border-left: 4px solid #ff5555; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 2px; font-size: 0.8em; font-weight: 600; }
.badge.light { background: #6272a4; color: #fff; }
.badge.medium { background: #ffb86c; color: #1a1a2e; }
.badge.deep { background: #ff79c6; color: #1a1a2e; }
.tag { display: inline-block; padding: 2px 6px; background: #0f3460; border-radius: 2px; margin: 2px; font-size: 0.8em; color: #6272a4; }
.growth-card { background: #16213e; border-radius: 8px; padding: 12px; border: 1px solid #0f3460; }
.growth-card h3 { color: #50fa7b; margin-bottom: 8px; }
.filter-input { padding: 6px 12px; background: #0d1117; border: 1px solid #0f3460; border-radius: 4px; color: #e0e0e0; width: 200px; }
nav { margin-bottom: 20px; }
nav a { padding: 6px 12px; margin-right: 4px; border-radius: 4px; }
nav a:hover, nav a.active { background: #0f3460; text-decoration: none; }
"""

# ===== JS =====

_JS = """
function togglePrettyPrint() {
  document.querySelectorAll('pre').forEach(el => {
    el.classList.toggle('compact');
  });
}
function filterGrowths() {
  const q = document.getElementById('filter-input').value.toLowerCase();
  document.querySelectorAll('.growth-card').forEach(card => {
    const text = card.textContent.toLowerCase();
    card.style.display = text.includes(q) ? '' : 'none';
  });
}
function refreshData(endpoint) {
  fetch('/api/' + endpoint).then(r => r.json()).then(data => {
    document.getElementById('refresh-status').textContent = '✓ 已刷新 ' + new Date().toLocaleTimeString();
  }).catch(e => {
    document.getElementById('refresh-status').textContent = '✗ 刷新失败: ' + e;
  });
}
"""


class MortisWebHandler(BaseHTTPRequestHandler):
    """HTTP 请求处理器 — 同时服务 HTML 页面和 JSON API。

    内容协商:
    - 路径以 /api/ 开头 → JSON
    - 否则 → HTML 页面 (含内嵌 CSS + JS)
    """

    vault: Vault = None  # type: ignore[assignment]

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        # API 路由 (/api/...)
        if path.startswith("/api/"):
            api_path = path[len("/api/"):]
            self._route_api(api_path)
            return

        # HTML 页面路由
        if path == "/" or path == "":
            self._serve_html_dashboard()
        elif path == "/growths":
            self._serve_html_growths()
        elif path.startswith("/growths/"):
            rel = path[len("/growths/"):]
            self._serve_html_growth_detail(rel)
        elif path == "/unease":
            self._serve_html_unease()
        elif path == "/notifications":
            self._serve_html_notifications()
        elif path == "/dreams":
            self._serve_html_dreams()
        else:
            self._send_json(404, {"error": "not found"})

    # ----- 通用发送 -----

    def _send_json(self, status: int, data: dict) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(
            json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        )

    def _send_html(self, status: int, html_content: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html_content.encode("utf-8"))

    def _html_wrap(self, title: str, body: str, active_nav: str = "") -> str:
        nav_items = [
            ("/", "仪表盘", "dashboard"),
            ("/growths", "Growth", "growths"),
            ("/unease", "Unease", "unease"),
            ("/notifications", "通知", "notifications"),
            ("/dreams", "Dream", "dreams"),
        ]
        nav_html = ""
        for href, label, key in nav_items:
            cls = ' class="active"' if key == active_nav else ""
            nav_html += f'<a href="{href}"{cls}>{label}</a>'

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} — Mortis Web UI</title>
<style>{_CSS}</style>
</head>
<body>
<h1>🧠 Mortis Web UI</h1>
<nav>{nav_html}</nav>
{body}
<script>{_JS}</script>
</body>
</html>"""

    # ===== API 路由 (JSON) =====

    def _route_api(self, path: str) -> None:
        if path == "dashboard" or path == "":
            self._api_dashboard()
        elif path == "growths":
            self._api_growths()
        elif path.startswith("growths/"):
            rel = path[len("growths/"):]
            self._api_growth_detail(rel)
        elif path == "unease":
            self._api_unease()
        elif path == "notifications":
            self._api_notifications()
        elif path == "dreams":
            self._api_dreams()
        else:
            self._send_json(404, {"error": "not found"})

    def _api_dashboard(self) -> None:
        clock = LogicalClock()
        phase = clock.state()
        unease = load_unease(self.vault)
        growths = self.vault.list_growths()
        self._send_json(200, {
            "phase": phase.value,
            "unease_max": round(unease.max_unease(), 2),
            "growth_count": len(growths),
            "endpoints": ["/growths", "/unease", "/notifications", "/dreams"],
        })

    def _api_growths(self) -> None:
        rels = self.vault.list_growths()
        growths = []
        for rel in rels[:50]:
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
                pass
        self._send_json(200, {"growths": growths, "total": len(rels)})

    def _api_growth_detail(self, rel_path: str) -> None:
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

    def _api_unease(self) -> None:
        unease = load_unease(self.vault)
        self._send_json(200, {
            "max_unease": round(unease.max_unease(), 3),
            "per_dimension": {
                dim.value: round(val, 3)
                for dim, val in unease.per_dimension.items()
            },
            "last_decay": unease.last_decay,
        })

    def _api_notifications(self) -> None:
        notifications = read_notifications(self.vault)
        self._send_json(200, {"notifications": notifications})

    def _api_dreams(self) -> None:
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

    # ===== HTML 页面路由 =====

    def _serve_html_dashboard(self) -> None:
        clock = LogicalClock()
        phase = clock.state()
        unease = load_unease(self.vault)
        growths = self.vault.list_growths()
        growth_count = len(growths)

        body = f"""
<div class="card">
  <h2>系统状态</h2>
  <div class="grid">
    <div class="stat"><div class="stat-label">当前时段</div><div class="stat-value">{html.escape(phase.value)}</div></div>
    <div class="stat"><div class="stat-label">Unease 最大值</div><div class="stat-value">{unease.max_unease():.2f}</div></div>
    <div class="stat"><div class="stat-label">Growth 总数</div><div class="stat-value">{growth_count}</div></div>
  </div>
</div>
<div class="card">
  <h2>快速导航</h2>
  <p><a href="/growths">浏览 Growth 列表</a> · <a href="/unease">查看 Unease 仪表盘</a> · <a href="/notifications">Owner 通知</a> · <a href="/dreams">Dream 日历</a></p>
</div>
<div class="card">
  <h2>API 端点 (JSON)</h2>
  <table><tr><th>端点</th><th>说明</th></tr>
  <tr><td><a href="/api/dashboard">/api/dashboard</a></td><td>仪表盘 JSON</td></tr>
  <tr><td><a href="/api/growths">/api/growths</a></td><td>Growth 列表 JSON</td></tr>
  <tr><td><a href="/api/unease">/api/unease</a></td><td>Unease 状态 JSON</td></tr>
  <tr><td><a href="/api/notifications">/api/notifications</a></td><td>通知列表 JSON</td></tr>
  <tr><td><a href="/api/dreams">/api/dreams</a></td><td>Dream 日历 JSON</td></tr>
  </table>
</div>
<div class="card">
  <h2>前端交互</h2>
  <div class="checkbox-row">
    <input type="checkbox" id="pretty-print" onchange="togglePrettyPrint()" checked>
    <label for="pretty-print">Pretty Print (紧凑模式切换)</label>
  </div>
  <button class="btn" onclick="refreshData('dashboard')">刷新数据</button>
  <span id="refresh-status" style="margin-left:8px;color:#6272a4;"></span>
</div>
"""
        self._send_html(200, self._html_wrap("仪表盘", body, "dashboard"))

    def _serve_html_growths(self) -> None:
        rels = self.vault.list_growths()
        cards = []
        for rel in rels[:50]:
            try:
                g = self.vault.read_growth(rel)
                tags_html = "".join(f'<span class="tag">{html.escape(t)}</span>' for t in g.tags)
                cards.append(f"""
<div class="growth-card" data-dimension="{html.escape(g.dimension.value)}">
  <h3><a href="/growths/{html.escape(rel)}">{html.escape(g.id)}</a></h3>
  <p><strong>维度:</strong> {html.escape(g.dimension.value)} | <strong>置信度:</strong> {g.confidence:.2f}</p>
  <p>{html.escape(g.body[:200])}</p>
  <p>{tags_html}</p>
</div>""")
            except Exception:
                pass

        body = f"""
<div class="card">
  <h2>Growth 列表 (共 {len(rels)} 条)</h2>
  <input type="text" class="filter-input" id="filter-input" placeholder="过滤 growth..." oninput="filterGrowths()">
  <span style="margin-left:8px;color:#6272a4;">输入关键词过滤</span>
</div>
<div class="grid">
  {"".join(cards)}
</div>
"""
        self._send_html(200, self._html_wrap("Growth 列表", body, "growths"))

    def _serve_html_growth_detail(self, rel_path: str) -> None:
        try:
            g = self.vault.read_growth(rel_path)
            tags_html = "".join(f'<span class="tag">{html.escape(t)}</span>' for t in g.tags)
            body = f"""
<div class="card">
  <h2>{html.escape(g.id)}</h2>
  <table>
    <tr><th>字段</th><th>值</th></tr>
    <tr><td>维度</td><td>{html.escape(g.dimension.value)}</td></tr>
    <tr><td>置信度</td><td>{g.confidence:.2f}</td></tr>
    <tr><td>标签</td><td>{tags_html}</td></tr>
    <tr><td>来源 Session</td><td>{", ".join(g.source_sessions) or "无"}</td></tr>
    <tr><td>Dream 级别</td><td>{g.dream_level.value if g.dream_level else "N/A"}</td></tr>
    <tr><td>情感 Valence</td><td>{g.emotional_valence if g.emotional_valence is not None else "N/A"}</td></tr>
    <tr><td>情感 Arousal</td><td>{g.emotional_arousal if g.emotional_arousal is not None else "N/A"}</td></tr>
  </table>
</div>
<div class="card">
  <h2>内容</h2>
  <pre class="compact">{html.escape(g.body)}</pre>
</div>
<div class="card">
  <h2>API</h2>
  <pre><a href="/api/growths/{html.escape(rel_path)}">/api/growths/{html.escape(rel_path)}</a></pre>
</div>
"""
            self._send_html(200, self._html_wrap(f"Growth: {g.id}", body, "growths"))
        except Exception as e:
            body = f'<div class="card"><h2>错误</h2><p>{html.escape(str(e))}</p></div>'
            self._send_html(404, self._html_wrap("Growth 未找到", body, "growths"))

    def _serve_html_unease(self) -> None:
        unease = load_unease(self.vault)
        bars = []
        for dim, val in sorted(unease.per_dimension.items(), key=lambda x: -x[1]):
            pct = min(int(val * 100), 100)
            bars.append(f"""
<div class="bar-row">
  <span class="bar-label">{html.escape(dim.value)}</span>
  <div class="bar-track"><div class="bar-fill" style="width:{pct}%"></div></div>
  <span class="bar-value">{val:.3f}</span>
</div>""")

        body = f"""
<div class="card">
  <h2>Unease 仪表盘</h2>
  <div class="stat"><div class="stat-label">最大 Unease</div><div class="stat-value">{unease.max_unease():.3f}</div></div>
  <div class="stat"><div class="stat-label">上次衰减</div><div class="stat-value" style="font-size:1em;">{html.escape(str(unease.last_decay))}</div></div>
</div>
<div class="card">
  <h2>7 维度 Unease 分布</h2>
  <div class="bar-chart">
    {"".join(bars)}
  </div>
</div>
<div class="card">
  <h2>API</h2>
  <pre><a href="/api/unease">/api/unease</a></pre>
</div>
"""
        self._send_html(200, self._html_wrap("Unease 仪表盘", body, "unease"))

    def _serve_html_notifications(self) -> None:
        notifications = read_notifications(self.vault)
        notif_html = []
        for n in notifications:
            severity = n.get("severity", "info")
            ntype = n.get("type", "unknown")
            message = n.get("message", "")
            notif_html.append(f"""
<div class="notification {html.escape(severity)}">
  <strong>[{html.escape(ntype)}]</strong> {html.escape(message)}
  <br><small style="color:#6272a4;">severity: {html.escape(severity)} | read: {n.get('read', False)}</small>
</div>""")

        body = f"""
<div class="card">
  <h2>Owner 通知 ({len(notifications)} 条)</h2>
  {"".join(notif_html) if notif_html else "<p>暂无通知</p>"}
</div>
<div class="card">
  <h2>API</h2>
  <pre><a href="/api/notifications">/api/notifications</a></pre>
</div>
"""
        self._send_html(200, self._html_wrap("Owner 通知", body, "notifications"))

    def _serve_html_dreams(self) -> None:
        dream_log_dir = self.vault.root / "mortis-dream-log"
        dreams = []
        if dream_log_dir.exists():
            for level_dir in sorted(dream_log_dir.iterdir()):
                if not level_dir.is_dir():
                    continue
                for f in sorted(level_dir.glob("*.md"))[:20]:
                    level = level_dir.name
                    badge_cls = level if level in ("light", "medium", "deep") else "light"
                    dreams.append(f"""
<tr>
  <td><span class="badge {html.escape(badge_cls)}">{html.escape(level)}</span></td>
  <td><a href="/api/dreams">{html.escape(f.name)}</a></td>
  <td>{html.escape(str(f.relative_to(self.vault.root)))}</td>
</tr>""")

        body = f"""
<div class="card">
  <h2>Dream 日历 ({len(dreams)} 条)</h2>
  <table>
    <tr><th>级别</th><th>文件</th><th>路径</th></tr>
    {"".join(dreams) if dreams else "<tr><td colspan='3'>暂无 dream 记录</td></tr>"}
  </table>
</div>
<div class="card">
  <h2>API</h2>
  <pre><a href="/api/dreams">/api/dreams</a></pre>
</div>
"""
        self._send_html(200, self._html_wrap("Dream 日历", body, "dreams"))

    # ----- logging -----

    def log_message(self, format, *args) -> None:  # noqa: A002
        _logger.debug("web: " + format, *args)


def start_web_server(vault_path: str = "vault", port: int = 8765) -> HTTPServer:
    """启动 Web UI server。

    创建 HTTPServer 并绑定 vault 到 handler 类变量, 但**不阻塞** —
    由调用方 (cmd_web) 调 server.serve_forever() 决定何时开始服务。
    """
    vault = Vault(vault_path)
    MortisWebHandler.vault = vault
    server = HTTPServer(("0.0.0.0", port), MortisWebHandler)
    _logger.info("Web UI started on http://localhost:%d", port)
    return server


__all__ = ["MortisWebHandler", "start_web_server"]

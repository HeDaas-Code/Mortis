"""Test mortis.web.server — Web UI HTTP server (issue #52 #53 #54)。

验收:
- start_web_server 返回 HTTPServer 实例
- GET / → dashboard JSON (phase + unease_max + growth_count)
- GET /growths → growth 列表 JSON
- GET /growths/<rel_path> → growth 详情 JSON
- GET /unease → unease 状态 JSON
- GET /notifications → owner 通知列表 JSON
- GET /dreams → dream log 列表 JSON
- GET /unknown → 404

测试策略: 在后台线程启动 HTTPServer (port=0 让 OS 分配空闲端口),
主线程用 urllib.request 发 GET 请求, 测试结束 server.shutdown()。
"""

from __future__ import annotations

import json
import threading
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError

import pytest

from mortis.clock import ConsciousnessState
from mortis.growth.model import Dimension, DreamLevel, Growth
from mortis.steiner import UneaseState, save_unease
from mortis.vault import Vault
from mortis.web.notify import send_notification
from mortis.web.server import MortisWebHandler, start_web_server

# ============================================================
# helpers
# ============================================================


def _make_growth(
    gid: str = "test-growth-001",
    dimension: Dimension = Dimension.VALUES,
    confidence: float = 0.7,
    body: str = "测试 growth 正文",
) -> Growth:
    """构造一个 Growth dataclass。"""
    now = datetime.now(tz=timezone.utc).isoformat()
    return Growth(
        id=gid,
        dimension=dimension,
        confidence=confidence,
        created_at=now,
        last_validated=now,
        source_sessions=("session-0",),
        dream_level=DreamLevel.LIGHT,
        emotional_valence=0.3,
        emotional_arousal=0.5,
        tags=("test", "values"),
        body=body,
    )


def _write_dream_log(vault: Vault, level: str, filename: str) -> str:
    """直接写一个 dream log .md 文件到 mortis-dream-log/<level>/。"""
    rel = f"mortis-dream-log/{level}/{filename}"
    vault.write(rel, f"# Dream Log: {level}\n\n测试 dream log\n", whitelist=None)
    return rel


def _get_json(base_url: str, path: str) -> tuple[int, dict]:
    """发 GET 请求, 返回 (status_code, parsed_json)。"""
    url = base_url + path
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            status = resp.status
            body = resp.read().decode("utf-8")
    except HTTPError as e:
        status = e.code
        body = e.read().decode("utf-8")
    return status, json.loads(body)


# ============================================================
# fixtures
# ============================================================


@pytest.fixture
def vault(tmp_path: Path) -> Vault:
    """空 vault (tmp 目录)。"""
    return Vault(tmp_path)


@pytest.fixture
def server_url(vault: Vault):
    """启动 Web UI server (后台线程, port=0 自动分配空闲端口)。

    yield base_url (e.g. http://127.0.0.1:54321), 测试结束后 shutdown。
    """
    # 用 port=0 让 OS 分配空闲端口, 避免端口冲突
    server = start_web_server(vault_path=str(vault.root), port=0)
    actual_port = server.server_address[1]
    base_url = f"http://127.0.0.1:{actual_port}"

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield base_url

    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


# ============================================================
# start_web_server
# ============================================================


class TestStartWebServer:
    """start_web_server 返回 HTTPServer。"""

    def test_returns_http_server(self, vault: Vault) -> None:
        """start_web_server 返回 HTTPServer 实例 (不 serve_forever)。"""
        from http.server import HTTPServer
        server = start_web_server(vault_path=str(vault.root), port=0)
        assert isinstance(server, HTTPServer)
        # vault 已绑定到 handler 类变量
        assert MortisWebHandler.vault is not None
        assert MortisWebHandler.vault.root == vault.root
        server.server_close()

    def test_binds_to_specified_port(self, vault: Vault) -> None:
        """server 绑定到指定端口。"""
        # port=0 → OS 分配, server_address[1] > 0
        server = start_web_server(vault_path=str(vault.root), port=0)
        assert server.server_address[1] > 0
        server.server_close()


# ============================================================
# GET / (dashboard)
# ============================================================


class TestDashboard:
    """GET / → dashboard JSON。"""

    def test_dashboard_empty_vault(self, server_url: str) -> None:
        """空 vault → phase + unease_max=0 + growth_count=0。"""
        status, data = _get_json(server_url, "/")
        assert status == 200
        assert data["phase"] in {s.value for s in ConsciousnessState}
        assert data["unease_max"] == 0.0
        assert data["growth_count"] == 0
        assert "/growths" in data["endpoints"]
        assert "/unease" in data["endpoints"]
        assert "/notifications" in data["endpoints"]
        assert "/dreams" in data["endpoints"]

    def test_dashboard_with_growth(self, vault: Vault, server_url: str) -> None:
        """有 growth → growth_count=1。"""
        vault.write_growth(_make_growth())
        status, data = _get_json(server_url, "/")
        assert status == 200
        assert data["growth_count"] == 1

    def test_dashboard_with_unease(self, vault: Vault, server_url: str) -> None:
        """有 unease → unease_max 反映最大值。"""
        from dataclasses import replace
        state = replace(
            UneaseState(),
            per_dimension={
                **UneaseState().per_dimension,
                Dimension.IDENTITY: 0.45,
            },
        )
        save_unease(vault, state)
        status, data = _get_json(server_url, "/")
        assert status == 200
        assert data["unease_max"] == 0.45


# ============================================================
# GET /growths
# ============================================================


class TestGrowths:
    """GET /growths → growth 列表。"""

    def test_growths_empty(self, server_url: str) -> None:
        """空 vault → 空列表, total=0。"""
        status, data = _get_json(server_url, "/growths")
        assert status == 200
        assert data["growths"] == []
        assert data["total"] == 0

    def test_growths_with_one(self, vault: Vault, server_url: str) -> None:
        """有 1 条 growth → 列表含 1 条预览。"""
        vault.write_growth(_make_growth(body="这是 growth 正文内容"))
        status, data = _get_json(server_url, "/growths")
        assert status == 200
        assert data["total"] == 1
        assert len(data["growths"]) == 1
        g = data["growths"][0]
        assert g["id"] == "test-growth-001"
        assert g["dimension"] == "values"
        assert g["confidence"] == 0.7
        assert g["body_preview"].startswith("这是 growth")
        assert "test" in g["tags"]
        assert g["rel_path"].startswith("mortis-growth/")

    def test_growths_multiple(self, vault: Vault, server_url: str) -> None:
        """多条 growth → 全部列出。"""
        vault.write_growth(_make_growth(gid="g-001"))
        vault.write_growth(_make_growth(gid="g-002", dimension=Dimension.TONE))
        status, data = _get_json(server_url, "/growths")
        assert status == 200
        assert data["total"] == 2
        assert len(data["growths"]) == 2


# ============================================================
# GET /growths/<rel_path>
# ============================================================


class TestGrowthDetail:
    """GET /growths/<rel_path> → growth 详情。"""

    def test_growth_detail_found(self, vault: Vault, server_url: str) -> None:
        """存在的 growth → 返回完整详情。"""
        vault.write_growth(_make_growth(body="完整正文"))
        # 先拿 rel_path
        _, list_data = _get_json(server_url, "/growths")
        rel_path = list_data["growths"][0]["rel_path"]
        status, data = _get_json(server_url, f"/growths/{rel_path}")
        assert status == 200
        assert data["id"] == "test-growth-001"
        assert data["dimension"] == "values"
        assert data["confidence"] == 0.7
        assert data["body"] == "完整正文"
        assert data["dream_level"] == "light"
        assert data["emotional_valence"] == 0.3
        assert data["emotional_arousal"] == 0.5
        assert "session-0" in data["source_sessions"]

    def test_growth_detail_not_found(self, server_url: str) -> None:
        """不存在的 growth → 404。"""
        status, data = _get_json(server_url, "/growths/mortis-growth/values/nope.md")
        assert status == 404
        assert "error" in data


# ============================================================
# GET /unease
# ============================================================


class TestUnease:
    """GET /unease → unease 状态。"""

    def test_unease_empty(self, server_url: str) -> None:
        """空 vault → max_unease=0, 7 维度全 0。"""
        status, data = _get_json(server_url, "/unease")
        assert status == 200
        assert data["max_unease"] == 0.0
        assert len(data["per_dimension"]) == 7
        for dim in ("identity", "values", "tone", "agency", "relations",
                    "creativity", "mortality"):
            assert dim in data["per_dimension"]
            assert data["per_dimension"][dim] == 0.0
        assert "last_decay" in data

    def test_unease_with_values(self, vault: Vault, server_url: str) -> None:
        """有 unease → per_dimension 反映各维度值。"""
        from dataclasses import replace
        state = replace(
            UneaseState(),
            per_dimension={
                **UneaseState().per_dimension,
                Dimension.IDENTITY: 0.45,
                Dimension.VALUES: 0.82,
            },
        )
        save_unease(vault, state)
        status, data = _get_json(server_url, "/unease")
        assert status == 200
        assert data["max_unease"] == 0.82
        assert data["per_dimension"]["identity"] == 0.45
        assert data["per_dimension"]["values"] == 0.82


# ============================================================
# GET /notifications
# ============================================================


class TestNotifications:
    """GET /notifications → owner 通知列表。"""

    def test_notifications_empty(self, server_url: str) -> None:
        """无通知 → 空列表。"""
        status, data = _get_json(server_url, "/notifications")
        assert status == 200
        assert data["notifications"] == []

    def test_notifications_with_one(self, vault: Vault, server_url: str) -> None:
        """有 1 条通知 → 列表含 1 条。"""
        send_notification(vault, "drift", "identity drift 0.82", severity="warning")
        status, data = _get_json(server_url, "/notifications")
        assert status == 200
        assert len(data["notifications"]) == 1
        n = data["notifications"][0]
        assert n["type"] == "drift"
        assert n["message"] == "identity drift 0.82"
        assert n["severity"] == "warning"
        assert n["read"] is False

    def test_notifications_multiple(self, vault: Vault, server_url: str) -> None:
        """多条通知 → 全部返回。"""
        send_notification(vault, "drift", "msg1")
        send_notification(vault, "unease", "msg2")
        send_notification(vault, "dream", "msg3")
        status, data = _get_json(server_url, "/notifications")
        assert status == 200
        assert len(data["notifications"]) == 3


# ============================================================
# GET /dreams
# ============================================================


class TestDreams:
    """GET /dreams → dream log 列表。"""

    def test_dreams_empty(self, server_url: str) -> None:
        """无 dream log → 空列表。"""
        status, data = _get_json(server_url, "/dreams")
        assert status == 200
        assert data["dreams"] == []

    def test_dreams_with_one(self, vault: Vault, server_url: str) -> None:
        """有 1 条 dream log → 列表含 1 条。"""
        _write_dream_log(vault, "light", "2026-06-22-light.md")
        status, data = _get_json(server_url, "/dreams")
        assert status == 200
        assert len(data["dreams"]) == 1
        d = data["dreams"][0]
        assert d["level"] == "light"
        assert d["file"] == "2026-06-22-light.md"
        assert d["rel_path"] == "mortis-dream-log/light/2026-06-22-light.md"

    def test_dreams_multiple_levels(self, vault: Vault, server_url: str) -> None:
        """多个 level 的 dream log → 按 level 分组返回。"""
        _write_dream_log(vault, "light", "2026-06-22-light.md")
        _write_dream_log(vault, "medium", "2026-06-22-medium.md")
        _write_dream_log(vault, "deep", "2026-06-22-deep.md")
        status, data = _get_json(server_url, "/dreams")
        assert status == 200
        assert len(data["dreams"]) == 3
        levels = {d["level"] for d in data["dreams"]}
        assert levels == {"light", "medium", "deep"}


# ============================================================
# GET /unknown (404)
# ============================================================


class TestNotFound:
    """未知路由 → 404。"""

    def test_unknown_path_404(self, server_url: str) -> None:
        """未知路径 → 404 + error。"""
        status, data = _get_json(server_url, "/nonexistent")
        assert status == 404
        assert data["error"] == "not found"

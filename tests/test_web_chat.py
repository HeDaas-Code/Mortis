"""Test mortis.web.chat + 对话 HTTP 端点 + HTML 对话页面 (issue #88)。

验收:
- ChatService: create_conversation / send / stream / list / get_history / delete
- POST /api/chat → JSON 响应
- POST /api/chat/stream → SSE 流式响应
- GET /api/conversations → 对话列表 JSON
- GET /api/conversations/<cid> → 对话历史 JSON
- DELETE /api/conversations/<cid> → 删除
- GET /chat → OpenUI 风格 HTML 对话页面
- 未配置 chat_service 时 /chat 显示「未启用」提示

测试策略: MockProvider (不调外部 LLM), tmp vault, 后台线程 HTTPServer。
"""

from __future__ import annotations

import json
import tempfile
import threading
import urllib.request
from pathlib import Path
from urllib.error import HTTPError

import pytest

from mortis.memory import Session
from mortis.provider import MockProvider
from mortis.runtime import MasterRuntime
from mortis.seed import Seed
from mortis.vault import Vault
from mortis.web.chat import ChatService
from mortis.web.server import MortisWebHandler, start_web_server


# ============================================================
# helpers
# ============================================================


def _make_seed() -> Seed:
    return Seed(
        identity="test", values="v", tone="简短。不注水。",
        agency="a", relations="r", creativity="c", mortality="m",
    )


def _make_master(vault: Vault, responses: list[str] | None = None) -> MasterRuntime:
    return MasterRuntime(
        seed=_make_seed(),
        vault=vault,
        provider=MockProvider(responses=responses),
        session=Session(session_id="test-chat-session"),
    )


def _get_json(base_url: str, path: str) -> tuple[int, dict]:
    url = base_url + path
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def _get_html(base_url: str, path: str) -> tuple[int, str]:
    url = base_url + path
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, resp.read().decode("utf-8")
    except HTTPError as e:
        return e.code, e.read().decode("utf-8")


def _post_json(base_url: str, path: str, body: dict) -> tuple[int, dict]:
    url = base_url + path
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def _post_stream(base_url: str, path: str, body: dict) -> tuple[int, str]:
    """POST SSE 端点, 返回 (status, raw_text)。"""
    url = base_url + path
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8")
    except HTTPError as e:
        return e.code, e.read().decode("utf-8")


def _delete(base_url: str, path: str) -> tuple[int, dict]:
    url = base_url + path
    req = urllib.request.Request(url, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


# ============================================================
# fixtures
# ============================================================


@pytest.fixture
def vault(tmp_path: Path) -> Vault:
    return Vault(tmp_path)


@pytest.fixture
def chat_service(vault: Vault) -> ChatService:
    master = _make_master(vault, responses=["你好，我是 Mortis", "继续聊"])
    return ChatService(master)


@pytest.fixture
def server_url_no_chat(vault: Vault):
    """无 chat_service 的 server (对话未启用)。"""
    server = start_web_server(vault_path=str(vault.root), port=0)
    port = server.server_address[1]
    base_url = f"http://127.0.0.1:{port}"
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield base_url
    server.shutdown()
    server.server_close()
    t.join(timeout=5)


@pytest.fixture
def server_url_chat(vault: Vault, chat_service: ChatService):
    """带 chat_service 的 server。"""
    server = start_web_server(
        vault_path=str(vault.root), port=0, chat_service=chat_service,
    )
    port = server.server_address[1]
    base_url = f"http://127.0.0.1:{port}"
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield base_url
    server.shutdown()
    server.server_close()
    t.join(timeout=5)


# ============================================================
# ChatService 单元测试
# ============================================================


class TestChatServiceUnit:
    """ChatService 直接调用 (不经 HTTP)。"""

    def test_create_conversation(self, chat_service: ChatService) -> None:
        conv = chat_service.create_conversation()
        assert conv.conversation_id.startswith("conv-")
        assert conv.messages == []
        assert conv.title == ""

    def test_send_returns_response(self, chat_service: ChatService) -> None:
        resp = chat_service.send("你好")
        assert resp.conversation_id.startswith("conv-")
        assert "Mortis" in resp.message or "mock" in resp.message
        assert resp.role == "assistant"

    def test_send_creates_conversation_if_none(self, chat_service: ChatService) -> None:
        resp = chat_service.send("第一条消息")
        cid = resp.conversation_id
        assert cid is not None
        # 第二条消息复用同一对话
        resp2 = chat_service.send("第二条", conversation_id=cid)
        assert resp2.conversation_id == cid

    def test_send_multi_turn_history(self, chat_service: ChatService) -> None:
        """多轮对话 → 历史累积。"""
        cid = chat_service.send("第一回合").conversation_id
        chat_service.send("第二回合", conversation_id=cid)
        history = chat_service.get_history(cid)
        assert history is not None
        # 2 轮 = 4 条消息 (user + assistant 各 2)
        assert len(history) == 4
        roles = [m["role"] for m in history]
        assert roles == ["user", "assistant", "user", "assistant"]

    def test_send_sets_title_from_first_message(self, chat_service: ChatService) -> None:
        cid = chat_service.send("这是第一条很长的消息内容").conversation_id
        conv = chat_service.get_conversation(cid)
        assert conv is not None
        assert conv.title == "这是第一条很长的消息内容"

    def test_stream_yields_chunks(self, chat_service: ChatService) -> None:
        from mortis.provider import StreamChunk
        chunks = list(chat_service.stream("流式测试"))
        assert len(chunks) > 0
        assert all(isinstance(c, StreamChunk) for c in chunks)
        # 最后一块有 finish_reason
        assert chunks[-1].finish_reason == "stop"
        # 完整内容拼起来非空
        full = "".join(c.delta for c in chunks)
        assert len(full) > 0

    def test_stream_persists_to_history(self, chat_service: ChatService) -> None:
        cid = None
        for chunk in chat_service.stream("流式消息"):
            pass
        # 流式结束后, 对话历史应有 2 条消息
        convs = chat_service.list_conversations()
        assert len(convs) == 1
        cid = convs[0]["conversation_id"]
        history = chat_service.get_history(cid)
        assert history is not None
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"

    def test_list_conversations(self, chat_service: ChatService) -> None:
        chat_service.send("对话 A")
        chat_service.send("对话 B")
        convs = chat_service.list_conversations()
        assert len(convs) == 2
        for c in convs:
            assert "conversation_id" in c
            assert "title" in c
            assert "message_count" in c

    def test_delete_conversation(self, chat_service: ChatService) -> None:
        cid = chat_service.send("待删除").conversation_id
        assert chat_service.delete_conversation(cid) is True
        assert chat_service.get_conversation(cid) is None
        # 再删一次 → False
        assert chat_service.delete_conversation(cid) is False

    def test_get_history_nonexistent(self, chat_service: ChatService) -> None:
        assert chat_service.get_history("nonexistent-cid") is None

    def test_persistence_across_instances(self, vault: Vault) -> None:
        """对话持久化到磁盘 → 新 ChatService 实例能加载。"""
        master1 = _make_master(vault, responses=["第一次回复"])
        svc1 = ChatService(master1)
        cid = svc1.send("持久化测试").conversation_id

        # 新实例, 同 vault
        master2 = _make_master(vault, responses=["第二次回复"])
        svc2 = ChatService(master2)
        history = svc2.get_history(cid)
        assert history is not None
        assert len(history) == 2
        assert history[0]["content"] == "持久化测试"
        assert history[1]["content"] == "第一次回复"


# ============================================================
# POST /api/chat (非流式)
# ============================================================


class TestChatApiSend:
    """POST /api/chat → JSON 响应。"""

    def test_send_returns_json(self, server_url_chat: str) -> None:
        status, data = _post_json(server_url_chat, "/api/chat", {"message": "你好"})
        assert status == 200
        assert data["conversation_id"].startswith("conv-")
        assert "message" in data
        assert data["role"] == "assistant"
        assert data["elapsed_sec"] >= 0

    def test_send_continues_conversation(self, server_url_chat: str) -> None:
        _, data1 = _post_json(server_url_chat, "/api/chat", {"message": "第一回合"})
        cid = data1["conversation_id"]
        _, data2 = _post_json(server_url_chat, "/api/chat", {
            "message": "第二回合", "conversation_id": cid,
        })
        assert data2["conversation_id"] == cid

    def test_send_empty_message_400(self, server_url_chat: str) -> None:
        status, data = _post_json(server_url_chat, "/api/chat", {"message": ""})
        assert status == 400
        assert "required" in data["error"]

    def test_send_no_message_400(self, server_url_chat: str) -> None:
        status, data = _post_json(server_url_chat, "/api/chat", {})
        assert status == 400

    def test_send_invalid_json_400(self, server_url_chat: str) -> None:
        url = server_url_chat + "/api/chat"
        req = urllib.request.Request(
            url, data=b"not json", method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                status = resp.status
                body = resp.read().decode("utf-8")
        except HTTPError as e:
            status = e.code
            body = e.read().decode("utf-8")
        assert status == 400
        assert "invalid JSON" in json.loads(body)["error"]


# ============================================================
# POST /api/chat/stream (SSE 流式)
# ============================================================


class TestChatApiStream:
    """POST /api/chat/stream → SSE 流式响应。"""

    def test_stream_returns_sse(self, server_url_chat: str) -> None:
        status, body = _post_stream(server_url_chat, "/api/chat/stream", {
            "message": "流式你好",
        })
        assert status == 200
        # SSE 格式: data: {...}\n\n
        assert "data: " in body
        # 至少有一个 chunk + 一个结束块
        lines = [l for l in body.split("\n\n") if l.startswith("data: ")]
        assert len(lines) >= 1
        # 解析第一个 data 块
        first = json.loads(lines[0][len("data: "):])
        assert "delta" in first
        assert "conversation_id" in first

    def test_stream_has_done_marker(self, server_url_chat: str) -> None:
        status, body = _post_stream(server_url_chat, "/api/chat/stream", {
            "message": "测试结束标记",
        })
        assert status == 200
        chunks = [l for l in body.split("\n\n") if l.startswith("data: ")]
        last = json.loads(chunks[-1][len("data: "):])
        assert last.get("done") is True
        assert last.get("finish_reason") == "stop"

    def test_stream_continues_conversation(self, server_url_chat: str) -> None:
        _, body = _post_stream(server_url_chat, "/api/chat/stream", {
            "message": "第一回合流式",
        })
        chunks = [l for l in body.split("\n\n") if l.startswith("data: ")]
        first = json.loads(chunks[0][len("data: "):])
        cid = first["conversation_id"]
        # 第二轮带 cid
        _, body2 = _post_stream(server_url_chat, "/api/chat/stream", {
            "message": "第二回合", "conversation_id": cid,
        })
        chunks2 = [l for l in body2.split("\n\n") if l.startswith("data: ")]
        first2 = json.loads(chunks2[0][len("data: "):])
        assert first2["conversation_id"] == cid


# ============================================================
# GET /api/conversations
# ============================================================


class TestConversationsApi:
    """GET /api/conversations + GET /api/conversations/<cid> + DELETE。"""

    def test_list_empty(self, server_url_chat: str) -> None:
        status, data = _get_json(server_url_chat, "/api/conversations")
        assert status == 200
        assert data["conversations"] == []
        assert data["total"] == 0

    def test_list_after_send(self, server_url_chat: str) -> None:
        _post_json(server_url_chat, "/api/chat", {"message": "对话一"})
        _post_json(server_url_chat, "/api/chat", {"message": "对话二"})
        status, data = _get_json(server_url_chat, "/api/conversations")
        assert status == 200
        assert data["total"] == 2

    def test_get_history(self, server_url_chat: str) -> None:
        _, send_data = _post_json(server_url_chat, "/api/chat", {"message": "历史测试"})
        cid = send_data["conversation_id"]
        status, data = _get_json(server_url_chat, f"/api/conversations/{cid}")
        assert status == 200
        assert data["conversation_id"] == cid
        assert data["message_count"] == 2
        assert data["messages"][0]["role"] == "user"
        assert data["messages"][1]["role"] == "assistant"

    def test_get_history_not_found(self, server_url_chat: str) -> None:
        status, data = _get_json(server_url_chat, "/api/conversations/nonexistent")
        assert status == 404
        assert "not found" in data["error"]

    def test_delete_conversation(self, server_url_chat: str) -> None:
        _, send_data = _post_json(server_url_chat, "/api/chat", {"message": "待删"})
        cid = send_data["conversation_id"]
        status, data = _delete(server_url_chat, f"/api/conversations/{cid}")
        assert status == 200
        assert data["deleted"] is True
        # 再查 → 404
        status2, _ = _get_json(server_url_chat, f"/api/conversations/{cid}")
        assert status2 == 404


# ============================================================
# GET /chat (HTML 对话页面)
# ============================================================


class TestChatHtmlPage:
    """GET /chat → OpenUI 风格 HTML 页面。"""

    def test_chat_html_enabled(self, server_url_chat: str) -> None:
        """chat_service 启用时 /chat 返回完整对话 UI。"""
        status, body = _get_html(server_url_chat, "/chat")
        assert status == 200
        assert "<!DOCTYPE html>" in body
        # OpenUI 风格元素
        assert "chat-layout" in body
        assert "chat-sidebar" in body
        assert "chat-messages" in body
        assert "chat-input" in body
        assert "chat-send" in body
        # JS 交互函数
        assert "sendMessage" in body
        assert "newConversation" in body
        assert "refreshConversations" in body
        # 导航栏含对话入口
        assert 'href="/chat"' in body

    def test_chat_html_disabled_shows_notice(self, server_url_no_chat: str) -> None:
        """未配置 chat_service 时 /chat 显示「未启用」提示。"""
        status, body = _get_html(server_url_no_chat, "/chat")
        assert status == 200
        assert "对话服务未启用" in body

    def test_chat_html_nav_active(self, server_url_chat: str) -> None:
        """对话页 nav 标记为 active。"""
        _, body = _get_html(server_url_chat, "/chat")
        assert 'class="active"' in body


# ============================================================
# 未配置 chat_service 时 API 返回 503
# ============================================================


class TestChatServiceNotConfigured:
    """未配置 chat_service 时, 对话 API 返回 503。"""

    def test_send_returns_503(self, server_url_no_chat: str) -> None:
        status, data = _post_json(server_url_no_chat, "/api/chat", {"message": "x"})
        assert status == 503
        assert "not configured" in data["error"]

    def test_conversations_returns_503(self, server_url_no_chat: str) -> None:
        status, data = _get_json(server_url_no_chat, "/api/conversations")
        assert status == 503

    def test_stream_returns_503(self, server_url_no_chat: str) -> None:
        status, body = _post_stream(server_url_no_chat, "/api/chat/stream", {
            "message": "x",
        })
        assert status == 503

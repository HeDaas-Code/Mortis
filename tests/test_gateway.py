"""Test mortis.gateway — 渠道抽象 + Gateway 路由 + WebChannel (issue #89)。

验收:
- InboundMessage / OutboundMessage 数据结构
- Channel 协议 (WebChannel 实现)
- 注册表 register_channel / get_channel / list_channels
- Gateway.handle_inbound → ChatService.send → OutboundMessage
- Gateway.handle_inbound_stream → 流式
- sender → conversation_id 映射 (跨轮次复用)
- channel.send 被调用 (用 spy 渠道验证)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mortis.gateway import (
    Channel,
    Gateway,
    InboundMessage,
    OutboundMessage,
    WebChannel,
    get_channel,
    list_channels,
    register_channel,
)
from mortis.memory import Session
from mortis.provider import MockProvider, StreamChunk
from mortis.runtime import MasterRuntime
from mortis.seed import Seed
from mortis.vault import Vault
from mortis.web.chat import ChatService


# ============================================================
# helpers
# ============================================================


def _make_master(vault: Vault, responses: list[str] | None = None) -> MasterRuntime:
    return MasterRuntime(
        seed=Seed(
            identity="test", values="v", tone="简短",
            agency="a", relations="r", creativity="c", mortality="m",
        ),
        vault=vault,
        provider=MockProvider(responses=responses),
        session=Session(session_id="test-gw-session"),
    )


class SpyChannel:
    """记录 send 调用的测试渠道。"""

    name = "spy"

    def __init__(self) -> None:
        self.sent: list[OutboundMessage] = []
        self.started = False
        self.stopped = False

    def send(self, outbound: OutboundMessage) -> None:
        self.sent.append(outbound)

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True


# ============================================================
# fixtures
# ============================================================


@pytest.fixture
def vault(tmp_path: Path) -> Vault:
    return Vault(tmp_path)


@pytest.fixture
def chat_service(vault: Vault) -> ChatService:
    return ChatService(_make_master(vault, responses=["回复一", "回复二", "回复三"]))


@pytest.fixture
def gateway(chat_service: ChatService) -> Gateway:
    return Gateway(chat_service)


# ============================================================
# 消息数据结构
# ============================================================


class TestMessageTypes:
    """InboundMessage / OutboundMessage 数据结构。"""

    def test_inbound_defaults(self) -> None:
        msg = InboundMessage(channel="web", sender_id="u1", content="hello")
        assert msg.channel == "web"
        assert msg.sender_id == "u1"
        assert msg.content == "hello"
        assert msg.conversation_id is None
        assert msg.timestamp  # 自动生成
        assert msg.metadata == {}

    def test_inbound_with_metadata(self) -> None:
        msg = InboundMessage(
            channel="telegram", sender_id="123", content="hi",
            metadata={"message_id": 42, "chat_type": "private"},
        )
        assert msg.metadata["message_id"] == 42

    def test_outbound_fields(self) -> None:
        out = OutboundMessage(
            channel="web", recipient_id="u1", content="reply",
            conversation_id="conv-1",
        )
        assert out.channel == "web"
        assert out.recipient_id == "u1"
        assert out.content == "reply"
        assert out.conversation_id == "conv-1"
        assert out.timestamp


# ============================================================
# WebChannel
# ============================================================


class TestWebChannel:
    """WebChannel — 被动渠道, send/start/stop 都是 no-op。"""

    def test_name(self) -> None:
        assert WebChannel().name == "web"

    def test_send_is_noop(self) -> None:
        ch = WebChannel()
        out = OutboundMessage(
            channel="web", recipient_id="u1", content="x", conversation_id="c1",
        )
        # 不抛异常即可
        ch.send(out)

    def test_start_stop_noop(self) -> None:
        ch = WebChannel()
        ch.start()
        ch.stop()

    def test_satisfies_channel_protocol(self) -> None:
        """WebChannel 满足 Channel 协议。"""
        assert isinstance(WebChannel(), Channel)


# ============================================================
# 注册表
# ============================================================


class TestRegistry:
    """register_channel / get_channel / list_channels。"""

    def test_web_auto_registered(self) -> None:
        names = list_channels()
        assert "web" in names

    def test_get_channel_web(self) -> None:
        factory = get_channel("web")
        ch = factory()
        assert ch.name == "web"

    def test_get_channel_unknown_raises(self) -> None:
        with pytest.raises(KeyError, match="not registered"):
            get_channel("nonexistent")

    def test_register_custom_channel(self) -> None:
        register_channel("test-spy", SpyChannel)
        assert "test-spy" in list_channels()
        ch = get_channel("test-spy")()
        assert ch.name == "spy"


# ============================================================
# Gateway 路由
# ============================================================


class TestGatewayRouting:
    """Gateway.handle_inbound → ChatService → OutboundMessage。"""

    def test_handle_inbound_returns_outbound(self, gateway: Gateway) -> None:
        msg = InboundMessage(channel="web", sender_id="user-1", content="你好")
        out = gateway.handle_inbound(msg)
        assert out.channel == "web"
        assert out.recipient_id == "user-1"
        assert out.content  # 非空
        assert out.conversation_id.startswith("conv-")

    def test_sender_mapping_reuses_conversation(self, gateway: Gateway) -> None:
        """同一 sender 多轮 → 复用同一 conversation_id。"""
        msg1 = InboundMessage(channel="web", sender_id="alice", content="第一轮")
        out1 = gateway.handle_inbound(msg1)
        msg2 = InboundMessage(channel="web", sender_id="alice", content="第二轮")
        out2 = gateway.handle_inbound(msg2)
        assert out1.conversation_id == out2.conversation_id

    def test_different_senders_different_conversations(
        self, gateway: Gateway
    ) -> None:
        """不同 sender → 不同 conversation_id。"""
        out1 = gateway.handle_inbound(
            InboundMessage(channel="web", sender_id="alice", content="hi")
        )
        out2 = gateway.handle_inbound(
            InboundMessage(channel="web", sender_id="bob", content="hi")
        )
        assert out1.conversation_id != out2.conversation_id

    def test_explicit_conversation_id_overrides_mapping(
        self, gateway: Gateway
    ) -> None:
        """msg.conversation_id 优先于 sender 映射。"""
        out1 = gateway.handle_inbound(
            InboundMessage(channel="web", sender_id="alice", content="第一轮")
        )
        cid = out1.conversation_id
        # bob 显式指定 alice 的 conversation_id
        out2 = gateway.handle_inbound(
            InboundMessage(
                channel="web", sender_id="bob", content="加入对话",
                conversation_id=cid,
            )
        )
        assert out2.conversation_id == cid

    def test_channel_send_called(self, chat_service: ChatService) -> None:
        """Gateway 调 channel.send 推送回复。"""
        gw = Gateway(chat_service)
        spy = SpyChannel()
        gw.register_channel(spy)
        out = gw.handle_inbound(
            InboundMessage(channel="spy", sender_id="u1", content="hi")
        )
        assert len(spy.sent) == 1
        assert spy.sent[0].content == out.content
        assert spy.sent[0].recipient_id == "u1"

    def test_unknown_channel_still_returns_response(self, gateway: Gateway) -> None:
        """消息来自未注册渠道 → 仍返回回复 (只是不推送)。"""
        out = gateway.handle_inbound(
            InboundMessage(channel="unknown", sender_id="u1", content="hi")
        )
        assert out.content

    def test_register_and_list_channels(self, gateway: Gateway) -> None:
        gateway.register_channel(WebChannel())
        gateway.register_channel(SpyChannel())
        names = gateway.list_channels()
        assert "web" in names
        assert "spy" in names

    def test_start_all_stop_all(self, gateway: Gateway) -> None:
        spy = SpyChannel()
        gateway.register_channel(spy)
        gateway.start_all()
        assert spy.started is True
        gateway.stop_all()
        assert spy.stopped is True


# ============================================================
# Gateway 流式
# ============================================================


class TestGatewayStream:
    """Gateway.handle_inbound_stream → (cid, generator)。"""

    def test_stream_returns_cid_and_generator(
        self, gateway: Gateway
    ) -> None:
        msg = InboundMessage(channel="web", sender_id="u1", content="流式")
        cid, gen = gateway.handle_inbound_stream(msg)
        assert cid.startswith("conv-")
        chunks = list(gen)
        assert len(chunks) > 0
        assert all(isinstance(c, StreamChunk) for c in chunks)

    def test_stream_sender_mapping(self, gateway: Gateway) -> None:
        """流式也维护 sender → conversation 映射。"""
        msg1 = InboundMessage(channel="web", sender_id="alice", content="第一轮")
        cid1, _ = gateway.handle_inbound_stream(msg1)
        # 第二轮不传 cid, 应复用
        msg2 = InboundMessage(channel="web", sender_id="alice", content="第二轮")
        cid2, gen2 = gateway.handle_inbound_stream(msg2)
        assert cid2 == cid1
        list(gen2)  # 消费以触发持久化


# ============================================================
# 端到端: 多渠道同时工作
# ============================================================


class TestMultiChannel:
    """多个渠道同时接入 Gateway, 各自独立对话。"""

    def test_web_and_spy_isolated(self, chat_service: ChatService) -> None:
        gw = Gateway(chat_service)
        spy = SpyChannel()
        gw.register_channel(WebChannel())
        gw.register_channel(spy)

        # web 用户
        web_out = gw.handle_inbound(
            InboundMessage(channel="web", sender_id="alice", content="来自 web")
        )
        # spy 用户
        spy_out = gw.handle_inbound(
            InboundMessage(channel="spy", sender_id="bob", content="来自 spy")
        )

        # 不同渠道 + 不同 sender → 不同对话
        assert web_out.conversation_id != spy_out.conversation_id
        # spy 渠道收到推送, web 没有 (web send 是 no-op, 但也调了)
        assert len(spy.sent) == 1

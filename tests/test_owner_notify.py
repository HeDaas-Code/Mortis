"""Test mortis.web.notify — owner 通知通道 (issue #54)。

验收:
- send_notification 写入 mortis-subconscious/owner-notify.json
- read_notifications 读取通知列表
- mark_read 标记通知为已读
- 通知上限 100 条 (FIFO 截断旧通知)
- 文件损坏 / 不存在 → 静默返回空列表
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mortis.vault import Vault
from mortis.web.notify import (
    NOTIFY_FILE,
    NOTIFY_MAX,
    NOTIFY_SUBDIR,
    mark_read,
    read_notifications,
    send_notification,
)

# ============================================================
# fixtures
# ============================================================


@pytest.fixture
def vault(tmp_path: Path) -> Vault:
    """空 vault (tmp 目录)。"""
    return Vault(tmp_path)


def _notify_path(vault: Vault) -> Path:
    """通知文件绝对路径。"""
    return vault.root / NOTIFY_SUBDIR / NOTIFY_FILE


# ============================================================
# send_notification
# ============================================================


class TestSendNotification:
    """send_notification 行为。"""

    def test_send_creates_file(self, vault: Vault) -> None:
        """send_notification 第一次调用 → 创建 owner-notify.json。"""
        send_notification(vault, "drift", "identity drift 0.82", severity="warning")
        assert _notify_path(vault).exists()

    def test_send_writes_valid_json_list(self, vault: Vault) -> None:
        """通知文件是合法 JSON list。"""
        send_notification(vault, "unease", "values unease high")
        data = json.loads(_notify_path(vault).read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) == 1

    def test_send_notification_structure(self, vault: Vault) -> None:
        """单条通知结构完整 (type/message/severity/timestamp/read)。"""
        send_notification(vault, "dream", "deep dream done", severity="info")
        notifs = read_notifications(vault)
        assert len(notifs) == 1
        n = notifs[0]
        assert n["type"] == "dream"
        assert n["message"] == "deep dream done"
        assert n["severity"] == "info"
        assert "timestamp" in n
        assert n["read"] is False

    def test_send_appends_multiple(self, vault: Vault) -> None:
        """多次 send → append 到同一列表。"""
        send_notification(vault, "drift", "msg1")
        send_notification(vault, "unease", "msg2")
        send_notification(vault, "dream", "msg3")
        notifs = read_notifications(vault)
        assert len(notifs) == 3
        assert notifs[0]["message"] == "msg1"
        assert notifs[2]["message"] == "msg3"

    def test_send_default_severity_info(self, vault: Vault) -> None:
        """不传 severity → 默认 info。"""
        send_notification(vault, "drift", "msg")
        notifs = read_notifications(vault)
        assert notifs[0]["severity"] == "info"

    def test_send_creates_subdir(self, vault: Vault) -> None:
        """mortis-subconscious/ 子目录不存在时自动创建。"""
        # 确保子目录不存在
        assert not (vault.root / NOTIFY_SUBDIR).exists()
        send_notification(vault, "drift", "msg")
        assert (vault.root / NOTIFY_SUBDIR).exists()


# ============================================================
# read_notifications
# ============================================================


class TestReadNotifications:
    """read_notifications 行为。"""

    def test_read_returns_empty_when_no_file(self, vault: Vault) -> None:
        """文件不存在 → 返回空列表。"""
        assert read_notifications(vault) == []

    def test_read_returns_list(self, vault: Vault) -> None:
        """读取已写入的通知列表。"""
        send_notification(vault, "drift", "msg1")
        send_notification(vault, "unease", "msg2")
        notifs = read_notifications(vault)
        assert len(notifs) == 2
        assert notifs[0]["type"] == "drift"
        assert notifs[1]["type"] == "unease"

    def test_read_handles_corrupted_json(self, vault: Vault) -> None:
        """JSON 损坏 → 返回空列表 (不抛错)。"""
        notify_path = _notify_path(vault)
        notify_path.parent.mkdir(parents=True, exist_ok=True)
        notify_path.write_text("{ not valid json", encoding="utf-8")
        assert read_notifications(vault) == []

    def test_read_handles_non_list_json(self, vault: Vault) -> None:
        """JSON 是 dict 而非 list → 返回空列表。"""
        notify_path = _notify_path(vault)
        notify_path.parent.mkdir(parents=True, exist_ok=True)
        notify_path.write_text('{"key": "value"}', encoding="utf-8")
        assert read_notifications(vault) == []


# ============================================================
# mark_read
# ============================================================


class TestMarkRead:
    """mark_read 行为。"""

    def test_mark_read_success(self, vault: Vault) -> None:
        """合法 index → 标记已读, 返回 True。"""
        send_notification(vault, "drift", "msg1")
        send_notification(vault, "unease", "msg2")
        result = mark_read(vault, 0)
        assert result is True
        notifs = read_notifications(vault)
        assert notifs[0]["read"] is True
        assert notifs[1]["read"] is False

    def test_mark_read_second_notification(self, vault: Vault) -> None:
        """标记第二条 (index=1)。"""
        send_notification(vault, "drift", "msg1")
        send_notification(vault, "unease", "msg2")
        result = mark_read(vault, 1)
        assert result is True
        notifs = read_notifications(vault)
        assert notifs[0]["read"] is False
        assert notifs[1]["read"] is True

    def test_mark_read_out_of_range_negative(self, vault: Vault) -> None:
        """负 index → 返回 False, 不抛异常。"""
        send_notification(vault, "drift", "msg1")
        result = mark_read(vault, -1)
        assert result is False

    def test_mark_read_out_of_range_positive(self, vault: Vault) -> None:
        """超出长度 index → 返回 False。"""
        send_notification(vault, "drift", "msg1")
        result = mark_read(vault, 10)
        assert result is False

    def test_mark_read_empty_list(self, vault: Vault) -> None:
        """空列表 → 任何 index 都返回 False。"""
        result = mark_read(vault, 0)
        assert result is False


# ============================================================
# 通知上限 100 条
# ============================================================


class TestNotificationCap:
    """通知上限 NOTIFY_MAX=100 (FIFO 截断)。"""

    def test_cap_at_100(self, vault: Vault) -> None:
        """发送 150 条 → 只保留最近 100 条。"""
        for i in range(150):
            send_notification(vault, "drift", f"msg-{i}")
        notifs = read_notifications(vault)
        assert len(notifs) == NOTIFY_MAX
        # 保留的是最后 100 条 (msg-50 ~ msg-149)
        assert notifs[0]["message"] == "msg-50"
        assert notifs[-1]["message"] == "msg-149"

    def test_cap_exactly_100_kept(self, vault: Vault) -> None:
        """发送正好 100 条 → 全部保留。"""
        for i in range(100):
            send_notification(vault, "drift", f"msg-{i}")
        notifs = read_notifications(vault)
        assert len(notifs) == 100
        assert notifs[0]["message"] == "msg-0"
        assert notifs[-1]["message"] == "msg-99"

    def test_cap_101_truncates_oldest(self, vault: Vault) -> None:
        """发送 101 条 → 第一条被截断, 保留 msg-1 ~ msg-100。"""
        for i in range(101):
            send_notification(vault, "drift", f"msg-{i}")
        notifs = read_notifications(vault)
        assert len(notifs) == 100
        assert notifs[0]["message"] == "msg-1"
        assert notifs[-1]["message"] == "msg-100"

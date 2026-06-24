"""Owner 通知通道 — 写入 owner-notify.json, 可被 Web UI 读取。

issue #54: Mortis 向 owner 推送通知的通道。通知文件位于
`mortis-subconscious/owner-notify.json`（与 steiner 隐藏层并列的
owner-facing 子目录）。

通知类型:
- drift: drift 超阈值 (steiner.drift.should_notify_owner)
- unease: unease 达到高档 (≥ 0.75)
- dream: dream 完成

设计要点:
- 纯 stdlib (json + pathlib), 无外部依赖
- 通知是 append-only 列表, 只保留最近 100 条
- mark_read 标记单条已读 (Web UI 调用)
- 文件损坏 → 静默返回空列表 (与 load_unease 一致, 不干扰主流程)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from mortis.vault import Vault

# 通知文件名
NOTIFY_FILE = "owner-notify.json"

# 通知子目录 (与 SUBCONSCIOUS_DIR 一致, 但不依赖 growth 包避免循环导入)
NOTIFY_SUBDIR = "mortis-subconscious"

# 通知保留上限 (FIFO, 超出截断旧通知)
NOTIFY_MAX = 100


def send_notification(
    vault: Vault,
    ntype: str,
    message: str,
    severity: str = "info",
) -> None:
    """发送通知到 owner-notify.json。

    Args:
        vault: vault 实例 (通知写到 vault.root / NOTIFY_SUBDIR / NOTIFY_FILE)。
        ntype: 通知类型 (drift / unease / dream / ...)。
        message: 通知正文。
        severity: 严重级别 (info / warning / critical), 默认 info。

    通知结构:
        {
            "type": str,
            "message": str,
            "severity": str,
            "timestamp": ISO8601 UTC,
            "read": False,
        }

    行为:
    - 文件不存在 → 新建, 写入第一条。
    - 文件存在但损坏 → 当作空列表重新开始 (不抛错)。
    - append 后只保留最近 NOTIFY_MAX 条 (FIFO 截断旧通知)。
    """
    notify_path = vault.root / NOTIFY_SUBDIR / NOTIFY_FILE
    notify_path.parent.mkdir(parents=True, exist_ok=True)

    notifications = read_notifications(vault)

    notifications.append({
        "type": ntype,
        "message": message,
        "severity": severity,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "read": False,
    })

    # 只保留最近 NOTIFY_MAX 条
    notifications = notifications[-NOTIFY_MAX:]

    notify_path.write_text(
        json.dumps(notifications, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def read_notifications(vault: Vault) -> list[dict]:
    """读取通知列表。

    文件不存在 → 返回 []。
    文件损坏 / 非 list → 返回 [] (静默回退, 与 load_unease 一致)。
    """
    notify_path = vault.root / NOTIFY_SUBDIR / NOTIFY_FILE
    if not notify_path.exists():
        return []
    try:
        data = json.loads(notify_path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError, ValueError):
        return []


def mark_read(vault: Vault, index: int) -> bool:
    """标记通知为已读。

    Args:
        vault: vault 实例。
        index: 通知在列表中的下标 (0-based)。

    Returns:
        True 如果 index 合法且成功标记; False 如果越界 (不抛异常)。
    """
    notifications = read_notifications(vault)
    if 0 <= index < len(notifications):
        notifications[index]["read"] = True
        notify_path = vault.root / NOTIFY_SUBDIR / NOTIFY_FILE
        notify_path.write_text(
            json.dumps(notifications, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return True
    return False


__all__ = [
    "NOTIFY_FILE",
    "NOTIFY_SUBDIR",
    "NOTIFY_MAX",
    "send_notification",
    "read_notifications",
    "mark_read",
]

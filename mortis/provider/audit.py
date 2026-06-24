"""Provider 审计日志工具 (issue #87)。

提供 SHA256 hash 前缀计算 — 用于在 log 中可追溯地标识 prompt / response
内容, 而**不记录原文** (HARNESS.md '数据不外流' 原则)。

设计要点:
- 同样的输入永远产生同样的 hash → 事后可比对某次调用是否泄漏/篡改
- hash 不可逆 → 无法从 log 反推 prompt 原文
- 只取前 16 位 hex → log 紧凑, 碰撞概率对审计场景足够低
"""

from __future__ import annotations

import hashlib

from .base import Message

# 审计 hash 默认截取长度 (SHA256 hex 前 16 位)
AUDIT_HASH_LENGTH = 16


def sha256_prefix(text: str, length: int = AUDIT_HASH_LENGTH) -> str:
    """计算 ``text`` 的 SHA256 hash, 返回前 ``length`` 位 hex。

    Args:
        text: 要 hash 的文本 (prompt / response 字符串)。
        length: 返回的 hex 前缀长度 (默认 16)。

    Returns:
        小写 hex 字符串, 长度 = ``length``。空串也返回其 hash (非空)。
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def messages_hash(messages: list[Message], length: int = AUDIT_HASH_LENGTH) -> str:
    """计算消息列表的审计 hash。

    把每条消息的 ``role`` + ``content`` 拼成稳定字符串再 hash —
    既能区分 role 不同导致的语义差异, 又不依赖 Message 的 repr/字段顺序。

    Args:
        messages: 消息列表 (system/user/assistant/tool)。
        length: 返回的 hex 前缀长度 (默认 16)。

    Returns:
        小写 hex 字符串, 长度 = ``length``。
    """
    blob = "\n".join(f"{m.role}:{m.content}" for m in messages)
    return sha256_prefix(blob, length=length)

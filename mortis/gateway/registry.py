"""Mortis Gateway registry — 渠道注册表。

按名称注册渠道类, 供 Gateway / CLI 按名称实例化。

用法::

    from mortis.gateway import register_channel, WebChannel
    register_channel("web", WebChannel)

    from mortis.gateway import get_channel
    cls = get_channel("web")
    channel = cls()
"""

from __future__ import annotations

from typing import Callable

from .base import Channel

# 渠道工厂注册表: name -> () -> Channel
# 用工厂而非类, 因为某些渠道构造需参数 (token / webhook_url 等)。
_CHANNEL_REGISTRY: dict[str, Callable[[], Channel]] = {}


def register_channel(name: str, factory: Callable[[], Channel]) -> None:
    """注册一个渠道工厂。

    Args:
        name: 渠道唯一名 (如 "web" / "wechat" / "telegram")。
        factory: 无参可调用, 返回一个 Channel 实例。
    """
    _CHANNEL_REGISTRY[name] = factory


def get_channel(name: str) -> Callable[[], Channel]:
    """取已注册的渠道工厂。未注册 → KeyError。"""
    if name not in _CHANNEL_REGISTRY:
        raise KeyError(
            f"channel not registered: {name!r}. "
            f"available: {list(_CHANNEL_REGISTRY)}"
        )
    return _CHANNEL_REGISTRY[name]


def list_channels() -> list[str]:
    """列出所有已注册的渠道名。"""
    return sorted(_CHANNEL_REGISTRY.keys())


__all__ = ["register_channel", "get_channel", "list_channels"]

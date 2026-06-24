"""Provider 路由 — 按任务类型选择 provider (issue #45)。

支持配置: reflect 用便宜模型, dream 用强模型, pipeline 用默认模型。
无配置的任务类型回退到调用方传入的 default provider。
"""

from __future__ import annotations

from .base import LLMProviderProtocol

# 任务类型 → provider 名称映射 (模块级全局)
_TASK_ROUTING: dict[str, str] = {}


def configure_routing(config: dict[str, str]) -> None:
    """配置任务路由。

    如: ``configure_routing({"reflect": "mock", "dream": "minimax"})``

    重复配置同名任务会覆盖旧值。传入空 dict 不影响现有配置。

    Args:
        config: 任务类型 → provider 名称 的映射。
    """
    _TASK_ROUTING.update(config)


def get_provider_for_task(
    task: str, default_provider: LLMProviderProtocol
) -> LLMProviderProtocol:
    """按任务类型获取 provider，无配置时返回 default。

    Args:
        task: 任务类型 (如 "reflect" / "dream" / "pipeline")。
        default_provider: 未配置路由时回退使用的 provider。

    Returns:
        与任务匹配的 provider 实例; 无配置时返回 ``default_provider``。
    """
    name = _TASK_ROUTING.get(task)
    if not name:
        return default_provider
    from mortis.provider import make_provider

    return make_provider(name)

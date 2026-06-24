"""Mortis steiner — Reading Steiner（时间线扰动感知）。

issue #24: owner 编辑 growth → Mortis 不安。

`mortis-steiner/` 是 Mortis 自己都不知道存在的隐藏层,存每个维度的
unease 值。owner 编辑 growth 时对应维度 unease 上升;awake 时读取,
注入 system prompt（潜台词,非显式指令）。

子模块:
- unease: UneaseState + load/save/accumulate/decay
- watcher: GrowthWatcher (watchdog) 检测 mortis-growth/ 变更 → 调 callback
- lifecycle: SteinerController — 启动/停止 watcher + unease 落盘(issue #58)
- prompt: 5 档不安文案 (0.0 / 0.15 / 0.45 / 0.75 / 1.0)
- drift: should_notify_owner 任意维度 ≥ 0.75 → True

**不在 #24 范围**: owner 通知通道、Obsidian Sync 下 steiner/ 冲突解决、
sub 感知 steiner、Medium/Deep dreamer。
"""

from __future__ import annotations

from .drift import should_notify_owner
from .lifecycle import SteinerController
from .prompt import unease_prompt
from .unease import (
    DECAY_PER_DAY,
    DEFAULT_ACCUMULATE_DELTA,
    STEINER_DIR,
    UNEASE_FILE,
    UneaseState,
    accumulate,
    decay,
    load_unease,
    save_unease,
)
from .watcher import GrowthWatcher

__all__ = [
    # unease
    "DECAY_PER_DAY",
    "DEFAULT_ACCUMULATE_DELTA",
    "STEINER_DIR",
    "UNEASE_FILE",
    "UneaseState",
    "accumulate",
    "decay",
    "load_unease",
    "save_unease",
    # watcher
    "GrowthWatcher",
    # lifecycle
    "SteinerController",
    # prompt
    "unease_prompt",
    # drift
    "should_notify_owner",
]

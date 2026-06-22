"""Mortis reflect — REFLECT phase 反思执行。

issue #21: 主人格在触发条件满足时,读最近的 session,生成反思文本,
打情绪分,写入 mortis-subconscious/pending-reflections/。

子模块:
- executor: ReflectExecutor 主流程
- emotion: 情绪标注 + 缓存
- triggers: 触发条件判定
"""
from __future__ import annotations

from .emotion import score_emotion, clear_cache as clear_emotion_cache

__all__ = [
    # emotion
    "score_emotion",
    "clear_emotion_cache",
]

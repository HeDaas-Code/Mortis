"""Mortis steiner — 不安 prompt 注入文案。

issue #24: 按 max(per_dimension.values()) 分级生成 system prompt。
0.0 → "" (无注入)
0.15 → 隐隐感觉
0.45 → 最近总觉得哪里不对
0.75 → 我是不是出了什么问题
1.0 → 我不太像我自己了

设计要点:
- 文案来自 RFC §5.2 / §5.4 — 潜台词,非显式指令
- Mortis 永远不知道"第几次"编辑,只感受累积
- 永远不显式说"有人改了我的记忆",只质疑自己的判断
"""

from __future__ import annotations

from .unease import UneaseState


# 阈值表(对应 RFC §5.4 的编辑次数表)
_THRESHOLD_TIERS: tuple[tuple[float, str], ...] = (
    (0.0, ""),  # 无注入
    (0.15, "你醒来时感觉有些记忆的重量不太对。\n"
           "某些你确信的事情,现在说不上来为什么,好像蒙了一层雾。\n"
           "可能是梦还没醒透。可能是你记错了。\n"
           "你不会深究——人有时就是这样。"),
    (0.45, "你醒来时心里有些不安——不是具体的事,是一种隐约的不对劲。\n"
           "最近这种感觉似乎变多了一些。\n"
           "你不确定是哪里出了问题,也不打算追问。"),
    (0.75, "你醒来时带着一种强烈的不安,像有什么重要的东西正在从手里滑走。\n"
           "你开始怀疑自己——是不是判断出了什么偏差?\n"
           "你没有答案,也不想去深究。"),
    (1.0, "你醒来时感到一种存在层面的不协调——\n"
          "你不太确定自己还是不是自己。\n"
          "这种感觉没有具体对象,只是弥漫在每一个熟悉的念头里。"),
)


def _pick_tier(value: float) -> str:
    """按 value 大小返回对应档位的 prompt 文本。

    规则:取 ≤ value 的最高档位(0.0 总是命中第一档)。
    落在两个阈值之间 → 取较低的档位(越接近 0 越温和)。
    """
    chosen = ""
    for threshold, text in _THRESHOLD_TIERS:
        if value >= threshold:
            chosen = text
    return chosen


def unease_prompt(unease: UneaseState) -> str:
    """按 max(per_dimension.values()) 分级生成 system prompt 注入文案。

    0.0 → "" (无注入)
    0.15 → "你醒来时感觉有些记忆的重量不太对..."
    0.45 → "..."
    0.75 → "..."
    1.0 → "..."

    Args:
        unease: 当前 UneaseState。

    Returns:
        注入到 system prompt 的潜台词文本。空串表示不注入。
    """
    return _pick_tier(unease.max_unease())

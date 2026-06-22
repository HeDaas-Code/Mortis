"""Mortis dream — RECALL phase: 情绪加权采样。

issue #22: 按 abs(valence) × arousal 加权随机采样 k 条 session。
纯函数 — 不依赖 vault / provider / IO,只接已算好的 (item, v, a) 三元组。

设计要点:
- 权重公式: w = abs(valence) * arousal
  - 极平静文本 (arousal ≈ 0) → 权重大概率极低,符合"平静内容不重要"直觉
  - 高 valence 高 arousal → 最易被选中
  - 0 valence 高 arousal → 也选中(纯粹激动也算)
- 加权随机不保证选中: rng.sample(weights=k, k) 在权重分布稀疏时可能跳过某条
- 确定性: 同一 input + 同一 rng → 同一 output(测试关键)
- 边界:
  - items 空 → []
  - k <= 0 → []
  - k >= len(items) → 全返回(顺序按 items 原序)
  - weight 全 0 → 用 uniform fallback
"""

from __future__ import annotations

import random
from typing import Any, Hashable


def compute_weight(valence: float, arousal: float) -> float:
    """计算情绪权重 w = abs(valence) * arousal。

    输入范围:
        valence ∈ [-1.0, 1.0]
        arousal ∈ [0.0, 1.0]

    返回: w ∈ [0.0, 1.0]
    """
    return abs(valence) * arousal


def emotion_weighted_sample(
    items: list[tuple[Any, float, float]],
    k: int,
    rng: random.Random,
) -> list[Any]:
    """从 (item, valence, arousal) 列表里按情绪权重采样 k 条。

    Args:
        items: [(item, valence, arousal), ...] 三元组列表。
            item 可以是任意类型(Session / path / ID 都行),
            函数只对 item 做返回,不修改。
        k: 要采样的数量。
        rng: 随机数生成器 — 必须由调用方注入,保证可复现。

    Returns:
        长度为 min(k, len(items)) 的 item 列表。
        当 k >= len(items) 时按 items 原序返回全量。
        空 items / k <= 0 → []。

    注意:
        - **保留随机性**:高权重更易被选中,但不保证。
        - **确定性**:同 input + 同 rng 状态 → 同 output(测试用 `rng.seed(42)` 验证)。
        - 当所有 weight = 0 时退化为 uniform random(用 weights=[1]*n)。
    """
    n = len(items)
    if n == 0 or k <= 0:
        return []

    if k >= n:
        # 全返回 — 不打乱原序(确定性 + 调用方预期)
        return [item for item, _v, _a in items]

    weights = [compute_weight(v, a) for _item, v, a in items]

    if sum(weights) == 0:
        # 全部 weight=0 → uniform fallback
        indices = list(range(n))
        rng.shuffle(indices)
        return [items[i][0] for i in indices[:k]]

    # Python 的 random.choices 做加权采样,但不放回;
    # 自己用 weighted sample without replacement 实现:用 rng.random() + 累积权重。
    indices = list(range(n))
    chosen: list[int] = []
    remaining = list(zip(indices, weights))

    for _ in range(k):
        if not remaining:
            break
        idxs, wts = zip(*remaining)
        total = sum(wts)
        pick = rng.random() * total
        cum = 0.0
        picked_pos = len(remaining) - 1  # fallback: 选最后一个
        for i, w in enumerate(wts):
            cum += w
            if cum >= pick:
                picked_pos = i
                break
        chosen.append(remaining[picked_pos][0])
        # 移除已选(不放回)
        remaining.pop(picked_pos)

    return [items[i][0] for i in chosen]
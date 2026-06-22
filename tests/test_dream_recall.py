"""Mortis dream — recall 测试。issue #22 验收 #2。"""

from __future__ import annotations

import random

import pytest

from mortis.dream.recall import (
    compute_weight,
    emotion_weighted_sample,
)


class TestComputeWeight:
    """权重公式 w = abs(valence) * arousal."""

    def test_positive_high_arousal(self):
        assert compute_weight(0.8, 0.9) == pytest.approx(0.72)

    def test_negative_high_arousal(self):
        # abs(-0.8) * 0.9
        assert compute_weight(-0.8, 0.9) == pytest.approx(0.72)

    def test_zero_arousal_zero_weight(self):
        assert compute_weight(0.5, 0.0) == 0.0
        assert compute_weight(-0.5, 0.0) == 0.0

    def test_zero_valence(self):
        # abs(0) * anything = 0
        assert compute_weight(0.0, 0.5) == 0.0


class TestEmotionWeightedSampleEmpty:
    """空输入边界。"""

    def test_empty_list(self):
        rng = random.Random(42)
        assert emotion_weighted_sample([], k=3, rng=rng) == []

    def test_k_zero(self):
        rng = random.Random(42)
        items = [("a", 0.5, 0.5), ("b", 0.5, 0.5)]
        assert emotion_weighted_sample(items, k=0, rng=rng) == []

    def test_k_negative(self):
        rng = random.Random(42)
        items = [("a", 0.5, 0.5)]
        assert emotion_weighted_sample(items, k=-1, rng=rng) == []


class TestEmotionWeightedSampleFull:
    """k >= len(items) → 全返回。"""

    def test_k_equals_n(self):
        rng = random.Random(42)
        items = [("a", 0.5, 0.5), ("b", -0.5, 0.5), ("c", 0.0, 0.0)]
        result = emotion_weighted_sample(items, k=3, rng=rng)
        assert sorted(result) == ["a", "b", "c"]

    def test_k_greater_than_n(self):
        rng = random.Random(42)
        items = [("a", 0.5, 0.5), ("b", 0.5, 0.5)]
        result = emotion_weighted_sample(items, k=10, rng=rng)
        assert sorted(result) == ["a", "b"]


class TestEmotionWeightedSampleDeterminism:
    """同 input + 同 seed → 同 output。"""

    def test_same_seed_same_output(self):
        items = [
            ("a", 0.9, 0.9),
            ("b", -0.7, 0.8),
            ("c", 0.5, 0.6),
            ("d", 0.0, 0.0),  # 不会被选中(weight=0 但 fallback 时可能被选)
            ("e", 0.3, 0.4),
        ]
        r1 = emotion_weighted_sample(items, k=2, rng=random.Random(42))
        r2 = emotion_weighted_sample(items, k=2, rng=random.Random(42))
        assert r1 == r2

    def test_different_seed_different_output(self):
        # 不是 100% 保证,但大概率不同 — 至少验证 seed 影响 output
        items = [(f"item_{i}", 0.5, 0.5) for i in range(20)]
        out_seeds = set()
        for seed in [1, 2, 3, 4, 5]:
            r = emotion_weighted_sample(items, k=5, rng=random.Random(seed))
            out_seeds.add(tuple(r))
        # 5 个 seed 至少应产生 2 种不同输出(20 个 item 选 5,组合空间巨大)
        assert len(out_seeds) >= 2


class TestEmotionWeightedSampleWeightEffect:
    """权重分布对采样的影响。"""

    def test_high_weight_item_preferred(self):
        """极端: 一条 weight=1, 一条 weight=0,采 k=1 → 大概率选中 weight=1。"""
        items = [("low", 0.0, 0.0), ("high", 1.0, 1.0)]
        # 100 次 seed=0..99 跑,high 应被选 >50 次
        high_count = 0
        for seed in range(100):
            rng = random.Random(seed)
            r = emotion_weighted_sample(items, k=1, rng=rng)
            if r[0] == "high":
                high_count += 1
        assert high_count >= 50

    def test_all_zero_weights_uniform(self):
        """全 0 weight → uniform fallback(不应爆)。"""
        items = [("a", 0.0, 0.0), ("b", 0.0, 0.0), ("c", 0.0, 0.0)]
        rng = random.Random(42)
        result = emotion_weighted_sample(items, k=2, rng=rng)
        assert len(result) == 2
        assert set(result) <= {"a", "b", "c"}


class TestEmotionWeightedSamplePreservesType:
    """item 类型不限定,函数透传原对象。"""

    def test_returns_original_objects(self):
        class Obj:
            pass

        a, b = Obj(), Obj()
        items = [(a, 0.5, 0.5), (b, -0.5, 0.5)]
        result = emotion_weighted_sample(items, k=1, rng=random.Random(42))
        assert result[0] is a or result[0] is b
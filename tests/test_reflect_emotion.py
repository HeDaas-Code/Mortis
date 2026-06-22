"""Test mortis.reflect.emotion — 情绪标注 + 缓存。

issue #21 acceptance:
- score_emotion(provider, session_path, text) -> (valence, arousal)
- 同一 session_path 二次调用 → 命中缓存,不调 provider
- parse 失败 → 回退 (0.0, 0.0) + warning
- clamp 到合法范围
"""
from __future__ import annotations

import logging
import re

import pytest

from mortis.provider import MockProvider
from mortis.reflect.emotion import clear_cache, score_emotion


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    """每个测试前清空 module-level 缓存,避免跨测试污染。"""
    clear_cache()
    yield
    clear_cache()


class TestScoreEmotion:
    """score_emotion 主流程。"""

    def test_basic_call_parses_json(self) -> None:
        """LLM 输出严格 JSON → 正确 parse。"""
        provider = MockProvider(responses=['{"valence": 0.6, "arousal": 0.4}'])
        v, a = score_emotion(provider, "s1", "some session text")
        assert v == 0.6
        assert a == 0.4

    def test_negative_valence(self) -> None:
        """负向 valence 正常 parse。"""
        provider = MockProvider(responses=['{"valence": -0.7, "arousal": 0.8}'])
        v, a = score_emotion(provider, "s1", "text")
        assert v == -0.7
        assert a == 0.8

    def test_zero_emotions(self) -> None:
        """中性 0/0 正常。"""
        provider = MockProvider(responses=['{"valence": 0.0, "arousal": 0.0}'])
        v, a = score_emotion(provider, "s1", "text")
        assert v == 0.0
        assert a == 0.0


class TestScoreEmotionCache:
    """缓存命中 — 第二次调同一 path 不再打 provider。"""

    def test_cache_hit_skips_provider(self) -> None:
        """第二次同 path → provider._call_count 不增加。"""
        provider = MockProvider(responses=['{"valence": 0.5, "arousal": 0.5}'])
        score_emotion(provider, "s1", "text A")
        assert provider._call_count == 1
        # 第二次(同 path) → 应该命中缓存
        score_emotion(provider, "s1", "text B (ignored)")
        assert provider._call_count == 1

    def test_different_paths_invoke_separately(self) -> None:
        """不同 session_path 各自打一次。"""
        provider = MockProvider(responses=[
            '{"valence": 0.1, "arousal": 0.1}',
            '{"valence": 0.9, "arousal": 0.9}',
        ])
        score_emotion(provider, "s1", "text")
        score_emotion(provider, "s2", "text")
        assert provider._call_count == 2

    def test_clear_cache_resets(self) -> None:
        """clear_cache 后同一 path 重新打。"""
        provider = MockProvider(responses=[
            '{"valence": 0.1, "arousal": 0.1}',
            '{"valence": 0.2, "arousal": 0.2}',
        ])
        score_emotion(provider, "s1", "x")
        clear_cache()
        score_emotion(provider, "s1", "x")
        assert provider._call_count == 2


class TestScoreEmotionFallback:
    """parse 失败 / 越界 — 走兜底。"""

    def test_invalid_json_falls_back_to_zero(self, caplog: pytest.LogCaptureFixture) -> None:
        """LLM 输出非 JSON → (0,0) + warning。"""
        provider = MockProvider(responses=["嗯,这看起来挺平静的"])
        with caplog.at_level(logging.WARNING):
            v, a = score_emotion(provider, "s1", "text")
        assert v == 0.0
        assert a == 0.0
        assert any("fallback" in r.message.lower() for r in caplog.records)

    def test_json_with_markdown_wrapper(self) -> None:
        """LLM 用 ```json ... ``` 包裹 → 正则仍能挑出来。"""
        provider = MockProvider(responses=[
            '```json\n{"valence": 0.3, "arousal": 0.7}\n```'
        ])
        v, a = score_emotion(provider, "s1", "text")
        assert v == 0.3
        assert a == 0.7

    def test_empty_response_falls_back(self) -> None:
        """LLM 返回空字符串 → (0,0)。"""
        provider = MockProvider(responses=[""])
        v, a = score_emotion(provider, "s1", "text")
        assert v == 0.0
        assert a == 0.0

    def test_out_of_range_clamped(self) -> None:
        """LLM 输出越界 → clamp。"""
        provider = MockProvider(responses=['{"valence": 1.5, "arousal": -0.2}'])
        v, a = score_emotion(provider, "s1", "text")
        assert v == 1.0  # clamp
        assert a == 0.0  # clamp

    def test_missing_keys_falls_back(self) -> None:
        """JSON 缺字段 → (0,0)。"""
        provider = MockProvider(responses=['{"mood": "happy"}'])
        v, a = score_emotion(provider, "s1", "text")
        assert v == 0.0
        assert a == 0.0

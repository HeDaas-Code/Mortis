"""Test mortis.growth.compress — 同维度低 confidence growth 合并。

issue #47: 维度压缩测试。
覆盖:
- 无候选时不操作
- 2 个低 confidence growth 合并为 1 条
- 高 confidence growth 不被合并
- 合并后 confidence = max + 0.1 (不超过 0.5)
- 合并后 source_sessions 是 union
- 合并后 tags 是 union
- 有 provider 时用 LLM 合并 body
- 无 provider 时 fallback 拼接
- 幂等性（多次调用不重复压缩）
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mortis.growth.compress import (
    COMPRESSION_THRESHOLD,
    MAX_COMPRESSED_CONFIDENCE,
    MIN_CANDIDATES,
    _merge_candidates,
    compress_growths,
)
from mortis.growth.model import Dimension, DreamLevel, Growth
from mortis.growth.vault_layout import growth_rel
from mortis.provider.mock import MockProvider
from mortis.vault.local import Vault


def _make_growth(**overrides) -> Growth:
    """构造一个合法的 Growth，可覆盖任意字段。"""
    defaults = dict(
        id="growth-2026-06-22-001",
        dimension=Dimension.TONE,
        confidence=0.6,
        created_at="2026-06-22T10:00:00+00:00",
        last_validated="2026-06-22T10:00:00+00:00",
        source_sessions=("session-a",),
        dream_level=DreamLevel.MEDIUM,
        emotional_valence=0.5,
        emotional_arousal=0.3,
        tags=("沟通策略", "已验证"),
        body="技术讨论中先给结论再解释，更有效。",
    )
    defaults.update(overrides)
    return Growth(**defaults)


@pytest.fixture()
def vault(tmp_path: Path) -> Vault:
    """每个测试用独立的 tmp vault。"""
    return Vault(tmp_path)


class TestCompressNoOp:
    """无候选 / 候选不足时不操作。"""

    def test_no_candidates_empty_vault(self, vault: Vault) -> None:
        """空 vault 调 compress 不抛错, 返回 0/0。"""
        result = compress_growths(vault)
        assert result == {"compressed": 0, "merged": 0}
        assert vault.list_growths() == []

    def test_no_candidates_all_high_confidence(self, vault: Vault) -> None:
        """全部高 confidence (>= 阈值) 时不合并, 文件原样保留。"""
        g1 = _make_growth(id="g-1", confidence=0.5, body="高置信 1")
        g2 = _make_growth(id="g-2", confidence=0.9, body="高置信 2")
        vault.write_growth(g1)
        vault.write_growth(g2)

        result = compress_growths(vault)
        assert result == {"compressed": 0, "merged": 0}
        # 两个文件都还在
        assert len(vault.list_growths()) == 2

    def test_single_low_confidence_not_merged(self, vault: Vault) -> None:
        """只有 1 个低 confidence (< MIN_CANDIDATES) 不触发合并。"""
        g_low = _make_growth(id="g-low", confidence=0.1, body="低置信")
        g_high = _make_growth(id="g-high", confidence=0.8, body="高置信")
        vault.write_growth(g_low)
        vault.write_growth(g_high)

        result = compress_growths(vault)
        assert result == {"compressed": 0, "merged": 0}
        # 低置信文件仍在 (未被删)
        assert vault.exists(growth_rel(Dimension.TONE, "g-low"))


class TestCompressMerge:
    """2 个低 confidence growth 合并为 1 条。"""

    def test_two_low_confidence_merged_into_one(self, vault: Vault) -> None:
        """同维度 2 个低 confidence growth 合并后只剩 1 条。"""
        g1 = _make_growth(id="g-1", confidence=0.1, body="记忆一")
        g2 = _make_growth(id="g-2", confidence=0.2, body="记忆二")
        vault.write_growth(g1)
        vault.write_growth(g2)

        result = compress_growths(vault)
        assert result["compressed"] == 2
        assert result["merged"] == 1

        # 只剩 1 条 (合并后的)
        remaining = vault.list_growths(dimension=Dimension.TONE)
        assert len(remaining) == 1

        # 旧文件被删
        assert not vault.exists(growth_rel(Dimension.TONE, "g-1"))
        assert not vault.exists(growth_rel(Dimension.TONE, "g-2"))

        # 合并后的能读出来, dimension 保持
        merged = vault.read_growth(remaining[0])
        assert merged.dimension == Dimension.TONE
        assert merged.id.startswith("compressed-")

    def test_high_confidence_not_merged_stays(self, vault: Vault) -> None:
        """高 confidence growth 不被合并, 与低 confidence 一起时只合并低的。"""
        g_low1 = _make_growth(id="g-low1", confidence=0.1, body="低一")
        g_low2 = _make_growth(id="g-low2", confidence=0.15, body="低二")
        g_high = _make_growth(id="g-high", confidence=0.8, body="高置信保留")
        vault.write_growth(g_low1)
        vault.write_growth(g_low2)
        vault.write_growth(g_high)

        result = compress_growths(vault)
        assert result["compressed"] == 2
        assert result["merged"] == 1

        # 高 confidence 文件原样保留
        assert vault.exists(growth_rel(Dimension.TONE, "g-high"))
        high = vault.read_growth(growth_rel(Dimension.TONE, "g-high"))
        assert high.confidence == 0.8
        assert high.body == "高置信保留"

        # 总共剩 2 条 (1 合并 + 1 高置信)
        assert len(vault.list_growths(dimension=Dimension.TONE)) == 2

    def test_only_specified_dimension_compressed(self, vault: Vault) -> None:
        """传 dimension 参数时只压缩该维度, 其他维度不动。"""
        # TONE: 2 个低 confidence
        vault.write_growth(_make_growth(id="t-1", dimension=Dimension.TONE, confidence=0.1, body="t1"))
        vault.write_growth(_make_growth(id="t-2", dimension=Dimension.TONE, confidence=0.1, body="t2"))
        # IDENTITY: 2 个低 confidence
        vault.write_growth(_make_growth(id="i-1", dimension=Dimension.IDENTITY, confidence=0.1, body="i1"))
        vault.write_growth(_make_growth(id="i-2", dimension=Dimension.IDENTITY, confidence=0.1, body="i2"))

        result = compress_growths(vault, dimension=Dimension.TONE)
        assert result == {"compressed": 2, "merged": 1}

        # TONE 被压缩 → 只剩 1 条
        assert len(vault.list_growths(dimension=Dimension.TONE)) == 1
        # IDENTITY 未被压缩 → 仍 2 条
        assert len(vault.list_growths(dimension=Dimension.IDENTITY)) == 2


class TestCompressConfidence:
    """合并后 confidence = max + 0.1 (不超过 0.5)。"""

    def test_merged_confidence_is_max_plus_0_1(self, vault: Vault) -> None:
        """合并后 confidence = max(候选) + 0.1。"""
        g1 = _make_growth(id="g-1", confidence=0.1, body="记忆一")
        g2 = _make_growth(id="g-2", confidence=0.2, body="记忆二")
        vault.write_growth(g1)
        vault.write_growth(g2)

        compress_growths(vault)

        merged = vault.read_growth(vault.list_growths(dimension=Dimension.TONE)[0])
        # max(0.1, 0.2) + 0.1 = 0.3
        assert merged.confidence == pytest.approx(0.3, abs=0.001)

    def test_merged_confidence_capped_at_0_5(self) -> None:
        """max + 0.1 超过 0.5 时被截断到 0.5。

        直接测 _merge_candidates — 用高于阈值的 confidence 验证 cap 逻辑
        (compress_growths 的阈值筛选不会让这种候选进入, 但合并公式本身需正确)。
        """
        g1 = _make_growth(id="g-1", confidence=0.45, body="高")
        g2 = _make_growth(id="g-2", confidence=0.48, body="更高")
        candidates = [
            (growth_rel(Dimension.TONE, "g-1"), g1),
            (growth_rel(Dimension.TONE, "g-2"), g2),
        ]
        merged = _merge_candidates(candidates, provider=None)
        assert merged is not None
        # max(0.45, 0.48) + 0.1 = 0.58 → cap 到 0.5
        assert merged.confidence == pytest.approx(MAX_COMPRESSED_CONFIDENCE, abs=0.001)

    def test_constants(self) -> None:
        """压缩常量符合 issue 约定。"""
        assert COMPRESSION_THRESHOLD == 0.3
        assert MIN_CANDIDATES == 2
        assert MAX_COMPRESSED_CONFIDENCE == 0.5


class TestCompressUnionFields:
    """合并后 source_sessions / tags 是 union。"""

    def test_merged_source_sessions_is_union(self, vault: Vault) -> None:
        """合并后 source_sessions = union(候选), 排序去重。"""
        g1 = _make_growth(
            id="g-1",
            confidence=0.1,
            source_sessions=("s-a", "s-b"),
            body="记忆一",
        )
        g2 = _make_growth(
            id="g-2",
            confidence=0.1,
            source_sessions=("s-b", "s-c"),
            body="记忆二",
        )
        vault.write_growth(g1)
        vault.write_growth(g2)

        compress_growths(vault)

        merged = vault.read_growth(vault.list_growths(dimension=Dimension.TONE)[0])
        # union = {s-a, s-b, s-c}, sorted
        assert merged.source_sessions == ("s-a", "s-b", "s-c")

    def test_merged_tags_is_union(self, vault: Vault) -> None:
        """合并后 tags = union(候选), 排序去重。"""
        g1 = _make_growth(
            id="g-1",
            confidence=0.1,
            tags=("沟通", "复盘"),
            body="记忆一",
        )
        g2 = _make_growth(
            id="g-2",
            confidence=0.1,
            tags=("复盘", "成长"),
            body="记忆二",
        )
        vault.write_growth(g1)
        vault.write_growth(g2)

        compress_growths(vault)

        merged = vault.read_growth(vault.list_growths(dimension=Dimension.TONE)[0])
        # union = {沟通, 复盘, 成长}, sorted
        assert merged.tags == tuple(sorted({"沟通", "复盘", "成长"}))


class TestCompressBody:
    """body 合并: 有 provider 用 LLM, 无 provider fallback 拼接。"""

    def test_with_provider_uses_llm_merge(self, vault: Vault) -> None:
        """有 provider 时, body = LLM 返回的摘要。"""
        provider = MockProvider(responses=["LLM 合并摘要结果"])
        g1 = _make_growth(id="g-1", confidence=0.1, body="记忆一内容")
        g2 = _make_growth(id="g-2", confidence=0.1, body="记忆二内容")
        vault.write_growth(g1)
        vault.write_growth(g2)

        compress_growths(vault, provider=provider)

        merged = vault.read_growth(vault.list_growths(dimension=Dimension.TONE)[0])
        assert merged.body == "LLM 合并摘要结果"

    def test_without_provider_fallback_concat(self, vault: Vault) -> None:
        """无 provider 时, body = 前 3 条用 ' | ' 拼接。"""
        g1 = _make_growth(id="g-1", confidence=0.1, body="记忆一")
        g2 = _make_growth(id="g-2", confidence=0.1, body="记忆二")
        vault.write_growth(g1)
        vault.write_growth(g2)

        compress_growths(vault, provider=None)

        merged = vault.read_growth(vault.list_growths(dimension=Dimension.TONE)[0])
        assert merged.body == "记忆一 | 记忆二"

    def test_provider_exception_falls_back_to_concat(self) -> None:
        """provider 抛异常时 fallback 到拼接 (不崩)。"""

        class BoomProvider:
            def generate_text(self, *args, **kwargs) -> str:
                raise RuntimeError("provider down")

            def generate(self, *args, **kwargs):
                raise RuntimeError("provider down")

        g1 = _make_growth(id="g-1", confidence=0.1, body="记忆一")
        g2 = _make_growth(id="g-2", confidence=0.1, body="记忆二")
        candidates = [
            (growth_rel(Dimension.TONE, "g-1"), g1),
            (growth_rel(Dimension.TONE, "g-2"), g2),
        ]
        merged = _merge_candidates(candidates, provider=BoomProvider())  # type: ignore[arg-type]
        assert merged is not None
        assert merged.body == "记忆一 | 记忆二"


class TestCompressIdempotent:
    """幂等性 — 多次调用不会重复压缩。"""

    def test_idempotent_double_call(self, vault: Vault) -> None:
        """连续调两次 compress, 第二次不产生变化。"""
        g1 = _make_growth(id="g-1", confidence=0.1, body="记忆一")
        g2 = _make_growth(id="g-2", confidence=0.2, body="记忆二")
        vault.write_growth(g1)
        vault.write_growth(g2)

        first = compress_growths(vault)
        assert first == {"compressed": 2, "merged": 1}

        count_after_first = len(vault.list_growths(dimension=Dimension.TONE))
        assert count_after_first == 1

        # 第二次: 只剩 1 条 (合并后), < MIN_CANDIDATES → 不操作
        second = compress_growths(vault)
        assert second == {"compressed": 0, "merged": 0}
        assert len(vault.list_growths(dimension=Dimension.TONE)) == count_after_first

    def test_idempotent_when_merged_conf_below_threshold(self, vault: Vault) -> None:
        """合并后 confidence 仍 < 阈值时, 第二次因候选不足也不重复压缩。

        g1=0.0, g2=0.0 → merged = 0.1 (< 0.3 仍是候选),
        但只剩 1 条 < MIN_CANDIDATES → 不再压缩。
        """
        g1 = _make_growth(id="g-1", confidence=0.0, body="记忆一")
        g2 = _make_growth(id="g-2", confidence=0.0, body="记忆二")
        vault.write_growth(g1)
        vault.write_growth(g2)

        first = compress_growths(vault)
        assert first == {"compressed": 2, "merged": 1}

        merged = vault.read_growth(vault.list_growths(dimension=Dimension.TONE)[0])
        # merged confidence = 0.0 + 0.1 = 0.1 < 0.3 (仍是候选)
        assert merged.confidence == pytest.approx(0.1, abs=0.001)
        assert merged.confidence < COMPRESSION_THRESHOLD

        # 第二次: 只剩 1 条 < MIN_CANDIDATES → 不操作
        second = compress_growths(vault)
        assert second == {"compressed": 0, "merged": 0}
        assert len(vault.list_growths(dimension=Dimension.TONE)) == 1


class TestDeleteGrowth:
    """Vault.delete_growth 基础行为 (issue #47 依赖)。"""

    def test_delete_existing_returns_true(self, vault: Vault) -> None:
        g = _make_growth(id="g-del", confidence=0.5)
        vault.write_growth(g)
        rel = growth_rel(Dimension.TONE, "g-del")
        assert vault.delete_growth(rel) is True
        assert not vault.exists(rel)

    def test_delete_missing_returns_false(self, vault: Vault) -> None:
        rel = growth_rel(Dimension.TONE, "nope")
        assert vault.delete_growth(rel) is False

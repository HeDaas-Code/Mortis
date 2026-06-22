"""Test growth vault — 长期记忆 vault CRUD（issue #18 Phase 2）。

覆盖:
- write_growth / read_growth 基本路径 + 安全检查
- list_growths / list_growths_by_tag / list_growths_min_confidence
- roundtrip、跨 7 维度、ID 覆盖、目录 lazy init
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Iterator

from mortis.growth import (
    Dimension,
    DreamLevel,
    Growth,
    GROWTH_DIR,
    growth_rel,
)
from mortis.growth.vault_layout import DIMENSION_DIRS
from mortis.vault.local import Vault, VaultAccessDenied


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


class TestGrowthVault(unittest.TestCase):
    """Vault.write_growth / read_growth / list_* API。"""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="mortis-growth-vault-")
        self.vault = Vault(Path(self.tmp))

    def tearDown(self) -> None:
        # mkdtemp 不自动清理 — 显式删
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ----- 1: write_growth 成功 -----
    def test_write_growth_success(self) -> None:
        """write_growth 写一篇,文件出现在 mortis-growth/<dim>/<id>.md。"""
        g = _make_growth()
        self.vault.write_growth(g)
        rel = growth_rel(g.dimension, g.id)
        self.assertTrue(self.vault.exists(rel))

    # ----- 2: write_growth 白名单外 → VaultAccessDenied -----
    def test_write_growth_outside_whitelist_raises(self) -> None:
        """直接调 self.write 写到白名单外路径会抛 VaultAccessDenied。"""
        # 模拟 sub 试图绕过 growth API 直接写别处
        with self.assertRaises(VaultAccessDenied):
            self.vault.write(
                "mortis-journal/notes/evil.md",
                "x",
                whitelist=("mortis-growth/",),
            )

    # ----- 3: read_growth 成功 -----
    def test_read_growth_success(self) -> None:
        """write 后 read_growth 拿到 Growth,字段一致。"""
        g = _make_growth()
        self.vault.write_growth(g)
        rel = growth_rel(g.dimension, g.id)
        loaded = self.vault.read_growth(rel)
        self.assertEqual(loaded.id, g.id)
        self.assertEqual(loaded.dimension, g.dimension)
        self.assertEqual(loaded.body, g.body)

    # ----- 4: read_growth 文件不存在 → FileNotFoundError -----
    def test_read_growth_missing_raises(self) -> None:
        """读不存在的 growth → FileNotFoundError。"""
        rel = growth_rel(Dimension.IDENTITY, "nope")
        with self.assertRaises(FileNotFoundError):
            self.vault.read_growth(rel)

    # ----- 5: list_growths 全量 -----
    def test_list_growths_all(self) -> None:
        """list_growths() 返回 mortis-growth/ 下所有 .md。"""
        g1 = _make_growth(id="g-1", dimension=Dimension.TONE)
        g2 = _make_growth(id="g-2", dimension=Dimension.IDENTITY)
        self.vault.write_growth(g1)
        self.vault.write_growth(g2)

        all_paths = self.vault.list_growths()
        self.assertIn(growth_rel(Dimension.TONE, "g-1"), all_paths)
        self.assertIn(growth_rel(Dimension.IDENTITY, "g-2"), all_paths)
        self.assertEqual(len(all_paths), 2)

    # ----- 6: list_growths 按维度过滤 -----
    def test_list_growths_filter_by_dimension(self) -> None:
        """list_growths(dimension=...) 只返该维度的 .md。"""
        g1 = _make_growth(id="g-1", dimension=Dimension.TONE)
        g2 = _make_growth(id="g-2", dimension=Dimension.IDENTITY)
        g3 = _make_growth(id="g-3", dimension=Dimension.TONE)
        self.vault.write_growth(g1)
        self.vault.write_growth(g2)
        self.vault.write_growth(g3)

        tone_paths = self.vault.list_growths(dimension=Dimension.TONE)
        self.assertEqual(
            sorted(tone_paths),
            sorted([
                growth_rel(Dimension.TONE, "g-1"),
                growth_rel(Dimension.TONE, "g-3"),
            ]),
        )
        # identity 维度的不应出现在 tone 结果中
        self.assertNotIn(growth_rel(Dimension.IDENTITY, "g-2"), tone_paths)

    # ----- 7: list_growths_by_tag -----
    def test_list_growths_by_tag(self) -> None:
        """list_growths_by_tag 过滤 frontmatter.tags 包含指定 tag。"""
        g1 = _make_growth(id="g-1", dimension=Dimension.TONE, tags=("A", "B"))
        g2 = _make_growth(id="g-2", dimension=Dimension.IDENTITY, tags=("B", "C"))
        g3 = _make_growth(id="g-3", dimension=Dimension.VALUES, tags=("C",))
        self.vault.write_growth(g1)
        self.vault.write_growth(g2)
        self.vault.write_growth(g3)

        # tag B → g-1, g-2
        b_paths = self.vault.list_growths_by_tag("B")
        self.assertEqual(
            sorted(b_paths),
            sorted([
                growth_rel(Dimension.TONE, "g-1"),
                growth_rel(Dimension.IDENTITY, "g-2"),
            ]),
        )
        # tag C → g-2, g-3
        c_paths = self.vault.list_growths_by_tag("C")
        self.assertEqual(len(c_paths), 2)
        # 不存在的 tag → 空
        self.assertEqual(self.vault.list_growths_by_tag("nope"), [])

    # ----- 8: list_growths_min_confidence 边界 >= -----
    def test_list_growths_min_confidence_inclusive(self) -> None:
        """min_confidence(0.7) → confidence >= 0.7(包含 0.7 自身)。"""
        g_low = _make_growth(id="g-low", dimension=Dimension.TONE, confidence=0.5)
        g_mid = _make_growth(id="g-mid", dimension=Dimension.TONE, confidence=0.7)
        g_high = _make_growth(id="g-high", dimension=Dimension.TONE, confidence=0.9)
        self.vault.write_growth(g_low)
        self.vault.write_growth(g_mid)
        self.vault.write_growth(g_high)

        result = self.vault.list_growths_min_confidence(0.7)
        # 边界 0.7 必含,0.5 必排除
        self.assertIn(growth_rel(Dimension.TONE, "g-mid"), result)
        self.assertIn(growth_rel(Dimension.TONE, "g-high"), result)
        self.assertNotIn(growth_rel(Dimension.TONE, "g-low"), result)
        self.assertEqual(len(result), 2)

    # ----- 9: 跨 7 维度写入读出 -----
    def test_cross_all_seven_dimensions(self) -> None:
        """7 个维度各写一篇,list_growths() 都能找到。"""
        for dim in Dimension:
            g = _make_growth(id=f"g-{dim.value}", dimension=dim)
            self.vault.write_growth(g)

        all_paths = self.vault.list_growths()
        self.assertEqual(len(all_paths), 7)
        for dim in Dimension:
            rel = growth_rel(dim, f"g-{dim.value}")
            self.assertIn(rel, all_paths)
            # 读出来字段对得上
            loaded = self.vault.read_growth(rel)
            self.assertEqual(loaded.dimension, dim)

    # ----- 10: roundtrip (write → read → 一致) -----
    def test_roundtrip_field_consistency(self) -> None:
        """write → read 全部字段一致(含 tuple/list 字段)。"""
        g = _make_growth(
            id="g-roundtrip",
            dimension=Dimension.MORTALITY,
            confidence=0.85,
            source_sessions=("s1", "s2", "s3"),
            dream_level=DreamLevel.DEEP,
            emotional_valence=-0.3,
            emotional_arousal=0.7,
            tags=("死亡", "接受", "已验证"),
            body="多行 body\n第二行\n\n第四行",
        )
        self.vault.write_growth(g)
        loaded = self.vault.read_growth(growth_rel(g.dimension, g.id))

        self.assertEqual(loaded.id, g.id)
        self.assertEqual(loaded.dimension, g.dimension)
        self.assertEqual(loaded.confidence, g.confidence)
        self.assertEqual(loaded.created_at, g.created_at)
        self.assertEqual(loaded.last_validated, g.last_validated)
        self.assertEqual(loaded.source_sessions, g.source_sessions)
        self.assertEqual(loaded.dream_level, g.dream_level)
        self.assertEqual(loaded.emotional_valence, g.emotional_valence)
        self.assertEqual(loaded.emotional_arousal, g.emotional_arousal)
        self.assertEqual(loaded.tags, g.tags)
        self.assertEqual(loaded.body, g.body)

    # ----- 11: 同 ID 重复写 → 覆盖 -----
    def test_same_id_overwrite(self) -> None:
        """同 ID 写第二次,内容被覆盖;read 拿到的是新内容。"""
        g_v1 = _make_growth(
            id="g-overwrite",
            dimension=Dimension.TONE,
            confidence=0.3,
            body="旧内容",
        )
        g_v2 = _make_growth(
            id="g-overwrite",
            dimension=Dimension.TONE,
            confidence=0.9,
            body="新内容",
        )
        self.vault.write_growth(g_v1)
        self.vault.write_growth(g_v2)

        # 文件路径只有一份
        all_paths = self.vault.list_growths()
        self.assertEqual(len(all_paths), 1)
        # 读出来是新内容
        loaded = self.vault.read_growth(growth_rel(Dimension.TONE, "g-overwrite"))
        self.assertEqual(loaded.confidence, 0.9)
        self.assertEqual(loaded.body, "新内容")

    # ----- 12: directory lazy init -----
    def test_directory_lazy_init_on_first_write(self) -> None:
        """write_growth 第一次调用前 mortis-growth/ 不存在;之后才被创建。"""
        # 初始: vault 根只建了 journal,没有 growth 目录
        growth_root = Path(self.tmp) / GROWTH_DIR
        self.assertFalse(growth_root.exists())

        # 第一次 write_growth 触发 lazy init
        g = _make_growth(id="g-lazy", dimension=Dimension.AGENCY)
        self.vault.write_growth(g)

        # 之后 mortis-growth/ + 7 个维度子目录都存在
        self.assertTrue(growth_root.exists())
        for dim_dir in DIMENSION_DIRS.values():
            self.assertTrue((growth_root / dim_dir).is_dir())


if __name__ == "__main__":
    unittest.main()

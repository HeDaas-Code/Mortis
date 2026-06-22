"""Test mortis.steiner.unease — UneaseState + load/save/accumulate/decay。

issue #24 acceptance:
- load_unease:文件不存在 → 全 0 + last_decay=now
- save_unease:写 mortis-steiner/unease.json,whitelist=None
- accumulate:dim 值 +0.15,cap 1.0
- decay:每天 ×0.85,last_decay 更新,低于 0.01 置 0
- frozen dataclass:accumulate/decay 返回新对象
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from mortis.growth.model import Dimension
from mortis.steiner.unease import (
    DECAY_PER_DAY,
    STEINER_DIR,
    UneaseState,
    accumulate,
    decay,
    load_unease,
    save_unease,
)
from mortis.vault.local import Vault


# ============================================================
# fixtures
# ============================================================


@pytest.fixture
def vault_dir() -> Path:
    """空 vault tmp 目录。"""
    with tempfile.TemporaryDirectory(prefix="mortis-steiner-unease-") as td:
        yield Path(td)


# ============================================================
# Test 1-3: UneaseState defaults / accumulate
# ============================================================


class TestUneaseState:
    """UneaseState 默认值 + 访问器。"""

    def test_default_per_dimension_all_zero(self) -> None:
        """新 UneaseState:7 维度全 0。"""
        s = UneaseState()
        assert len(s.per_dimension) == 7
        for dim in Dimension:
            assert s.per_dimension[dim] == 0.0
        # max_unease 0, dim_unease 0
        assert s.max_unease() == 0.0
        assert s.dim_unease(Dimension.IDENTITY) == 0.0

    def test_last_decay_is_now(self) -> None:
        """last_decay 默认是当前 UTC 时间(ISO8601,字符串)。"""
        s = UneaseState()
        parsed = datetime.fromisoformat(s.last_decay)
        assert parsed.tzinfo is not None
        now = datetime.now(tz=timezone.utc)
        assert abs((now - parsed).total_seconds()) < 5

    def test_accumulate_increments_and_caps(self) -> None:
        """accumulate 一次 +0.15;多次 cap 1.0;原对象不变。"""
        s = UneaseState()
        s2 = accumulate(s, Dimension.IDENTITY)
        assert s2.per_dimension[Dimension.IDENTITY] == 0.15
        # 原对象不变(frozen)
        assert s.per_dimension[Dimension.IDENTITY] == 0.0
        # 多次 cap 1.0
        cur = s
        for _ in range(10):
            cur = accumulate(cur, Dimension.VALUES)
        assert cur.per_dimension[Dimension.VALUES] == 1.0


# ============================================================
# Test 4-6: accumulate / decay
# ============================================================


class TestAccumulate:
    """accumulate 行为。"""

    def test_accumulate_does_not_touch_other_dims(self) -> None:
        """accumulate 一个 dim 不影响其他 dim。"""
        s = UneaseState()
        s2 = accumulate(s, Dimension.TONE, delta=0.3)
        assert s2.per_dimension[Dimension.TONE] == 0.3
        for dim in Dimension:
            if dim != Dimension.TONE:
                assert s2.per_dimension[dim] == 0.0

    def test_accumulate_rejects_negative_to_zero(self) -> None:
        """delta 负数不会让值变负(下限 0)。"""
        s = UneaseState(per_dimension={d: 0.1 for d in Dimension})
        s2 = accumulate(s, Dimension.IDENTITY, delta=-1.0)
        assert s2.per_dimension[Dimension.IDENTITY] == 0.0


# ============================================================
# Test 7-8: decay
# ============================================================


class TestDecay:
    """decay 每天 ×0.85。"""

    def test_decay_one_day_multiplies_by_factor(self) -> None:
        """1 天后 = ×0.85。"""
        last = datetime(2026, 6, 22, 10, 0, 0, tzinfo=timezone.utc)
        s = UneaseState(
            per_dimension={d: 0.45 for d in Dimension},
            last_decay=last.isoformat(),
        )
        s2 = decay(s, last + timedelta(days=1))
        for dim in Dimension:
            assert abs(s2.per_dimension[dim] - 0.45 * DECAY_PER_DAY) < 1e-9

    def test_decay_zeroes_small_values(self) -> None:
        """低于 0.01 的维度置 0(30 天后 0.01 → 0.0008 → 0)。"""
        last = datetime(2026, 6, 22, 10, 0, 0, tzinfo=timezone.utc)
        s = UneaseState(
            per_dimension={d: 0.01 for d in Dimension},
            last_decay=last.isoformat(),
        )
        s2 = decay(s, last + timedelta(days=30))
        for dim in Dimension:
            assert s2.per_dimension[dim] == 0.0


# ============================================================
# Test 9-10: load / save round-trip
# ============================================================


class TestLoadSave:
    """load_unease / save_unease round-trip。"""

    def test_load_returns_default_when_file_missing(self, vault_dir: Path) -> None:
        """文件不存在 → 返回全 0 + last_decay=now。"""
        vault = Vault(vault_dir)
        s = load_unease(vault)
        for dim in Dimension:
            assert s.per_dimension[dim] == 0.0

    def test_save_creates_file_and_roundtrip(self, vault_dir: Path) -> None:
        """save 写到 mortis-steiner/unease.json + save/load 一致。"""
        vault = Vault(vault_dir)
        s = UneaseState(
            per_dimension={d: i * 0.1 for i, d in enumerate(Dimension)},
            last_decay="2026-06-22T10:00:00+00:00",
        )
        save_unease(vault, s)
        target = vault_dir / STEINER_DIR / "unease.json"
        assert target.exists()
        # JSON 合法
        json.loads(target.read_text(encoding="utf-8"))
        # round-trip
        loaded = load_unease(vault)
        assert loaded.last_decay == "2026-06-22T10:00:00+00:00"
        for dim in Dimension:
            assert abs(loaded.per_dimension[dim] - s.per_dimension[dim]) < 1e-9

    def test_load_handles_corrupted_json(self, vault_dir: Path) -> None:
        """JSON 损坏 → 返回全 0 + last_decay=now(不抛错)。"""
        vault = Vault(vault_dir)
        target = vault_dir / STEINER_DIR / "unease.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{ not valid json", encoding="utf-8")
        s = load_unease(vault)
        for dim in Dimension:
            assert s.per_dimension[dim] == 0.0

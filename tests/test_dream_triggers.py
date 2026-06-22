"""Test mortis.dream.triggers — Medium/Deep 触发条件。"""

from __future__ import annotations

import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from mortis.dream.phases import DreamLevel
from mortis.dream.triggers import (
    DEEP_INTERVAL_DAYS,
    MEDIUM_INTERVAL_DAYS,
    PENDING_REFLECTIONS_THRESHOLD,
    should_deep_dream,
    should_medium_dream,
)
from mortis.vault import Vault


@pytest.fixture
def vault_dir() -> Path:
    with tempfile.TemporaryDirectory(prefix="mortis-trig-") as td:
        d = Path(td)
        (d / "mortis-journal" / "sub-outputs").mkdir(parents=True)
        (d / "mortis-journal" / "notes").mkdir(parents=True)
        yield d


class TestShouldMediumDream:
    def test_manual_always_true(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        d = should_medium_dream(v, manual=True)
        assert d.should_run is True
        assert d.reason == "manual trigger"

    def test_first_run_always_true(self, vault_dir: Path) -> None:
        """无历史 dream → days=None → interval 条件触发。"""
        v = Vault(vault_dir)
        d = should_medium_dream(v)
        assert d.should_run is True
        assert d.days_since_last is None

    def test_interval_not_met(self, vault_dir: Path) -> None:
        """3 天前刚跑过 → 不该跑。"""
        v = Vault(vault_dir)
        log = vault_dir / "mortis-dream-log" / "medium"
        log.mkdir(parents=True)
        mtime = (datetime.now(tz=timezone.utc) - timedelta(days=3)).timestamp()
        (log / "2026-06-19-medium.md").write_text("past")
        import os
        os.utime(log / "2026-06-19-medium.md", (mtime, mtime))

        d = should_medium_dream(v)
        assert d.should_run is False
        assert "interval" in d.reason

    def test_interval_met(self, vault_dir: Path) -> None:
        """8 天前跑过 → 该跑。"""
        v = Vault(vault_dir)
        log = vault_dir / "mortis-dream-log" / "medium"
        log.mkdir(parents=True)
        mtime = (datetime.now(tz=timezone.utc) - timedelta(days=8)).timestamp()
        f = log / "2026-06-14-medium.md"
        f.write_text("past")
        import os
        os.utime(f, (mtime, mtime))

        d = should_medium_dream(v)
        assert d.should_run is True
        assert d.days_since_last is not None
        assert d.days_since_last >= 7

    def test_pending_reflections(self, vault_dir: Path) -> None:
        """pending ≥ 10 → 该跑。"""
        v = Vault(vault_dir)
        pending = vault_dir / "mortis-subconscious" / "pending-reflections"
        pending.mkdir(parents=True)
        for i in range(10):
            (pending / f"r{i}.md").write_text(f"r{i}")
        d = should_medium_dream(v)
        assert d.should_run is True
        assert d.pending_count == 10


class TestShouldDeepDream:
    def test_manual_always_true(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        d = should_deep_dream(v, manual=True)
        assert d.should_run is True

    def test_interval_default_30(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        # 无历史 → 该跑
        d = should_deep_dream(v)
        assert d.should_run is True

    def test_drift_triggers(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        # 刚跑过 (1 天前) 不该跑
        log = vault_dir / "mortis-dream-log" / "deep"
        log.mkdir(parents=True)
        mtime = (datetime.now(tz=timezone.utc) - timedelta(days=1)).timestamp()
        f = log / "2026-06-21-deep.md"
        f.write_text("past")
        import os
        os.utime(f, (mtime, mtime))

        d = should_deep_dream(v, drift_total=0.8)  # > 0.7
        assert d.should_run is True
        assert "drift" in d.reason

    def test_no_trigger(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        log = vault_dir / "mortis-dream-log" / "deep"
        log.mkdir(parents=True)
        mtime = (datetime.now(tz=timezone.utc) - timedelta(days=5)).timestamp()
        f = log / "2026-06-17-deep.md"
        f.write_text("past")
        import os
        os.utime(f, (mtime, mtime))

        d = should_deep_dream(v, drift_total=0.3)  # < 0.7, 5 < 30
        assert d.should_run is False


class TestConstants:
    def test_medium_interval(self):
        assert MEDIUM_INTERVAL_DAYS == 7

    def test_deep_interval(self):
        assert DEEP_INTERVAL_DAYS == 30

    def test_pending_threshold(self):
        assert PENDING_REFLECTIONS_THRESHOLD == 10

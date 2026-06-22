"""Test mortis.dream.dream_log — 梦境日志写入。"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from mortis.dream.dream_log import (
    DREAM_LOG_DIR,
    DreamLog,
    dream_log_rel,
    write_dream_log,
)
from mortis.dream.phases import DreamLevel, DreamPhase
from mortis.dream.pipeline import DreamResult, PhaseTrace
from mortis.vault import Vault


@pytest.fixture
def vault_dir() -> Path:
    with tempfile.TemporaryDirectory(prefix="mortis-dlog-") as td:
        d = Path(td)
        (d / "mortis-journal" / "sub-outputs").mkdir(parents=True)
        (d / "mortis-journal" / "notes").mkdir(parents=True)
        yield d


def _make_result(level: DreamLevel, ok: bool = True) -> DreamResult:
    r = DreamResult(level=level, traces=[
        PhaseTrace(phase=DreamPhase.RECALL.value, ok=True, detail={"loaded": 3}),
        PhaseTrace(phase=DreamPhase.ASSOCIATE.value, ok=True, detail={"body_len": 50}),
        PhaseTrace(phase=DreamPhase.CRYSTALLIZE.value, ok=ok, detail={"growth_id": "g1"}),
    ])
    return r


class TestDreamLogRel:
    def test_light_path(self):
        rel = dream_log_rel(DreamLevel.LIGHT, "2026-06-22")
        assert rel == "mortis-dream-log/light/2026-06-22-light.md"

    def test_medium_path(self):
        rel = dream_log_rel(DreamLevel.MEDIUM, "2026-06-22")
        assert rel == "mortis-dream-log/medium/2026-06-22-medium.md"

    def test_deep_path(self):
        rel = dream_log_rel(DreamLevel.DEEP, "2026-06-22")
        assert rel == "mortis-dream-log/deep/2026-06-22-deep.md"

    def test_default_today(self):
        rel = dream_log_rel(DreamLevel.LIGHT)
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        assert today in rel


class TestWriteDreamLog:
    def test_write_success(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        result = _make_result(DreamLevel.LIGHT)
        started = datetime(2026, 6, 22, 10, 0, 0, tzinfo=timezone.utc)
        finished = datetime(2026, 6, 22, 10, 0, 30, tzinfo=timezone.utc)
        log = write_dream_log(v, result, started_at=started, finished_at=finished)

        assert isinstance(log, DreamLog)
        assert log.ok is True
        assert log.duration_seconds == 30.0
        # 文件实际写到了
        assert (vault_dir / log.rel_path).exists()
        content = (vault_dir / log.rel_path).read_text(encoding="utf-8")
        assert "level: light" in content
        assert "duration_seconds: 30.00" in content
        assert "ok: true" in content

    def test_write_failure(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        result = _make_result(DreamLevel.MEDIUM, ok=False)
        started = datetime(2026, 6, 22, 10, 0, 0, tzinfo=timezone.utc)
        finished = datetime(2026, 6, 22, 10, 0, 5, tzinfo=timezone.utc)
        log = write_dream_log(
            v, result, started_at=started, finished_at=finished,
            error="LLM timeout",
        )
        assert log.ok is False
        assert log.error == "LLM timeout"
        content = (vault_dir / log.rel_path).read_text(encoding="utf-8")
        assert "error:" in content

    def test_dream_log_dir_constant(self):
        assert DREAM_LOG_DIR == "mortis-dream-log"

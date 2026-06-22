"""Test mortis.toolagent.clock — ClockAgent."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

import pytest

from mortis.toolagent.clock import ClockAgent
from mortis.vault import Vault


@pytest.fixture
def vault_dir() -> Path:
    with tempfile.TemporaryDirectory(prefix="mortis-clock-") as td:
        d = Path(td)
        (d / "mortis-journal" / "sub-outputs").mkdir(parents=True)
        (d / "mortis-journal" / "notes").mkdir(parents=True)
        yield d


class TestClockAgent:
    def test_now_iso(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        agent = ClockAgent(v)
        r = agent.execute({})
        assert r.success is True
        assert "T" in r.data["now"]  # ISO8601 含 T

    def test_no_dream_log(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        agent = ClockAgent(v)
        r = agent.execute({})
        assert r.data["last_dream"] is None

    def test_find_last_dream(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        log = vault_dir / "mortis-dream-log" / "light"
        log.mkdir(parents=True)
        (log / "2026-06-22-light.md").write_text("test dream", encoding="utf-8")
        time.sleep(0.05)
        agent = ClockAgent(v)
        r = agent.execute({})
        assert r.success is True
        assert r.data["last_dream"] is not None
        assert "T" in r.data["last_dream"]

    def test_logical_clock_placeholder(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        agent = ClockAgent(v)
        r = agent.execute({})
        # #26 才实现 — 占位
        assert r.data["logical_clock_phase"] == "unknown"

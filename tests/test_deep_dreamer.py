"""Test mortis.dream.deep — DeepDreamer 7 phase。"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from mortis.dream.deep import DeepDreamer
from mortis.dream.phases import DreamLevel
from mortis.dream.seed_check import seed_check
from mortis.growth.model import Dimension, DreamLevel, Growth
from mortis.provider import MockProvider
from mortis.reflect import clear_emotion_cache
from mortis.seed import Seed
from mortis.vault import Vault


def _make_seed() -> Seed:
    return Seed(
        identity="我是 mortis",
        values="应该注重 owner 体验",
        tone="平和",
        agency="自主决策",
        relations="信任 owner",
        creativity="联想丰富",
        mortality="接受遗忘",
    )


def _write_growth(
    vault: Vault, id: str, body: str, confidence: float = 0.5,
    dim: Dimension = Dimension.IDENTITY,
    last_validated: str | None = None,
    source_sessions: tuple[str, ...] = (),
) -> None:
    lv = last_validated or datetime.now(tz=timezone.utc).isoformat()
    g = Growth(
        id=id, dimension=dim, confidence=confidence,
        created_at=lv, last_validated=lv,
        source_sessions=source_sessions,
        dream_level=DreamLevel.LIGHT,
        emotional_valence=0.0, emotional_arousal=0.0,
        tags=(), body=body,
    )
    vault.write_growth(g)


@pytest.fixture(autouse=True)
def _reset_emotion() -> None:
    clear_emotion_cache()
    yield
    clear_emotion_cache()


@pytest.fixture
def vault_dir() -> Path:
    with tempfile.TemporaryDirectory(prefix="mortis-deep-") as td:
        d = Path(td)
        (d / "mortis-journal" / "sub-outputs").mkdir(parents=True)
        (d / "mortis-journal" / "notes").mkdir(parents=True)
        yield d


def _all_zero_drift() -> str:
    return ('{"identity": 0.0, "values": 0.0, "tone": 0.0, "agency": 0.0, '
            '"relations": 0.0, "creativity": 0.0, "mortality": 0.0}')


class TestDeepDreamer:
    def test_run_empty_vault(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        # Deep 7 phase, RECALL → SEED_CHECK, SEED_CHECK 调 LLM 1 次
        provider = MockProvider(responses=[_all_zero_drift()])
        dreamer = DeepDreamer(v, provider, _make_seed())
        result = dreamer.run()
        assert result.level == DreamLevel.DEEP
        assert result.ok is True
        assert len(result.traces) == 7

    def test_recall_loads_growths(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        _write_growth(v, "g1", "alpha", confidence=0.6)
        _write_growth(v, "g2", "beta", confidence=0.7)
        provider = MockProvider(responses=[_all_zero_drift()])
        dreamer = DeepDreamer(v, provider, _make_seed())
        result = dreamer.run()
        recall = result.trace_for("recall")
        assert recall is not None
        assert recall.detail["active"] == 2

    def test_crystallize_recalibrates_high_conf(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        _write_growth(v, "high", "x", confidence=0.8)
        _write_growth(v, "low", "y", confidence=0.3)
        provider = MockProvider(responses=[_all_zero_drift()])
        dreamer = DeepDreamer(v, provider, _make_seed())
        result = dreamer.run()
        crystal = result.trace_for("crystallize")
        assert crystal is not None
        assert crystal.detail["recalibrated"] == 1  # 只 high 被校准

    def test_erode_archives_low_conf(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        # 100 天前 + 0.05 confidence → erode 后 < 0.1 → archive
        from datetime import timedelta
        old_ts = (datetime.now(tz=timezone.utc) - timedelta(days=100)).isoformat()
        _write_growth(v, "old-low", "x", confidence=0.05, last_validated=old_ts)
        _write_growth(v, "fresh-high", "y", confidence=0.9)
        provider = MockProvider(responses=[_all_zero_drift()])
        dreamer = DeepDreamer(v, provider, _make_seed())
        result = dreamer.run()

        erode = result.trace_for("erode")
        assert erode is not None
        assert "old-low" in erode.detail["archived_ids"]
        # 原文件已被移走 (但 archive/ 副本存在)
        archived = list((vault_dir / "mortis-growth" / "archive").rglob("*.md"))
        assert len(archived) >= 1

    def test_seed_check_writes_notify_when_drift_high(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        _write_growth(v, "g1", "x")
        # drift > 0.7 → needs_owner_notify
        high_drift = (
            '{"identity": 0.9, "values": 0.0, "tone": 0.0, "agency": 0.0, '
            '"relations": 0.0, "creativity": 0.0, "mortality": 0.0}'
        )
        provider = MockProvider(responses=[high_drift])
        dreamer = DeepDreamer(v, provider, _make_seed(), drift_threshold=0.7)
        result = dreamer.run()

        sc = result.trace_for("seed_check")
        assert sc is not None
        assert sc.detail["needs_owner_notify"] is True
        # 写 owner-notify.json
        notify = vault_dir / "mortis-subconscious" / "owner-notify.json"
        assert notify.exists()
        assert "needs_notify" in notify.read_text(encoding="utf-8")

    def test_seed_check_no_notify_when_low_drift(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        _write_growth(v, "g1", "x")
        provider = MockProvider(responses=[_all_zero_drift()])
        dreamer = DeepDreamer(v, provider, _make_seed())
        result = dreamer.run()

        sc = result.trace_for("seed_check")
        assert sc.detail["needs_owner_notify"] is False
        # 不写 notify
        notify = vault_dir / "mortis-subconscious" / "owner-notify.json"
        assert not notify.exists()

    def test_reconcile_handles_mutex(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        # 旧高 conf + 旧低 conf 同维度 + mutex
        _write_growth(v, "hi", "应该信任", confidence=0.8, dim=Dimension.VALUES)
        _write_growth(v, "lo", "不该信任", confidence=0.4, dim=Dimension.VALUES)
        provider = MockProvider(responses=[_all_zero_drift()])
        dreamer = DeepDreamer(v, provider, _make_seed())
        result = dreamer.run()

        reconcile = result.trace_for("reconcile")
        assert reconcile is not None
        assert reconcile.detail["conflicts"] >= 1

    def test_run_level_deep(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        provider = MockProvider(responses=[_all_zero_drift()])
        dreamer = DeepDreamer(v, provider, _make_seed())
        assert dreamer.level == DreamLevel.DEEP

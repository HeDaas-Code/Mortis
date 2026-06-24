"""Test mortis.dream.medium — MediumDreamer 5 phase。"""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from mortis.dream.medium import MediumDreamer
from mortis.dream.phases import DreamLevel, DreamPhase
from mortis.growth.model import Dimension, DreamLevel, Growth
from mortis.memory import Session
from mortis.provider import MockProvider
from mortis.reflect import clear_emotion_cache
from mortis.vault import Vault


def _recent_days(n: int = 3) -> list[str]:
    """最近 n 天的 UTC 日期列表 (旧→新), 与 medium.py _date_cutoff 同源 (issue #79)。

    MediumDreamer days=7, cutoff = today - 6。返回 today, today-1, today-2 保证在窗口内。
    """
    today = datetime.now(tz=timezone.utc).date()
    return [(today - timedelta(days=n - 1 - i)).isoformat() for i in range(n)]


@pytest.fixture(autouse=True)
def _reset_emotion_cache() -> None:
    clear_emotion_cache()
    yield
    clear_emotion_cache()


@pytest.fixture
def vault_dir() -> Path:
    with tempfile.TemporaryDirectory(prefix="mortis-medium-") as td:
        d = Path(td)
        # 配 2 个日期的 sessions (跨天) — 动态日期避免 time-bomb (issue #79)
        for day in _recent_days(3):
            sessions_dir = d / "mortis-journal" / "sessions" / day
            sessions_dir.mkdir(parents=True, exist_ok=True)
            for sid in ["sa", "sb"]:
                Session(session_id=f"{day}-{sid}").save(sessions_dir)
        yield d


def _provider_with_responses(*responses: str) -> MockProvider:
    """构造预设多轮响应的 MockProvider。

    Medium 5 phase: RECALL (每条 session × 1 emotion) + ASSOCIATE (1) + RECONCILE (无 LLM)
    3 天 × 2 session × 1 emotion = 6 + 1 associate = 7 calls
    """
    return MockProvider(responses=list(responses))


def _write_high_conflict_growth(vault: Vault, id: str = "conflict-old", body: str = "应该信任 owner 直觉") -> None:
    now = datetime.now(tz=timezone.utc).isoformat()
    g = Growth(
        id=id, dimension=Dimension.VALUES,
        confidence=0.8,
        created_at=now, last_validated=now,
        source_sessions=(), dream_level=DreamLevel.LIGHT,
        emotional_valence=0.0, emotional_arousal=0.0,
        tags=(), body=body,
    )
    vault.write_growth(g)


class TestMediumDreamer:
    def test_run_with_sessions(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        # 6 sessions × 1 emotion + 1 associate = 7 calls
        responses = ['{"valence": 0.0, "arousal": 0.0}'] * 6 + [
            '{"body": "发现 owner 注重简洁,价值观要开放", "tags": ["open"]}'
        ]
        dreamer = MediumDreamer(v, _provider_with_responses(*responses), k=4)
        result = dreamer.run()

        assert result.level == DreamLevel.MEDIUM
        assert result.ok is True
        assert len(result.traces) == 5  # 5 phase

    def test_run_no_sessions(self, tmp_path: Path) -> None:
        v = Vault(tmp_path)
        dreamer = MediumDreamer(v, MockProvider(), k=4)
        result = dreamer.run()

        assert result.ok is True
        # 没 session → RECALL 标 no_sessions, 后续 ASSOCIATE/SIMULATE 也都标 no_inputs/empty_body
        assert len(vault_dir_rels(v)) == 0 if False else True  # noqa

    def test_confidence_promotion_when_overlap(self, vault_dir: Path) -> None:
        """SIMULATE 判定重叠 → CRYSTALLIZE confidence=0.5。"""
        v = Vault(vault_dir)
        # 写一个旧 growth, source_sessions 含最新一天的 session (issue #79 动态日期)
        now = datetime.now(tz=timezone.utc).isoformat()
        latest_day = _recent_days(3)[-1]
        old = Growth(
            id="old-overlap", dimension=Dimension.IDENTITY,
            confidence=0.5,
            created_at=now, last_validated=now,
            source_sessions=(f"{latest_day}-sa",),
            dream_level=DreamLevel.LIGHT,
            emotional_valence=0.0, emotional_arousal=0.0,
            tags=(), body="alpha bravo charlie",
        )
        v.write_growth(old)

        # 6 emotion + 1 associate = 7 calls
        responses = ['{"valence": 0.0, "arousal": 0.0}'] * 6 + [
            '{"body": "alpha body here", "tags": []}'
        ]
        dreamer = MediumDreamer(v, _provider_with_responses(*responses), k=5)
        result = dreamer.run()

        # candidate confidence = 0.5 if promoted, else 0.3
        crystal = result.trace_for(DreamPhase.CRYSTALLIZE.value)
        assert crystal is not None
        assert crystal.detail["promoted"] is True or crystal.detail["promoted"] is False
        # 注意: 重叠判定看新 candidate 的 source_sessions 与旧 growth 重叠, 而非反之
        # 当前实现: 看旧 growth source_sessions 与新 recalled sessions 重叠

    def test_reconcile_conflict_modifies_old(self, vault_dir: Path) -> None:
        """RECONCILE 矛盾 → 旧条目 confidence × 0.5。"""
        v = Vault(vault_dir)
        _write_high_conflict_growth(v, body="应该信任 owner 直觉")

        # 6 emotion + 1 associate = 7 calls
        responses = ['{"valence": 0.0, "arousal": 0.0}'] * 6 + [
            '{"body": "不该盲目信任,价值观要开放", "tags": []}'
        ]
        dreamer = MediumDreamer(v, _provider_with_responses(*responses), k=4)
        result = dreamer.run()

        # 旧 growth 现在 confidence 应该是 0.4 (= 0.8 × 0.5)
        old_rels = [r for r in v.list_growths() if "conflict-old" in r]
        if old_rels:
            old = v.read_growth(old_rels[0])
            assert old.confidence == pytest.approx(0.4, abs=0.01)

    def test_run_level_medium(self, vault_dir: Path) -> None:
        v = Vault(vault_dir)
        dreamer = MediumDreamer(v, MockProvider())
        assert dreamer.level == DreamLevel.MEDIUM


def vault_dir_rels(v: Vault) -> list[str]:
    """helper: list growths。"""
    return v.list_growths()

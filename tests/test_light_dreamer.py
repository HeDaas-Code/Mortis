"""Test mortis.dream.light — LightDreamer 4 phase 完整流程。issue #22 验收 #3。"""

from __future__ import annotations

import random
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from mortis.dream.light import LightDreamer, Conflict
from mortis.dream.phases import DreamLevel, DreamPhase
from mortis.dream.crystallize import reset_counter
from mortis.memory import Session
from mortis.provider import MockProvider
from mortis.reflect import clear_emotion_cache
from mortis.vault import Vault


def _today() -> str:
    """UTC today — 与 light.py _date_cutoff() 同源, 避免 time-bomb (issue #78)。"""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


# ============================================================
# fixtures
# ============================================================


@pytest.fixture
def vault_dir() -> Path:
    """每次测试一个 tmp 目录 + 配好 2 个 session。"""
    with tempfile.TemporaryDirectory(prefix="mortis-dream-") as td:
        d = Path(td)
        sessions_dir = d / "mortis-journal" / "sessions" / _today()
        sessions_dir.mkdir(parents=True, exist_ok=True)
        s1 = Session(session_id="session-a", threads=["th-1"])
        s1.save(sessions_dir)
        s2 = Session(session_id="session-b", threads=["th-2"])
        s2.save(sessions_dir)
        yield d


@pytest.fixture(autouse=True)
def _reset_state() -> None:
    """每个测试前后清空 emotion cache + dream id counter。"""
    clear_emotion_cache()
    reset_counter()
    yield
    clear_emotion_cache()
    reset_counter()


def _make_provider(emotion_responses: list[str], associate_response: str = "") -> MockProvider:
    """构造 MockProvider: RECALL 阶段每条 session 调一次 emotion + ASSOCIATE 调一次。"""
    return MockProvider(responses=[
        *emotion_responses,
        associate_response or '{"body": "今天发现 owner 注重结论先行", "tags": ["结论", "owner"]}',
    ])


# ============================================================
# 主流程
# ============================================================


class TestRunEndToEnd:
    """完整 run → 写盘 → 读回 流程。"""

    def test_run_with_no_sessions(self, tmp_path: Path) -> None:
        """无 session(vault 里没 sessions 目录) → 4 phase 全 ok,no_sessions 标。"""
        vault = Vault(tmp_path)
        provider = MockProvider()  # 不会真调 LLM(没进 RECALL)
        dreamer = LightDreamer(vault, provider)
        result = dreamer.run()

        assert result.ok is True  # 4 phase 都标 ok=True
        assert result.level == DreamLevel.LIGHT
        assert len(result.traces) == 4
        # 没有 candidate
        assert result.candidates == []
        assert result.conflicts == []
        # vault 里不应有 growth 文件
        assert vault.list_growths() == []

    def test_run_with_sessions_writes_candidate(self, vault_dir: Path) -> None:
        """有 session → 4 phase → 写一个 confidence=0.3 growth 候选。"""
        vault = Vault(vault_dir)
        provider = _make_provider(
            emotion_responses=['{"valence": 0.5, "arousal": 0.5}'] * 2,
            associate_response='{"body": "owner 注重简洁", "tags": ["简洁"]}',
        )
        dreamer = LightDreamer(vault, provider, k=2)
        result = dreamer.run()

        assert result.ok is True
        # 写了一个 growth 候选
        growths = vault.list_growths()
        assert len(growths) == 1
        rel = growths[0]
        assert rel.startswith("mortis-growth/")
        assert rel.endswith(".md")

        # 读回
        g = vault.read_growth(rel)
        assert g.confidence == 0.3
        assert g.dream_level == DreamLevel.LIGHT
        assert "简洁" in g.body or "owner" in g.body or "注重" in g.body

    def test_run_id_format(self, vault_dir: Path) -> None:
        """candidate id: dream-YYYY-MM-DD-NNN。"""
        vault = Vault(vault_dir)
        provider = _make_provider(
            ['{"valence": 0.0, "arousal": 0.0}'] * 2,
        )
        dreamer = LightDreamer(vault, provider, k=2)
        dreamer.run()

        growths = vault.list_growths()
        assert len(growths) == 1
        g = vault.read_growth(growths[0])
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        assert g.id == f"dream-{today}-001"

    def test_run_with_only_one_session(self, vault_dir: Path) -> None:
        """单 session 也能跑(只 load 1 条)。"""
        # 删掉 session-b
        (vault_dir / "mortis-journal" / "sessions" / _today() / "session-b.json").unlink()

        vault = Vault(vault_dir)
        provider = _make_provider(
            ['{"valence": 0.3, "arousal": 0.3}'],
            '{"body": "single session", "tags": []}',
        )
        dreamer = LightDreamer(vault, provider, k=2)  # k=2 但只有 1 session
        result = dreamer.run()

        assert result.ok is True
        assert len(vault.list_growths()) == 1


# ============================================================
# RECONCILE — 不影响旧 growth
# ============================================================


class TestReconcileNonDestructive:
    """RECONCILE 只检测冲突,不修改旧 growth 文件。"""

    def test_reconcile_no_existing_growths(self, vault_dir: Path) -> None:
        """无旧 growth → RECONCILE ok 标 0 conflicts。"""
        vault = Vault(vault_dir)
        provider = _make_provider(['{"valence": 0.0, "arousal": 0.0}'] * 2)
        dreamer = LightDreamer(vault, provider, k=2)
        result = dreamer.run()

        reconcile = result.trace_for("reconcile")
        assert reconcile.ok is True
        assert reconcile.detail.get("conflicts") == 0

    def test_reconcile_no_conflict_when_low_confidence_existing(self, vault_dir: Path) -> None:
        """旧 growth confidence < 0.5 → 不报冲突。"""
        from mortis.growth.model import Dimension, DreamLevel, Growth
        vault = Vault(vault_dir)
        # 先手动写一个低 confidence 旧 growth (含 mutex 关键词)
        old = Growth(
            id="old-low-conf",
            dimension=Dimension.VALUES,
            confidence=0.3,
            created_at="2026-06-21T00:00:00",
            last_validated="2026-06-21T00:00:00",
            source_sessions=(),
            dream_level=None,
            emotional_valence=0.0,
            emotional_arousal=0.0,
            tags=(),
            body="应该注重代码质量",  # 含 "应该"
        )
        vault.write_growth(old)

        # 跑梦,候选含 "不该"
        provider = _make_provider(
            ['{"valence": 0.0, "arousal": 0.0}'] * 2,
            '{"body": "不该过度设计", "tags": []}',
        )
        dreamer = LightDreamer(vault, provider, k=2)
        result = dreamer.run()

        reconcile = result.trace_for("reconcile")
        assert reconcile.detail.get("conflicts") == 0

        # 旧 growth 内容未被改
        old_rels = [r for r in vault.list_growths() if "old-low-conf" in r]
        assert len(old_rels) == 1
        old_g = vault.read_growth(old_rels[0])
        assert old_g.confidence == 0.3  # 没被提升
        assert "应该注重代码质量" in old_g.body  # 内容未改

    def test_reconcile_detects_mutex_conflict(self, vault_dir: Path) -> None:
        """同维度 + 高 confidence 旧 growth + mutex 关键词 → 报冲突。"""
        from mortis.growth.model import Dimension, DreamLevel, Growth
        vault = Vault(vault_dir)
        # 写一个高 confidence 旧 growth (含 "应该")
        old = Growth(
            id="old-high-conf",
            dimension=Dimension.VALUES,
            confidence=0.8,
            created_at="2026-06-21T00:00:00",
            last_validated="2026-06-21T00:00:00",
            source_sessions=(),
            dream_level=None,
            emotional_valence=0.0,
            emotional_arousal=0.0,
            tags=(),
            body="应该信任 owner 的直觉",
        )
        vault.write_growth(old)

        # 候选含 "不该" + VALUES 关键词 (同时确保同维度)
        provider = _make_provider(
            ['{"valence": 0.0, "arousal": 0.0}'] * 2,
            '{"body": "不该盲目信任,价值观要更开放", "tags": []}',
        )
        dreamer = LightDreamer(vault, provider, k=2)
        result = dreamer.run()

        reconcile = result.trace_for("reconcile")
        assert reconcile.detail.get("conflicts") == 1

        # 旧 growth confidence 不变(0.8)
        old_rels = [r for r in vault.list_growths() if "old-high-conf" in r]
        old_g = vault.read_growth(old_rels[0])
        assert old_g.confidence == 0.8

        # conflict 文件写到 mortis-subconscious/conflicts/
        conflict_files = list(
            (vault_dir / "mortis-subconscious" / "conflicts").glob("*.md")
        )
        assert len(conflict_files) == 1
        content = conflict_files[0].read_text(encoding="utf-8")
        assert "old-high-conf" in content
        assert "should" in content or "该" in content  # 候选 body 片段


# ============================================================
# 错误兜底
# ============================================================


class TestErrors:
    """空响应 / parse 失败 → 不崩,跑完。"""

    def test_empty_associate_response(self, vault_dir: Path) -> None:
        """ASSOCIATE 返回空 → 不写 candidate,跑完不崩。"""
        vault = Vault(vault_dir)
        provider = MockProvider(responses=[
            '{"valence": 0.0, "arousal": 0.0}',
            '{"valence": 0.0, "arousal": 0.0}',
            "",  # associate empty
        ])
        dreamer = LightDreamer(vault, provider, k=2)
        result = dreamer.run()

        assert result.ok is True
        assert vault.list_growths() == []  # 没写


# ============================================================
# Emotion cache 集成
# ============================================================


class TestEmotionCacheIntegration:
    """emotion 缓存按 session_path 命中,不被 dreamer 重复调用。"""

    def test_emotion_called_once_per_session(self, vault_dir: Path) -> None:
        """k=2, RECALL 阶段 emotion 调 2 次(2 sessions × 1 each)。"""
        vault = Vault(vault_dir)
        # 2 sessions × 1 emotion + 1 associate = 3 calls total
        provider = MockProvider(responses=[
            '{"valence": 0.5, "arousal": 0.5}',
            '{"valence": -0.3, "arousal": 0.7}',
            '{"body": "发现 owner 注重简洁", "tags": []}',
        ])
        dreamer = LightDreamer(vault, provider, k=2)
        dreamer.run()

        assert provider._call_count == 3


# ============================================================
# Path helpers
# ============================================================


class TestVaultWrites:
    """写盘位置 + 格式校验。"""

    def test_candidate_under_growth_dir(self, vault_dir: Path) -> None:
        """candidate 写在 mortis-growth/<dimension>/<id>.md。"""
        vault = Vault(vault_dir)
        provider = _make_provider(['{"valence": 0.0, "arousal": 0.0}'] * 2)
        dreamer = LightDreamer(vault, provider, k=2)
        dreamer.run()

        growths = vault.list_growths()
        assert len(growths) == 1
        rel = growths[0]
        assert rel.startswith("mortis-growth/")
        assert rel.endswith(".md")
        # dimension 子目录存在
        assert "/" in rel[len("mortis-growth/"):]  # 至少一层子目录

    def test_conflict_under_subconscious(self, vault_dir: Path) -> None:
        """conflict 写在 mortis-subconscious/conflicts/<candidate_id>.md。"""
        from mortis.growth.model import Dimension, Growth

        vault = Vault(vault_dir)
        old = Growth(
            id="old-conf",
            dimension=Dimension.IDENTITY,
            confidence=0.8,
            created_at="2026-06-21T00:00:00",
            last_validated="2026-06-21T00:00:00",
            source_sessions=(),
            dream_level=None,
            emotional_valence=0.0,
            emotional_arousal=0.0,
            tags=(),
            body="必须相信直觉",
        )
        vault.write_growth(old)

        provider = _make_provider(
            ['{"valence": 0.0, "arousal": 0.0}'] * 2,
            '{"body": "不必相信直觉", "tags": []}',
        )
        dreamer = LightDreamer(vault, provider, k=2)
        dreamer.run()

        conflicts_dir = vault_dir / "mortis-subconscious" / "conflicts"
        assert conflicts_dir.exists()
        conflicts = list(conflicts_dir.glob("*.md"))
        assert len(conflicts) == 1
        assert conflicts[0].name.startswith("dream-")
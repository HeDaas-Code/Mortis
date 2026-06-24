"""Test mortis.dream.drift_log — drift 历史日志 + 误报率统计 (issue #48)。

issue #48: 记录每次 seed_check 结果到 mortis-subconscious/drift-log.json,
计算 false_positive_rate, 让 owner 可以校准阈值。

测试覆盖:
- log_drift 写入文件 (追加, 不覆盖)
- read_drift_log 读取
- drift_stats 统计正确 (total / notified / dismissed / false_positive_rate / avg_score)
- dismiss_drift 标记误报
- 空日志返回空列表 / 默认统计
- seed_check 集成: 传 vault 时自动记录
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from mortis.dream.drift_log import (
    DRIFT_LOG_FILE,
    DRIFT_LOG_SUBDIR,
    dismiss_drift,
    drift_stats,
    log_drift,
    read_drift_log,
)
from mortis.dream.seed_check import seed_check
from mortis.growth.model import Dimension
from mortis.provider import MockProvider
from mortis.seed import Seed
from mortis.vault import Vault


@pytest.fixture
def vault_dir() -> Path:
    with tempfile.TemporaryDirectory(prefix="mortis-drift-") as td:
        d = Path(td)
        (d / "mortis-journal" / "sub-outputs").mkdir(parents=True)
        (d / "mortis-journal" / "notes").mkdir(parents=True)
        yield d


def _make_vault(vault_dir: Path) -> Vault:
    return Vault(vault_dir)


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


def _all_zero_drift() -> str:
    return (
        '{"identity": 0.0, "values": 0.0, "tone": 0.0, "agency": 0.0, '
        '"relations": 0.0, "creativity": 0.0, "mortality": 0.0}'
    )


# ============================================================
# log_drift — 写入
# ============================================================


class TestLogDrift:
    def test_writes_single_entry(self, vault_dir: Path) -> None:
        """log_drift 写入一条记录到 drift-log.json。"""
        v = _make_vault(vault_dir)
        log_drift(v, drift_score=0.8, threshold=0.75, notified=True)

        log_path = vault_dir / DRIFT_LOG_SUBDIR / DRIFT_LOG_FILE
        assert log_path.exists()
        entries = json.loads(log_path.read_text(encoding="utf-8"))
        assert len(entries) == 1
        e = entries[0]
        assert e["drift_score"] == 0.8
        assert e["threshold"] == 0.75
        assert e["notified"] is True
        assert e["dismissed"] is False
        assert "timestamp" in e

    def test_appends_not_overwrites(self, vault_dir: Path) -> None:
        """多次 log_drift 追加, 不覆盖已有记录。"""
        v = _make_vault(vault_dir)
        log_drift(v, drift_score=0.1, threshold=0.7, notified=False)
        log_drift(v, drift_score=0.9, threshold=0.7, notified=True)
        log_drift(v, drift_score=0.5, threshold=0.7, notified=False)

        entries = read_drift_log(v)
        assert len(entries) == 3
        assert entries[0]["drift_score"] == 0.1
        assert entries[1]["drift_score"] == 0.9
        assert entries[2]["drift_score"] == 0.5

    def test_creates_subdir_if_missing(self, vault_dir: Path) -> None:
        """mortis-subconscious/ 目录不存在时自动创建。"""
        v = _make_vault(vault_dir)
        subdir = vault_dir / DRIFT_LOG_SUBDIR
        assert not subdir.exists()
        log_drift(v, drift_score=0.3, threshold=0.7, notified=False)
        assert subdir.exists()
        assert (subdir / DRIFT_LOG_FILE).exists()

    def test_entry_fields_complete(self, vault_dir: Path) -> None:
        """每条记录含 5 个字段: timestamp, drift_score, threshold, notified, dismissed。"""
        v = _make_vault(vault_dir)
        log_drift(v, drift_score=0.6, threshold=0.7, notified=False)
        entries = read_drift_log(v)
        assert set(entries[0].keys()) == {
            "timestamp", "drift_score", "threshold", "notified", "dismissed",
        }

    def test_timestamp_is_iso_utc(self, vault_dir: Path) -> None:
        """timestamp 是 ISO8601 UTC 格式 (含时区信息)。"""
        v = _make_vault(vault_dir)
        log_drift(v, drift_score=0.2, threshold=0.7, notified=False)
        entries = read_drift_log(v)
        ts = entries[0]["timestamp"]
        # ISO8601 with timezone — datetime.fromisoformat 能解析
        from datetime import datetime
        dt = datetime.fromisoformat(ts)
        assert dt.tzinfo is not None


# ============================================================
# read_drift_log — 读取
# ============================================================


class TestReadDriftLog:
    def test_read_returns_entries(self, vault_dir: Path) -> None:
        """读取已写入的日志条目。"""
        v = _make_vault(vault_dir)
        log_drift(v, drift_score=0.4, threshold=0.7, notified=False)
        log_drift(v, drift_score=0.8, threshold=0.7, notified=True)
        entries = read_drift_log(v)
        assert len(entries) == 2
        assert entries[0]["drift_score"] == 0.4
        assert entries[1]["drift_score"] == 0.8

    def test_read_empty_when_no_file(self, vault_dir: Path) -> None:
        """文件不存在 → 返回空列表。"""
        v = _make_vault(vault_dir)
        assert read_drift_log(v) == []

    def test_read_empty_when_corrupt_json(self, vault_dir: Path) -> None:
        """文件损坏 (非法 JSON) → 返回空列表, 不抛错。"""
        v = _make_vault(vault_dir)
        log_dir = vault_dir / DRIFT_LOG_SUBDIR
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / DRIFT_LOG_FILE).write_text("not valid json {{{", encoding="utf-8")
        assert read_drift_log(v) == []


# ============================================================
# drift_stats — 统计
# ============================================================


class TestDriftStats:
    def test_empty_stats(self, vault_dir: Path) -> None:
        """无日志 → 全 0 统计, false_positive_rate=0。"""
        v = _make_vault(vault_dir)
        stats = drift_stats(v)
        assert stats["total"] == 0
        assert stats["notified"] == 0
        assert stats["dismissed"] == 0
        assert stats["false_positive_rate"] == 0
        assert stats["avg_score"] == 0

    def test_basic_stats(self, vault_dir: Path) -> None:
        """3 条记录: 2 notified, 1 not → notified=2, total=3。"""
        v = _make_vault(vault_dir)
        log_drift(v, drift_score=0.1, threshold=0.7, notified=False)
        log_drift(v, drift_score=0.8, threshold=0.7, notified=True)
        log_drift(v, drift_score=0.9, threshold=0.7, notified=True)
        stats = drift_stats(v)
        assert stats["total"] == 3
        assert stats["notified"] == 2
        assert stats["dismissed"] == 0
        assert stats["false_positive_rate"] == 0  # 无 dismissed

    def test_avg_score(self, vault_dir: Path) -> None:
        """avg_score = 平均 drift_score, 保留 3 位小数。"""
        v = _make_vault(vault_dir)
        log_drift(v, drift_score=0.0, threshold=0.7, notified=False)
        log_drift(v, drift_score=0.6, threshold=0.7, notified=False)
        log_drift(v, drift_score=0.9, threshold=0.7, notified=True)
        stats = drift_stats(v)
        # (0.0 + 0.6 + 0.9) / 3 = 0.5
        assert stats["avg_score"] == 0.5

    def test_false_positive_rate(self, vault_dir: Path) -> None:
        """2 notified, 1 dismissed → false_positive_rate = 0.5。"""
        v = _make_vault(vault_dir)
        log_drift(v, drift_score=0.1, threshold=0.7, notified=False)  # index 0
        log_drift(v, drift_score=0.8, threshold=0.7, notified=True)   # index 1
        log_drift(v, drift_score=0.9, threshold=0.7, notified=True)   # index 2
        # 标记 index 1 为误报
        dismiss_drift(v, index=1)
        stats = drift_stats(v)
        assert stats["notified"] == 2
        assert stats["dismissed"] == 1
        assert stats["false_positive_rate"] == 0.5

    def test_false_positive_rate_zero_when_no_notified(self, vault_dir: Path) -> None:
        """无 notified 记录 → false_positive_rate = 0 (不除零)。"""
        v = _make_vault(vault_dir)
        log_drift(v, drift_score=0.1, threshold=0.7, notified=False)
        log_drift(v, drift_score=0.2, threshold=0.7, notified=False)
        stats = drift_stats(v)
        assert stats["notified"] == 0
        assert stats["false_positive_rate"] == 0


# ============================================================
# dismiss_drift — 标记误报
# ============================================================


class TestDismissDrift:
    def test_dismiss_marks_entry(self, vault_dir: Path) -> None:
        """dismiss_drift 把指定条目的 dismissed 设为 True。"""
        v = _make_vault(vault_dir)
        log_drift(v, drift_score=0.8, threshold=0.7, notified=True)  # index 0
        log_drift(v, drift_score=0.9, threshold=0.7, notified=True)  # index 1

        result = dismiss_drift(v, index=0)
        assert result is True
        entries = read_drift_log(v)
        assert entries[0]["dismissed"] is True
        assert entries[1]["dismissed"] is False

    def test_dismiss_persists_to_file(self, vault_dir: Path) -> None:
        """dismiss 后重新读取文件, dismissed 状态已持久化。"""
        v = _make_vault(vault_dir)
        log_drift(v, drift_score=0.85, threshold=0.7, notified=True)
        dismiss_drift(v, index=0)

        # 重新构造 vault 读 (模拟重启)
        v2 = _make_vault(vault_dir)
        entries = read_drift_log(v2)
        assert entries[0]["dismissed"] is True

    def test_dismiss_invalid_index_returns_false(self, vault_dir: Path) -> None:
        """越界索引 → 返回 False, 不抛错。"""
        v = _make_vault(vault_dir)
        log_drift(v, drift_score=0.8, threshold=0.7, notified=True)
        assert dismiss_drift(v, index=5) is False
        assert dismiss_drift(v, index=-1) is False

    def test_dismiss_empty_log_returns_false(self, vault_dir: Path) -> None:
        """空日志 dismiss → False。"""
        v = _make_vault(vault_dir)
        assert dismiss_drift(v, index=0) is False

    def test_dismiss_only_affects_target(self, vault_dir: Path) -> None:
        """dismiss index 1 不影响 index 0 和 2。"""
        v = _make_vault(vault_dir)
        log_drift(v, drift_score=0.1, threshold=0.7, notified=False)  # 0
        log_drift(v, drift_score=0.8, threshold=0.7, notified=True)   # 1
        log_drift(v, drift_score=0.9, threshold=0.7, notified=True)   # 2
        dismiss_drift(v, index=1)
        entries = read_drift_log(v)
        assert entries[0]["dismissed"] is False
        assert entries[1]["dismissed"] is True
        assert entries[2]["dismissed"] is False


# ============================================================
# seed_check 集成 — 传 vault 时自动记录
# ============================================================


class TestSeedCheckDriftLogIntegration:
    def test_seed_check_logs_when_vault_provided(self, vault_dir: Path) -> None:
        """seed_check 传 vault → drift-log.json 写入一条记录。"""
        v = _make_vault(vault_dir)
        provider = MockProvider(responses=[_all_zero_drift()])
        report = seed_check(
            seed=_make_seed(),
            growth_summary="test",
            provider=provider,
            vault=v,
        )
        entries = read_drift_log(v)
        assert len(entries) == 1
        assert entries[0]["drift_score"] == report.total_drift
        assert entries[0]["threshold"] == report.threshold
        assert entries[0]["notified"] is report.needs_owner_notify
        assert entries[0]["dismissed"] is False

    def test_seed_check_no_log_when_vault_none(self, vault_dir: Path) -> None:
        """seed_check 不传 vault → 不写 drift-log.json (向后兼容)。"""
        v = _make_vault(vault_dir)
        provider = MockProvider(responses=[_all_zero_drift()])
        seed_check(seed=_make_seed(), growth_summary="test", provider=provider)
        log_path = vault_dir / DRIFT_LOG_SUBDIR / DRIFT_LOG_FILE
        assert not log_path.exists()

    def test_seed_check_high_drift_logged_as_notified(self, vault_dir: Path) -> None:
        """drift > threshold → notified=True 写入日志。"""
        v = _make_vault(vault_dir)
        high_drift = (
            '{"identity": 0.9, "values": 0.0, "tone": 0.0, "agency": 0.0, '
            '"relations": 0.0, "creativity": 0.0, "mortality": 0.0}'
        )
        provider = MockProvider(responses=[high_drift])
        seed_check(
            seed=_make_seed(),
            growth_summary="test",
            provider=provider,
            threshold=0.7,
            vault=v,
        )
        entries = read_drift_log(v)
        assert len(entries) == 1
        assert entries[0]["notified"] is True
        assert entries[0]["drift_score"] == 0.9

    def test_seed_check_return_value_unchanged(self, vault_dir: Path) -> None:
        """传 vault 不改变 seed_check 的返回值 (DriftReport)。"""
        v = _make_vault(vault_dir)
        provider = MockProvider(responses=[_all_zero_drift()])
        report = seed_check(
            seed=_make_seed(),
            growth_summary="test",
            provider=provider,
            vault=v,
        )
        assert report.total_drift == 0.0
        assert report.needs_owner_notify is False
        assert set(report.per_dimension.keys()) == set(Dimension)

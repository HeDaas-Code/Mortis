"""Drift 历史日志 — 记录每次 seed_check 结果，计算误报率。

issue #48: DeepDreamer 的 SEED_CHECK 用 LLM 评估 growth 与 seed 的 drift,
但可能产生误报。本模块记录 drift 历史, 计算 false_positive_rate, 让 owner
可以校准阈值。

文件位置: mortis-subconscious/drift-log.json
格式: [{"timestamp": "...", "drift_score": 0.8, "threshold": 0.75, "notified": true, "dismissed": false}]
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from mortis.vault import Vault


DRIFT_LOG_SUBDIR = "mortis-subconscious"
DRIFT_LOG_FILE = "drift-log.json"


def log_drift(vault: Vault, drift_score: float, threshold: float, notified: bool) -> None:
    """记录一次 drift 检测结果。

    Args:
        vault: vault 根 (日志写到 vault.root / mortis-subconscious / drift-log.json)。
        drift_score: 本次 drift 总分 (0.0-1.0)。
        threshold: 触发 owner 通知的阈值。
        notified: 是否触发了 owner 通知 (drift_score > threshold)。
    """
    log_dir = vault.root / DRIFT_LOG_SUBDIR
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / DRIFT_LOG_FILE

    entries: list[dict] = []
    if log_path.exists():
        try:
            entries = json.loads(log_path.read_text(encoding="utf-8"))
        except Exception:
            entries = []

    entries.append({
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "drift_score": drift_score,
        "threshold": threshold,
        "notified": notified,
        "dismissed": False,  # owner 可后续标记为误报
    })

    log_path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")


def read_drift_log(vault: Vault) -> list[dict]:
    """读取 drift 历史日志。

    Returns:
        日志条目列表 (按写入顺序)。文件不存在或损坏 → 空列表。
    """
    log_path = vault.root / DRIFT_LOG_SUBDIR / DRIFT_LOG_FILE
    if not log_path.exists():
        return []
    try:
        return json.loads(log_path.read_text(encoding="utf-8"))
    except Exception:
        return []


def drift_stats(vault: Vault) -> dict:
    """计算 drift 统计：总次数、通知次数、误报率。

    false_positive_rate = dismissed / notified (被标记为误报的比例)。
    无通知记录时 false_positive_rate = 0。
    """
    entries = read_drift_log(vault)
    total = len(entries)
    notified = sum(1 for e in entries if e.get("notified"))
    dismissed = sum(1 for e in entries if e.get("dismissed"))
    avg_score = sum(e.get("drift_score", 0) for e in entries) / total if total else 0
    return {
        "total": total,
        "notified": notified,
        "dismissed": dismissed,
        "false_positive_rate": dismissed / notified if notified else 0,
        "avg_score": round(avg_score, 3),
    }


def dismiss_drift(vault: Vault, index: int) -> bool:
    """标记某次 drift 为误报。

    Args:
        vault: vault 根。
        index: 日志条目索引 (0-based, 按写入顺序)。

    Returns:
        True 如果索引有效并已标记; False 如果索引越界。
    """
    entries = read_drift_log(vault)
    if 0 <= index < len(entries):
        entries[index]["dismissed"] = True
        log_path = vault.root / DRIFT_LOG_SUBDIR / DRIFT_LOG_FILE
        log_path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
        return True
    return False


__all__ = [
    "DRIFT_LOG_SUBDIR",
    "DRIFT_LOG_FILE",
    "log_drift",
    "read_drift_log",
    "drift_stats",
    "dismiss_drift",
]

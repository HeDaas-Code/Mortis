"""Mortis toolagent — ClockAgent: 当前时间 + 上次 dream + 逻辑时钟状态。

issue #25: 只读 steiner/。
- now: 当前 UTC 时间 (ISO8601)
- last_dream: mortis-dream-log/ 下最近 .md 的 mtime (或 None)
- logical_clock_phase: 占位 (issue #26 才有真实现) → hardcoded "unknown"

输入 schema (input dict):
    {}  (无参数)

输出 schema (ToolResult.data dict):
    now: str                    # ISO8601 UTC
    last_dream: str | None      # ISO8601 或 None
    logical_clock_phase: str    # 占位 "unknown"
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from mortis.toolagent.base import ToolResult
from mortis.vault import Vault


DREAM_LOG_DIR = "mortis-dream-log"


class ClockAgent:
    """Clock Agent — 物理时间 + 上次 dream。"""

    agent_id: str = "clock"

    def __init__(self, vault: Vault) -> None:
        self.vault = vault

    def execute(self, input: dict) -> ToolResult:
        try:
            now = datetime.now(tz=timezone.utc).isoformat()
            last_dream = self._find_last_dream()
            return ToolResult(
                success=True,
                data={
                    "now": now,
                    "last_dream": last_dream,
                    "logical_clock_phase": "unknown",  # #26 占位
                },
                error=None,
            )
        except Exception as e:  # noqa: BLE001
            return ToolResult(success=False, data=None, error=str(e))

    def _find_last_dream(self) -> str | None:
        """扫 mortis-dream-log/{light,medium,deep}/ 找最近 mtime 的 .md。"""
        log_root = Path(self.vault.root) / DREAM_LOG_DIR
        if not log_root.exists():
            return None
        latest_mtime: float = 0.0
        latest_iso: str | None = None
        for level_dir in log_root.iterdir():
            if not level_dir.is_dir():
                continue
            for md in level_dir.glob("*.md"):
                mt = md.stat().st_mtime
                if mt > latest_mtime:
                    latest_mtime = mt
                    latest_iso = datetime.fromtimestamp(
                        mt, tz=timezone.utc
                    ).isoformat()
        return latest_iso


__all__ = ["ClockAgent"]

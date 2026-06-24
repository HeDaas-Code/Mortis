"""GrowthWatcher 生命周期管理 — 启动/停止 watcher + unease 落盘。"""

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional

from mortis.growth.model import Dimension
from mortis.steiner.unease import accumulate, decay, load_unease, save_unease
from mortis.steiner.watcher import GrowthWatcher
from mortis.vault import Vault

_logger = logging.getLogger(__name__)


class SteinerController:
    """管理 GrowthWatcher 生命周期 + unease 状态落盘。

    线程安全：_lock 保护 accumulate + save_unease 的读-改-写操作。
    Debounce：同一 dimension 1 秒内只 accumulate 一次。
    """

    def __init__(self, vault: Vault) -> None:
        self._vault = vault
        self._lock = threading.Lock()
        self._watcher: Optional[GrowthWatcher] = None
        self._last_trigger: dict[Dimension, float] = {}  # dim -> timestamp
        self._debounce_seconds = 1.0

    def start(self) -> None:
        """启动 GrowthWatcher。watchdog 未安装时 no-op + log warning。"""
        def on_growth_edit(dim: Dimension) -> None:
            self._on_edit(dim)

        self._watcher = GrowthWatcher(self._vault.root, on_growth_edit)
        self._watcher.start()
        _logger.info("SteinerController started, watching %s", self._vault.root / "mortis-growth")

    def stop(self) -> None:
        """停止 GrowthWatcher。"""
        if self._watcher:
            self._watcher.stop()
            self._watcher = None
            _logger.info("SteinerController stopped")

    def _on_edit(self, dim: Dimension) -> None:
        """watcher 回调：debounce + accumulate + save。"""
        now = time.time()
        with self._lock:
            # debounce: 同一 dim 1 秒内只处理一次
            last = self._last_trigger.get(dim, 0)
            if now - last < self._debounce_seconds:
                return
            self._last_trigger[dim] = now

            # accumulate + save
            try:
                state = load_unease(self._vault)
                # 启动时 decay 一次
                state = decay(state, datetime.now(tz=timezone.utc))
                state = accumulate(state, dim, delta=0.15)
                save_unease(self._vault, state)
                _logger.info("unease accumulated: dim=%s, max=%.2f", dim.value, state.max_unease())
            except Exception as e:
                _logger.error("unease accumulate failed: %s", e)

    def tick_decay(self) -> None:
        """手动触发 decay + save（可由 scheduler 定期调用）。"""
        with self._lock:
            try:
                state = load_unease(self._vault)
                state = decay(state, datetime.now(tz=timezone.utc))
                save_unease(self._vault, state)
            except Exception as e:
                _logger.error("unease decay failed: %s", e)

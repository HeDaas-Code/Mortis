"""Mortis daemon — 常驻进程，整合 GrowthWatcher + clock Scheduler。

自动触发:
- REFLECT (22:00-23:00): 读当天 sessions → 写反思
- DREAM_LIGHT (23:00-02:00): LightDreamer.run()
- DREAM_DEEP (02:00-04:00): DeepDreamer.run()
- ERODE (04:00-06:00): decay unease + archive growth

issue #60: 让 Mortis 作为常驻进程运行，按 clock phase 自动触发认知周期。
"""

from __future__ import annotations

import logging
import signal
import time
from datetime import datetime, timezone

from mortis.clock import (
    ConsciousnessState,
    LogicalClock,
    Scheduler,
    SleepState,
    update_sleep_state,
)
from mortis.provider import make_provider
from mortis.seed import load_seed
from mortis.steiner import SteinerController
from mortis.vault import Vault

_logger = logging.getLogger(__name__)


class MortisDaemon:
    """常驻进程，按 clock phase 自动触发认知周期。

    生命周期:
    1. start(): 启动 SteinerController (GrowthWatcher)
    2. run(): 主循环，每 60 秒 tick 一次
       - 检查 clock phase
       - 根据 Scheduler.tick() 结果触发 reflect/dream/erode
       - SteinerController.tick_decay() 定期 decay
    3. stop(): 停止 SteinerController + 清理
    """

    TICK_INTERVAL_SECONDS = 60  # 每分钟检查一次

    def __init__(
        self,
        vault_path: str = "vault",
        provider_kind: str = "auto",
        seed_path: str = "seed.md",
    ) -> None:
        self._vault = Vault(vault_path)
        self._provider = make_provider(provider_kind)
        self._seed = load_seed(seed_path)
        self._clock = LogicalClock()
        self._scheduler = Scheduler()
        self._steiner = SteinerController(self._vault)
        self._sleep_state = SleepState.fresh()
        self._running = False
        self._last_phase: ConsciousnessState | None = None

    def start(self) -> None:
        """启动 daemon：SteinerController + 主循环。"""
        self._steiner.start()
        _logger.info("MortisDaemon started")

    def stop(self) -> None:
        """停止 daemon。"""
        self._running = False
        self._steiner.stop()
        _logger.info("MortisDaemon stopped")

    def run(self) -> None:
        """主循环。阻塞直到 stop() 或 KeyboardInterrupt。"""
        self._running = True
        self.start()
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        try:
            while self._running:
                self._tick()
                time.sleep(self.TICK_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def _signal_handler(self, signum, frame) -> None:
        """SIGINT/SIGTERM → 优雅停止。"""
        _logger.info("received signal %d, stopping...", signum)
        self._running = False

    def _tick(self) -> None:
        """单次 tick：检查 clock + 触发认知周期。"""
        now = datetime.now(tz=timezone.utc)
        phase = self._clock.state(now)

        # phase 变化时 log
        if phase != self._last_phase:
            _logger.info("phase transition: %s -> %s", self._last_phase, phase)
            # 从 AWAKE 进入睡眠阶段 (REFLECT/DREAM/ERODE) → 标记 slept (decay debt)
            if (
                self._last_phase == ConsciousnessState.AWAKE
                and phase != ConsciousnessState.AWAKE
            ):
                self._sleep_state = update_sleep_state(
                    self._sleep_state, now, slept=True
                )
            self._last_phase = phase

        # AWAKE 时段累积清醒时长 + debt
        if phase == ConsciousnessState.AWAKE:
            self._sleep_state = update_sleep_state(
                self._sleep_state, now, slept=False
            )

        # scheduler tick
        tick_result = self._scheduler.tick(sleep_state=self._sleep_state, now=now)

        # 触发认知周期
        if tick_result.should_trigger_reflect:
            self._do_reflect()
        if tick_result.should_trigger_dream_light:
            self._do_dream("light")
        if tick_result.should_trigger_dream_deep:
            self._do_dream("deep")

        # 定期 decay unease (ERODE 时段)
        if phase == ConsciousnessState.ERODE:
            self._steiner.tick_decay()

    def _do_reflect(self) -> None:
        """触发反思。"""
        try:
            from mortis.reflect import ReflectExecutor

            executor = ReflectExecutor(
                self._vault, self._provider, mortis_name="Mortis"
            )
            sessions_dir = self._vault.root / "mortis-journal" / "sessions"
            if sessions_dir.exists():
                today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
                today_dir = sessions_dir / today
                if today_dir.exists():
                    session_paths = [f.name for f in today_dir.glob("*.json")]
                    if session_paths:
                        executor.run(session_paths, sessions_dir=today_dir)
                        _logger.info(
                            "reflect completed: %d sessions", len(session_paths)
                        )
        except Exception as e:
            _logger.error("reflect failed: %s", e)

    def _do_dream(self, level: str) -> None:
        """触发梦境。"""
        try:
            if level == "light":
                from mortis.dream import LightDreamer

                dreamer = LightDreamer(self._vault, self._provider)
            elif level == "deep":
                from mortis.dream.deep import DeepDreamer

                dreamer = DeepDreamer(self._vault, self._provider, self._seed)
            else:
                return
            result = dreamer.run()
            _logger.info(
                "dream %s: ok=%s, phases=%d", level, result.ok, len(result.traces)
            )
        except Exception as e:
            _logger.error("dream %s failed: %s", level, e)


__all__ = ["MortisDaemon"]

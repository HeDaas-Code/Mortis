"""Test mortis.steiner.lifecycle — SteinerController 生命周期 + unease 落盘。

issue #58 acceptance:
- SteinerController 构造
- _on_edit 回调写入 unease.json
- debounce: 同一 dim 1 秒内多次调用只 accumulate 一次
- tick_decay: decay 后 unease 值降低
- 异常时不崩溃(静默处理)
- start/stop 生命周期(watchdog 未安装时不崩溃)

测试策略:不真起 watchdog observer(耗时+不稳定+本环境未装 watchdog),
直接调 _on_edit / tick_decay 验证 unease 落盘逻辑;start/stop 验证
watchdog 未安装时 no-op 不崩溃 + callback 接线正确。
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from mortis.growth.model import Dimension
from mortis.steiner.lifecycle import SteinerController
from mortis.steiner.unease import (
    DECAY_PER_DAY,
    STEINER_DIR,
    UneaseState,
    load_unease,
    save_unease,
)
from mortis.steiner.watcher import FakeEvent
from mortis.vault.local import Vault

# ============================================================
# fixtures
# ============================================================


@pytest.fixture
def vault_dir() -> Path:
    """空 vault tmp 目录。"""
    with tempfile.TemporaryDirectory(prefix="mortis-steiner-controller-") as td:
        yield Path(td)


@pytest.fixture
def vault(vault_dir: Path) -> Vault:
    """Vault 实例(指向 tmp 目录)。"""
    return Vault(vault_dir)


@pytest.fixture
def controller(vault: Vault) -> SteinerController:
    """SteinerController 实例(未 start)。"""
    return SteinerController(vault)


# ============================================================
# Test 1: 构造
# ============================================================


class TestConstruction:
    """SteinerController 构造 — 字段正确初始化。"""

    def test_constructs_with_vault(self, vault: Vault) -> None:
        """构造后 _vault 指向传入 vault,其余字段为默认。"""
        c = SteinerController(vault)
        assert c._vault is vault
        assert c._watcher is None
        assert c._debounce_seconds == 1.0
        assert c._last_trigger == {}

    def test_lock_is_a_real_lock(self, controller: SteinerController) -> None:
        """_lock 是 threading.Lock 实例(线程安全保证)。"""
        import threading
        assert isinstance(controller._lock, type(threading.Lock()))


# ============================================================
# Test 2: _on_edit 回调写入 unease.json
# ============================================================


class TestOnEditWritesUnease:
    """_on_edit 回调:debounce + accumulate + save 落盘。"""

    def test_on_edit_creates_unease_json(self, controller: SteinerController,
                                         vault: Vault, vault_dir: Path) -> None:
        """_on_edit 后 mortis-steiner/unease.json 存在且内容合法 JSON。"""
        controller._on_edit(Dimension.IDENTITY)
        target = vault_dir / STEINER_DIR / "unease.json"
        assert target.exists()
        data = json.loads(target.read_text(encoding="utf-8"))
        assert "per_dimension" in data
        assert "last_decay" in data

    def test_on_edit_accumulates_edited_dim(self, controller: SteinerController,
                                            vault: Vault) -> None:
        """_on_edit(IDENTITY) → identity 维度 +0.15。"""
        controller._on_edit(Dimension.IDENTITY)
        state = load_unease(vault)
        assert state.per_dimension[Dimension.IDENTITY] == pytest.approx(0.15)

    def test_on_edit_does_not_touch_other_dims(self, controller: SteinerController,
                                               vault: Vault) -> None:
        """_on_edit(CREATIVITY) → 只有 creativity 维度变化,其余仍 0。"""
        controller._on_edit(Dimension.CREATIVITY)
        state = load_unease(vault)
        assert state.per_dimension[Dimension.CREATIVITY] == pytest.approx(0.15)
        for dim in Dimension:
            if dim != Dimension.CREATIVITY:
                assert state.per_dimension[dim] == 0.0

    def test_on_edit_accumulates_on_existing_state(self, controller: SteinerController,
                                                    vault: Vault) -> None:
        """已有 unease 状态时,_on_edit 在原值基础上累加。"""
        pre = UneaseState(
            per_dimension={d: 0.3 for d in Dimension},
            last_decay=datetime.now(tz=timezone.utc).isoformat(),
        )
        save_unease(vault, pre)
        controller._on_edit(Dimension.TONE)
        state = load_unease(vault)
        # tone 维度:0.3 + 0.15 = 0.45(忽略极小 decay)
        assert state.per_dimension[Dimension.TONE] == pytest.approx(0.45, abs=0.01)


# ============================================================
# Test 3: debounce
# ============================================================


class TestDebounce:
    """debounce:同一 dim 1 秒内多次调用只 accumulate 一次。"""

    def test_two_quick_calls_one_accumulate(self, controller: SteinerController,
                                            vault: Vault) -> None:
        """同一 dim 连续两次调用(1 秒内)→ 只 accumulate 一次(0.15)。"""
        controller._on_edit(Dimension.IDENTITY)
        controller._on_edit(Dimension.IDENTITY)
        state = load_unease(vault)
        assert state.per_dimension[Dimension.IDENTITY] == pytest.approx(0.15)

    def test_different_dims_not_debounced(self, controller: SteinerController,
                                          vault: Vault) -> None:
        """不同 dim 不互相 debounce → 各 accumulate 一次。"""
        controller._on_edit(Dimension.IDENTITY)
        controller._on_edit(Dimension.VALUES)
        state = load_unease(vault)
        assert state.per_dimension[Dimension.IDENTITY] == pytest.approx(0.15)
        assert state.per_dimension[Dimension.VALUES] == pytest.approx(0.15)

    def test_after_debounce_window_accumulates_again(self, controller: SteinerController,
                                                     vault: Vault) -> None:
        """超过 debounce 窗口后再次调用 → 第二次 accumulate 生效(0.30)。"""
        controller._on_edit(Dimension.IDENTITY)
        # 把 last_trigger 回拨到很久以前,模拟过了 debounce 窗口
        controller._last_trigger[Dimension.IDENTITY] = 0.0
        controller._on_edit(Dimension.IDENTITY)
        state = load_unease(vault)
        assert state.per_dimension[Dimension.IDENTITY] == pytest.approx(0.30)

    def test_debounce_window_is_one_second(self, controller: SteinerController) -> None:
        """debounce 窗口确认为 1.0 秒。"""
        assert controller._debounce_seconds == 1.0


# ============================================================
# Test 4: tick_decay
# ============================================================


class TestTickDecay:
    """tick_decay:decay + save,unease 值降低。"""

    def test_tick_decay_lowers_unease(self, controller: SteinerController,
                                      vault: Vault) -> None:
        """10 天前的 0.9 unease → tick_decay 后 ≈ 0.9 × 0.85^10。"""
        old = datetime.now(tz=timezone.utc) - timedelta(days=10)
        state = UneaseState(
            per_dimension={d: 0.9 for d in Dimension},
            last_decay=old.isoformat(),
        )
        save_unease(vault, state)
        controller.tick_decay()
        new_state = load_unease(vault)
        expected = 0.9 * (DECAY_PER_DAY ** 10)
        for dim in Dimension:
            assert new_state.per_dimension[dim] < 0.9
            assert new_state.per_dimension[dim] == pytest.approx(expected, rel=1e-6)

    def test_tick_decay_updates_last_decay(self, controller: SteinerController,
                                           vault: Vault) -> None:
        """tick_decay 后 last_decay 更新为当前时间。"""
        old = datetime.now(tz=timezone.utc) - timedelta(days=5)
        state = UneaseState(
            per_dimension={d: 0.5 for d in Dimension},
            last_decay=old.isoformat(),
        )
        save_unease(vault, state)
        before = datetime.now(tz=timezone.utc)
        controller.tick_decay()
        new_state = load_unease(vault)
        new_last = datetime.fromisoformat(new_state.last_decay)
        assert new_last > old
        assert new_last >= before

    def test_tick_decay_no_state_no_crash(self, controller: SteinerController,
                                          vault: Vault) -> None:
        """vault 内无 unease.json 时 tick_decay 不崩溃(全 0 落盘)。"""
        controller.tick_decay()
        state = load_unease(vault)
        for dim in Dimension:
            assert state.per_dimension[dim] == 0.0


# ============================================================
# Test 5: 异常时不崩溃(静默处理)
# ============================================================


class TestExceptionHandling:
    """异常不能传播到 watcher 线程(会导致线程崩溃)。"""

    def test_on_edit_swallows_load_exception(
        self, controller: SteinerController, vault: Vault, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """load_unease 抛异常时 _on_edit 静默处理,不传播。"""

        def boom(v: Vault) -> UneaseState:
            raise RuntimeError("boom")

        monkeypatch.setattr("mortis.steiner.lifecycle.load_unease", boom)
        # 不应抛异常
        controller._on_edit(Dimension.IDENTITY)

    def test_tick_decay_swallows_load_exception(
        self, controller: SteinerController, vault: Vault, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """load_unease 抛异常时 tick_decay 静默处理,不传播。"""

        def boom(v: Vault) -> UneaseState:
            raise RuntimeError("boom")

        monkeypatch.setattr("mortis.steiner.lifecycle.load_unease", boom)
        controller.tick_decay()

    def test_on_edit_swallows_save_exception(
        self, controller: SteinerController, vault: Vault, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """save_unease 抛异常时 _on_edit 静默处理,不传播。"""

        def boom(v: Vault, s: UneaseState) -> bool:
            raise RuntimeError("save boom")

        monkeypatch.setattr("mortis.steiner.lifecycle.save_unease", boom)
        controller._on_edit(Dimension.IDENTITY)


# ============================================================
# Test 6: start/stop 生命周期(watchdog 未安装时不崩溃)
# ============================================================


class TestStartStop:
    """start/stop 生命周期 — watchdog 未安装时 no-op 不崩溃。"""

    def test_start_does_not_crash_without_watchdog(
        self, controller: SteinerController
    ) -> None:
        """watchdog 未安装时 start() 是 no-op,不崩溃。"""
        controller.start()
        assert controller._watcher is not None
        controller.stop()

    def test_stop_is_reentrant(self, controller: SteinerController) -> None:
        """stop() 多次调用不报错(幂等)。"""
        controller.start()
        controller.stop()
        controller.stop()  # 第二次 stop 不崩溃
        assert controller._watcher is None

    def test_stop_without_start_no_crash(self, controller: SteinerController) -> None:
        """未 start 直接 stop 不崩溃。"""
        controller.stop()
        assert controller._watcher is None

    def test_start_wires_callback_to_handler(
        self, controller: SteinerController, vault: Vault
    ) -> None:
        """start() 后 handler 触发 → _on_edit → unease 落盘(callback 接线正确)。"""
        controller.start()
        try:
            target = vault.root / "mortis-growth" / "identity" / "g1.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("body", encoding="utf-8")
            # 直接调 handler.on_modified 模拟 watchdog 事件(不真起线程)
            controller._watcher.handler.on_modified(FakeEvent(src_path=str(target)))
            state = load_unease(vault)
            assert state.per_dimension[Dimension.IDENTITY] == pytest.approx(0.15)
        finally:
            controller.stop()

    def test_start_wires_callback_different_dim(
        self, controller: SteinerController, vault: Vault
    ) -> None:
        """start() 后 handler 触发不同 dim → 对应维度 accumulate。"""
        controller.start()
        try:
            target = vault.root / "mortis-growth" / "mortality" / "g2.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("body", encoding="utf-8")
            controller._watcher.handler.on_created(
                FakeEvent(src_path=str(target), event_type="created")
            )
            state = load_unease(vault)
            assert state.per_dimension[Dimension.MORTALITY] == pytest.approx(0.15)
        finally:
            controller.stop()

"""Test mortis.cli.daemon — MortisDaemon 常驻进程 (issue #60)。

验收:
- MortisDaemon 构造 (vault / provider / seed / clock / scheduler / steiner)
- start/stop 生命周期 (watchdog 未安装时不崩溃)
- _tick 不崩溃 (空 vault)
- _do_reflect 无 session 时静默处理 (不抛异常)
- _do_dream light 执行 (MockProvider + sessions → 写 growth 候选)
- signal handler 设置 _running=False (SIGINT/SIGTERM 优雅退出)

测试策略: daemon.run() 是阻塞主循环,测试中不调 run();
直接测 start/stop/_tick/_do_reflect/_do_dream/_signal_handler。
"""

from __future__ import annotations

import signal
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from mortis.cli.daemon import MortisDaemon
from mortis.clock import ConsciousnessState, LogicalClock, SleepState
from mortis.dream.crystallize import reset_counter
from mortis.memory import Session
from mortis.provider import MockProvider
from mortis.reflect import clear_emotion_cache
from mortis.vault import Vault

# ============================================================
# helpers
# ============================================================


def _today() -> str:
    """UTC today — 与 daemon / executor 内部 datetime.now 同源,避免跨日 flaky。"""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


def _repo_seed() -> str:
    """仓库根的 seed.md 绝对路径 — 测试不依赖 cwd。"""
    return str(Path(__file__).resolve().parent.parent / "seed.md")


@pytest.fixture(autouse=True)
def _reset_state() -> None:
    """每个测试前后清空 emotion cache + dream id counter,避免跨测试污染。"""
    clear_emotion_cache()
    reset_counter()
    yield
    clear_emotion_cache()
    reset_counter()


@pytest.fixture
def vault_dir() -> Path:
    """空 vault tmp 目录。"""
    with tempfile.TemporaryDirectory(prefix="mortis-daemon-") as td:
        yield Path(td)


def _make_daemon(vault_path: Path) -> MortisDaemon:
    """构造 MortisDaemon (mock provider + repo seed)。"""
    return MortisDaemon(
        vault_path=str(vault_path),
        provider_kind="mock",
        seed_path=_repo_seed(),
    )


def _make_vault_with_sessions(td: Path, n: int = 2) -> Path:
    """在 tmp 目录建 vault + 今天日期目录 + n 个 session。"""
    sessions_dir = td / "mortis-journal" / "sessions" / _today()
    sessions_dir.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        Session(session_id=f"session-{i}", threads=[f"th-{i}"]).save(sessions_dir)
    return td


# ============================================================
# Test 1: 构造
# ============================================================


class TestConstruction:
    """MortisDaemon 构造 — 字段正确初始化。"""

    def test_constructs_with_vault(self, vault_dir: Path) -> None:
        """构造后各组件就位。"""
        daemon = _make_daemon(vault_dir)
        assert daemon._vault.root == Vault(vault_dir).root
        assert isinstance(daemon._provider, MockProvider)
        assert daemon._seed.is_complete()
        assert isinstance(daemon._clock, LogicalClock)
        assert daemon._steiner is not None
        assert isinstance(daemon._sleep_state, SleepState)
        assert daemon._running is False
        assert daemon._last_phase is None

    def test_tick_interval_is_sixty_seconds(self, vault_dir: Path) -> None:
        """TICK_INTERVAL_SECONDS = 60 (每分钟一次)。"""
        daemon = _make_daemon(vault_dir)
        assert daemon.TICK_INTERVAL_SECONDS == 60


# ============================================================
# Test 2: start/stop 生命周期
# ============================================================


class TestStartStop:
    """start/stop 生命周期 — watchdog 未安装时 no-op 不崩溃。"""

    def test_start_does_not_crash(self, vault_dir: Path) -> None:
        """watchdog 未安装时 start() 是 no-op,不崩溃。"""
        daemon = _make_daemon(vault_dir)
        daemon.start()
        assert daemon._steiner._watcher is not None
        daemon.stop()

    def test_stop_sets_running_false(self, vault_dir: Path) -> None:
        """stop() 把 _running 置 False。"""
        daemon = _make_daemon(vault_dir)
        daemon._running = True
        daemon.stop()
        assert daemon._running is False

    def test_stop_after_start_clears_watcher(self, vault_dir: Path) -> None:
        """start → stop 后 _steiner._watcher 归 None。"""
        daemon = _make_daemon(vault_dir)
        daemon.start()
        assert daemon._steiner._watcher is not None
        daemon.stop()
        assert daemon._steiner._watcher is None

    def test_stop_without_start_no_crash(self, vault_dir: Path) -> None:
        """未 start 直接 stop 不崩溃 (幂等)。"""
        daemon = _make_daemon(vault_dir)
        daemon.stop()
        assert daemon._running is False
        assert daemon._steiner._watcher is None

    def test_stop_is_reentrant(self, vault_dir: Path) -> None:
        """多次 stop 不报错。"""
        daemon = _make_daemon(vault_dir)
        daemon.start()
        daemon.stop()
        daemon.stop()  # 第二次 stop 不崩溃
        assert daemon._steiner._watcher is None


# ============================================================
# Test 3: _tick 不崩溃 (空 vault)
# ============================================================


class TestTick:
    """_tick 单次执行 — 不崩溃。"""

    def test_tick_empty_vault_no_crash(self, vault_dir: Path) -> None:
        """空 vault 上 _tick() 不抛异常。"""
        daemon = _make_daemon(vault_dir)
        daemon._tick()  # 不应抛异常

    def test_tick_sets_last_phase(self, vault_dir: Path) -> None:
        """_tick() 后 _last_phase 被设为当前 ConsciousnessState。"""
        daemon = _make_daemon(vault_dir)
        assert daemon._last_phase is None
        daemon._tick()
        assert daemon._last_phase is not None
        assert daemon._last_phase in ConsciousnessState

    def test_tick_multiple_times_no_crash(self, vault_dir: Path) -> None:
        """连续多次 _tick() 不崩溃。"""
        daemon = _make_daemon(vault_dir)
        for _ in range(3):
            daemon._tick()

    def test_tick_does_not_set_running(self, vault_dir: Path) -> None:
        """_tick() 不改变 _running (主循环控制,不是 tick)。"""
        daemon = _make_daemon(vault_dir)
        daemon._tick()
        assert daemon._running is False


# ============================================================
# Test 4: _do_reflect 无 session 时静默处理
# ============================================================


class TestDoReflect:
    """_do_reflect — 无 session 时静默,有 session 时写反思。"""

    def test_do_reflect_no_sessions_dir(self, vault_dir: Path) -> None:
        """vault 无 sessions 目录 → 静默,不抛异常,不写反思。"""
        daemon = _make_daemon(vault_dir)
        daemon._do_reflect()  # 不应抛异常

        vault = Vault(vault_dir)
        from mortis.reflect import list_pending_reflections
        assert list_pending_reflections(vault) == []

    def test_do_reflect_empty_today_dir(self, vault_dir: Path) -> None:
        """今天日期目录存在但无 session 文件 → 静默,不抛异常。"""
        sessions_dir = vault_dir / "mortis-journal" / "sessions" / _today()
        sessions_dir.mkdir(parents=True, exist_ok=True)
        # 不放任何 .json

        daemon = _make_daemon(vault_dir)
        daemon._do_reflect()  # 不应抛异常

        vault = Vault(vault_dir)
        from mortis.reflect import list_pending_reflections
        assert list_pending_reflections(vault) == []

    def test_do_reflect_with_sessions_writes_reflection(
        self, vault_dir: Path
    ) -> None:
        """有 session → 写一篇反思。"""
        _make_vault_with_sessions(vault_dir, n=2)
        daemon = _make_daemon(vault_dir)
        # 注入有 JSON 响应的 MockProvider (reflect 调 generate_text)
        daemon._provider = MockProvider(responses=[
            '{"valence": 0.3, "arousal": 0.5}',  # emotion score
            "今天和 owner 聊了两个任务,语气稳定。",  # reflection body
        ])
        daemon._do_reflect()

        vault = Vault(vault_dir)
        from mortis.reflect import list_pending_reflections
        pending = list_pending_reflections(vault)
        assert len(pending) == 1
        assert "pending-reflections" in pending[0]

    def test_do_reflect_swallows_exception(
        self, vault_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ReflectExecutor.run 抛异常时 _do_reflect 静默,不传播。"""
        _make_vault_with_sessions(vault_dir, n=1)
        daemon = _make_daemon(vault_dir)

        def boom(*args, **kwargs):
            raise RuntimeError("reflect boom")

        monkeypatch.setattr(
            "mortis.reflect.ReflectExecutor.run", boom
        )
        daemon._do_reflect()  # 不应抛异常


# ============================================================
# Test 5: _do_dream light 执行 (MockProvider)
# ============================================================


class TestDoDream:
    """_do_dream — light 执行 + 异常兜底。"""

    def test_do_dream_light_with_sessions(self, vault_dir: Path) -> None:
        """有 session → light dream 跑完 5 phase → 写 growth 候选。

        issue #94: Light 追加 EXPRESSION_DISTILL phase (无 stats 时跳过)。
        """
        _make_vault_with_sessions(vault_dir, n=2)
        daemon = _make_daemon(vault_dir)
        # 注入有 JSON 响应的 MockProvider:
        # 2 emotion (per session) + 1 associate
        daemon._provider = MockProvider(responses=[
            '{"valence": 0.5, "arousal": 0.5}',
            '{"valence": -0.3, "arousal": 0.7}',
            '{"body": "owner 注重简洁", "tags": ["简洁"]}',
        ])
        daemon._do_dream("light")

        vault = Vault(vault_dir)
        growths = vault.list_growths()
        assert len(growths) == 1
        assert growths[0].startswith("mortis-growth/")

    def test_do_dream_light_empty_vault(self, vault_dir: Path) -> None:
        """空 vault → light dream 跑完不崩,不写 growth。"""
        daemon = _make_daemon(vault_dir)
        daemon._do_dream("light")  # 不应抛异常

        vault = Vault(vault_dir)
        assert vault.list_growths() == []

    def test_do_dream_invalid_level_no_crash(self, vault_dir: Path) -> None:
        """非法 level → 提前返回,不抛异常。"""
        daemon = _make_daemon(vault_dir)
        daemon._do_dream("invalid")  # 不应抛异常

    def test_do_dream_swallows_exception(
        self, vault_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LightDreamer.run 抛异常时 _do_dream 静默,不传播。"""
        daemon = _make_daemon(vault_dir)

        def boom(self):
            raise RuntimeError("dream boom")

        monkeypatch.setattr("mortis.dream.LightDreamer.run", boom)
        daemon._do_dream("light")  # 不应抛异常


# ============================================================
# Test 6: signal handler
# ============================================================


class TestSignalHandler:
    """_signal_handler — SIGINT/SIGTERM 优雅退出。"""

    def test_signal_handler_sets_running_false(self, vault_dir: Path) -> None:
        """_signal_handler(SIGINT) 把 _running 置 False。"""
        daemon = _make_daemon(vault_dir)
        daemon._running = True
        assert daemon._running is True
        daemon._signal_handler(signal.SIGINT, None)
        assert daemon._running is False

    def test_signal_handler_sigterm(self, vault_dir: Path) -> None:
        """_signal_handler(SIGTERM) 也把 _running 置 False。"""
        daemon = _make_daemon(vault_dir)
        daemon._running = True
        daemon._signal_handler(signal.SIGTERM, None)
        assert daemon._running is False

    def test_signal_handler_idempotent(self, vault_dir: Path) -> None:
        """多次调用 _signal_handler 不报错。"""
        daemon = _make_daemon(vault_dir)
        daemon._running = True
        daemon._signal_handler(signal.SIGINT, None)
        assert daemon._running is False
        daemon._signal_handler(signal.SIGTERM, None)  # 已经 False,不报错
        assert daemon._running is False

    def test_signal_handler_changes_running_state(self, vault_dir: Path) -> None:
        """_signal_handler 改变 _running 状态:True → False。"""
        daemon = _make_daemon(vault_dir)
        daemon._running = True
        before = daemon._running
        daemon._signal_handler(signal.SIGINT, None)
        after = daemon._running
        assert before is True
        assert after is False
        assert before != after

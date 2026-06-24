"""Test mortis.cli.goodnight — owner「晚安」触发完整夜间认知周期。

issue #61 acceptance:
- run_goodnight 完整流程 (REFLECT → DREAM_LIGHT → ERODE)
- 无 session 时 reflect 返回 True (不算失败)
- --deep=True 时执行 dream_deep
- --deep=False 时不执行 dream_deep
- 各 phase 异常时返回 False 但不崩溃
- erode 调用 steiner.tick_decay()
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from mortis.cli.commands import COMMANDS, build_parser, main
from mortis.dream.crystallize import reset_counter
from mortis.memory import Session
from mortis.provider import MockProvider
from mortis.reflect import clear_emotion_cache, list_pending_reflections
from mortis.vault import Vault


# ============================================================
# helpers
# ============================================================


def _today() -> str:
    """UTC today — 与 goodnight / executor / dreamer 内部 datetime.now 同源。"""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


def _repo_seed() -> str:
    """仓库根的 seed.md 绝对路径 — 测试不依赖 cwd。"""
    return str(Path(__file__).resolve().parent.parent / "seed.md")


def _all_zero_drift() -> str:
    """DeepDreamer SEED_CHECK 用的全 0 drift JSON 响应。"""
    return (
        '{"identity": 0.0, "values": 0.0, "tone": 0.0, "agency": 0.0, '
        '"relations": 0.0, "creativity": 0.0, "mortality": 0.0}'
    )


@pytest.fixture(autouse=True)
def _reset_state() -> None:
    """每个测试前后清空 emotion cache + dream id counter,避免跨测试污染。"""
    clear_emotion_cache()
    reset_counter()
    yield
    clear_emotion_cache()
    reset_counter()


def _make_vault_with_sessions(td: Path, n: int = 2) -> Path:
    """在 tmp 目录建 vault + 今天日期目录 + n 个 session。"""
    sessions_dir = td / "mortis-journal" / "sessions" / _today()
    sessions_dir.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        Session(session_id=f"session-{i}", threads=[f"th-{i}"]).save(sessions_dir)
    return td


def _make_mock_provider(deep: bool = False) -> MockProvider:
    """构造带预设响应的 MockProvider, 覆盖 reflect + dream_light (+ dream_deep)。

    调用顺序 (deep=False):
      1. reflect: reflection text
      2. reflect: emotion JSON (cache key = "session-0.json")
      3. dream_light: emotion JSON (session-0)
      4. dream_light: emotion JSON (session-1)
      5. dream_light: associate JSON

    deep=True 时追加:
      6. dream_deep: seed_check drift JSON
    """
    responses = [
        "今天主要在写代码,语气平和。结论先行效果不错。",  # reflect: reflection
        '{"valence": 0.3, "arousal": 0.4}',               # reflect: emotion
        '{"valence": 0.3, "arousal": 0.4}',               # dream: emotion (session-0)
        '{"valence": 0.3, "arousal": 0.4}',               # dream: emotion (session-1)
        '{"body": "owner 注重简洁", "tags": ["简洁"]}',     # dream: associate
    ]
    if deep:
        responses.append(_all_zero_drift())                 # deep: seed_check
    return MockProvider(responses=responses)


def _patch_provider(monkeypatch: pytest.MonkeyPatch, provider: MockProvider) -> None:
    """把 run_goodnight 内部的 make_provider 替换为返回指定 provider。"""
    monkeypatch.setattr(
        "mortis.cli.goodnight.make_provider", lambda kind: provider
    )


# ============================================================
# parser + COMMANDS 注册
# ============================================================


class TestParser:
    """build_parser 能解析 goodnight 命令及其参数。"""

    def test_parse_goodnight_defaults(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["goodnight"])
        assert args.command == "goodnight"
        assert args.deep is False
        assert args.provider == "auto"
        assert args.vault == "vault"
        assert args.seed == "seed.md"

    def test_parse_goodnight_deep(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["goodnight", "--deep"])
        assert args.deep is True

    def test_parse_goodnight_mock_provider(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["goodnight", "--provider", "mock"])
        assert args.provider == "mock"

    def test_commands_dict_has_goodnight(self) -> None:
        assert "goodnight" in COMMANDS
        assert COMMANDS["goodnight"].__name__ == "cmd_goodnight"


# ============================================================
# run_goodnight 完整流程
# ============================================================


class TestRunGoodnightFullFlow:
    """run_goodnight 完整流程: REFLECT → DREAM_LIGHT → ERODE。"""

    def test_full_flow_deep_false(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """有 sessions + deep=False → 3 phase 全 ok,写反思 + growth。"""
        _make_vault_with_sessions(tmp_path, n=2)
        provider = _make_mock_provider(deep=False)
        _patch_provider(monkeypatch, provider)

        from mortis.cli.goodnight import run_goodnight
        results = run_goodnight(
            vault_path=str(tmp_path),
            provider_kind="mock",
            seed_path=_repo_seed(),
            deep=False,
        )

        assert results["reflect_ok"] is True
        assert results["dream_light_ok"] is True
        assert results["erode_ok"] is True
        assert "dream_deep_ok" not in results

        # 反思已写盘
        vault = Vault(tmp_path)
        pending = list_pending_reflections(vault)
        assert len(pending) == 1
        assert "pending-reflections" in pending[0]

        # growth 候选已写盘
        growths = vault.list_growths()
        assert len(growths) == 1
        assert growths[0].startswith("mortis-growth/")

    def test_full_flow_writes_reflection_and_growth(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """完整流程后 vault 里有 1 篇反思 + 1 个 growth 候选。"""
        _make_vault_with_sessions(tmp_path, n=2)
        provider = _make_mock_provider(deep=False)
        _patch_provider(monkeypatch, provider)

        from mortis.cli.goodnight import run_goodnight
        run_goodnight(
            vault_path=str(tmp_path),
            provider_kind="mock",
            seed_path=_repo_seed(),
            deep=False,
        )

        vault = Vault(tmp_path)
        # 反思
        pending = list_pending_reflections(vault)
        assert len(pending) == 1
        # growth
        assert len(vault.list_growths()) == 1

    def test_full_flow_via_cli_rc_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """CLI: goodnight → rc=0, 输出 3 phase 全 ✓。"""
        _make_vault_with_sessions(tmp_path, n=2)
        provider = _make_mock_provider(deep=False)
        _patch_provider(monkeypatch, provider)

        rc = main([
            "goodnight",
            "--vault", str(tmp_path),
            "--seed", _repo_seed(),
            "--provider", "mock",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert "reflect_ok: ✓" in out
        assert "dream_light_ok: ✓" in out
        assert "erode_ok: ✓" in out
        assert "dream_deep_ok" not in out


# ============================================================
# 无 session 时 reflect 返回 True
# ============================================================


class TestNoSessions:
    """无 session 时 reflect 返回 True (不算失败)。"""

    def test_no_sessions_reflect_returns_true(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """vault 无今天 sessions → reflect_ok=True, dream_light_ok=True, erode_ok=True。"""
        Vault(tmp_path)  # 建 vault 但无 sessions 目录
        provider = MockProvider()  # 不会真调 LLM (没进 reflect / dream 的实质路径)
        _patch_provider(monkeypatch, provider)

        from mortis.cli.goodnight import run_goodnight
        results = run_goodnight(
            vault_path=str(tmp_path),
            provider_kind="mock",
            seed_path=_repo_seed(),
            deep=False,
        )

        assert results["reflect_ok"] is True  # 无 session 不算失败
        assert results["dream_light_ok"] is True  # 4 phase 全 ok (no_sessions)
        assert results["erode_ok"] is True

    def test_no_session_files_in_today_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """有今天日期目录但无 .json 文件 → reflect_ok=True。"""
        sessions_dir = tmp_path / "mortis-journal" / "sessions" / _today()
        sessions_dir.mkdir(parents=True, exist_ok=True)
        # 不放任何 .json
        Vault(tmp_path)
        provider = MockProvider()
        _patch_provider(monkeypatch, provider)

        from mortis.cli.goodnight import run_goodnight
        results = run_goodnight(
            vault_path=str(tmp_path),
            provider_kind="mock",
            seed_path=_repo_seed(),
            deep=False,
        )

        assert results["reflect_ok"] is True
        assert results["dream_light_ok"] is True
        assert results["erode_ok"] is True


# ============================================================
# --deep flag
# ============================================================


class TestDeepFlag:
    """--deep=True/False 控制 dream_deep 是否执行。"""

    def test_deep_true_executes_dream_deep(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """deep=True → results 含 dream_deep_ok 且为 True。"""
        _make_vault_with_sessions(tmp_path, n=2)
        provider = _make_mock_provider(deep=True)
        _patch_provider(monkeypatch, provider)

        from mortis.cli.goodnight import run_goodnight
        results = run_goodnight(
            vault_path=str(tmp_path),
            provider_kind="mock",
            seed_path=_repo_seed(),
            deep=True,
        )

        assert "dream_deep_ok" in results
        assert results["dream_deep_ok"] is True
        # 前置 phase 也 ok
        assert results["reflect_ok"] is True
        assert results["dream_light_ok"] is True
        assert results["erode_ok"] is True

    def test_deep_false_no_dream_deep(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """deep=False → results 不含 dream_deep_ok。"""
        _make_vault_with_sessions(tmp_path, n=2)
        provider = _make_mock_provider(deep=False)
        _patch_provider(monkeypatch, provider)

        from mortis.cli.goodnight import run_goodnight
        results = run_goodnight(
            vault_path=str(tmp_path),
            provider_kind="mock",
            seed_path=_repo_seed(),
            deep=False,
        )

        assert "dream_deep_ok" not in results

    def test_deep_true_via_cli(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """CLI: goodnight --deep → 输出含 dream_deep_ok 行。"""
        _make_vault_with_sessions(tmp_path, n=2)
        provider = _make_mock_provider(deep=True)
        _patch_provider(monkeypatch, provider)

        rc = main([
            "goodnight", "--deep",
            "--vault", str(tmp_path),
            "--seed", _repo_seed(),
            "--provider", "mock",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert "dream_deep_ok" in out
        assert "reflect_ok" in out
        assert "dream_light_ok" in out
        assert "erode_ok" in out

    def test_deep_false_via_cli(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """CLI: goodnight (无 --deep) → 输出不含 dream_deep_ok 行。"""
        _make_vault_with_sessions(tmp_path, n=2)
        provider = _make_mock_provider(deep=False)
        _patch_provider(monkeypatch, provider)

        rc = main([
            "goodnight",
            "--vault", str(tmp_path),
            "--seed", _repo_seed(),
            "--provider", "mock",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert "dream_deep_ok" not in out


# ============================================================
# 各 phase 异常时返回 False 但不崩溃
# ============================================================


class TestPhaseExceptions:
    """单个 phase 异常时返回 False,不影响后续 phase。"""

    def test_reflect_exception_returns_false(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ReflectExecutor.run 抛异常 → reflect_ok=False, 后续 phase 仍执行。"""
        _make_vault_with_sessions(tmp_path, n=2)
        provider = _make_mock_provider(deep=False)
        _patch_provider(monkeypatch, provider)

        def boom(self, *args, **kwargs):
            raise RuntimeError("reflect boom")

        monkeypatch.setattr("mortis.reflect.ReflectExecutor.run", boom)

        from mortis.cli.goodnight import run_goodnight
        results = run_goodnight(
            vault_path=str(tmp_path),
            provider_kind="mock",
            seed_path=_repo_seed(),
            deep=False,
        )

        assert results["reflect_ok"] is False
        # 后续 phase 不受影响
        assert results["dream_light_ok"] is True
        assert results["erode_ok"] is True

    def test_dream_light_exception_returns_false(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LightDreamer.run 抛异常 → dream_light_ok=False, erode 仍执行。"""
        _make_vault_with_sessions(tmp_path, n=2)
        provider = _make_mock_provider(deep=False)
        _patch_provider(monkeypatch, provider)

        def boom(self):
            raise RuntimeError("dream_light boom")

        monkeypatch.setattr("mortis.dream.LightDreamer.run", boom)

        from mortis.cli.goodnight import run_goodnight
        results = run_goodnight(
            vault_path=str(tmp_path),
            provider_kind="mock",
            seed_path=_repo_seed(),
            deep=False,
        )

        assert results["reflect_ok"] is True
        assert results["dream_light_ok"] is False
        assert results["erode_ok"] is True

    def test_dream_deep_exception_returns_false(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """DeepDreamer.run 抛异常 → dream_deep_ok=False, erode 仍执行。"""
        _make_vault_with_sessions(tmp_path, n=2)
        provider = _make_mock_provider(deep=True)
        _patch_provider(monkeypatch, provider)

        def boom(self):
            raise RuntimeError("dream_deep boom")

        monkeypatch.setattr("mortis.dream.deep.DeepDreamer.run", boom)

        from mortis.cli.goodnight import run_goodnight
        results = run_goodnight(
            vault_path=str(tmp_path),
            provider_kind="mock",
            seed_path=_repo_seed(),
            deep=True,
        )

        assert results["reflect_ok"] is True
        assert results["dream_light_ok"] is True
        assert results["dream_deep_ok"] is False
        assert results["erode_ok"] is True

    def test_erode_exception_returns_false(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SteinerController.tick_decay 抛异常 → erode_ok=False。"""
        _make_vault_with_sessions(tmp_path, n=2)
        provider = _make_mock_provider(deep=False)
        _patch_provider(monkeypatch, provider)

        def boom(self):
            raise RuntimeError("erode boom")

        monkeypatch.setattr("mortis.steiner.SteinerController.tick_decay", boom)

        from mortis.cli.goodnight import run_goodnight
        results = run_goodnight(
            vault_path=str(tmp_path),
            provider_kind="mock",
            seed_path=_repo_seed(),
            deep=False,
        )

        assert results["reflect_ok"] is True
        assert results["dream_light_ok"] is True
        assert results["erode_ok"] is False

    def test_one_phase_fail_does_not_crash_others(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """reflect 失败时 CLI 不崩溃, 返回 rc=1, 其他 phase 仍输出。"""
        _make_vault_with_sessions(tmp_path, n=2)
        provider = _make_mock_provider(deep=False)
        _patch_provider(monkeypatch, provider)

        def boom(self, *args, **kwargs):
            raise RuntimeError("reflect boom")

        monkeypatch.setattr("mortis.reflect.ReflectExecutor.run", boom)

        rc = main([
            "goodnight",
            "--vault", str(tmp_path),
            "--seed", _repo_seed(),
            "--provider", "mock",
        ])
        assert rc == 1  # 有 phase 失败 → rc=1
        out = capsys.readouterr().out
        assert "reflect_ok: ✗" in out
        assert "dream_light_ok: ✓" in out
        assert "erode_ok: ✓" in out


# ============================================================
# erode 调用 steiner.tick_decay()
# ============================================================


class TestErodeCallsTickDecay:
    """erode phase 调用 SteinerController.tick_decay()。"""

    def test_tick_decay_called_once(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """run_goodnight 后 tick_decay 被调用恰好一次。"""
        _make_vault_with_sessions(tmp_path, n=2)
        provider = _make_mock_provider(deep=False)
        _patch_provider(monkeypatch, provider)

        call_count = {"n": 0}

        def spy(self):
            call_count["n"] += 1

        monkeypatch.setattr(
            "mortis.steiner.SteinerController.tick_decay", spy
        )

        from mortis.cli.goodnight import run_goodnight
        results = run_goodnight(
            vault_path=str(tmp_path),
            provider_kind="mock",
            seed_path=_repo_seed(),
            deep=False,
        )

        assert results["erode_ok"] is True
        assert call_count["n"] == 1

    def test_tick_decay_actually_decays(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """真实 tick_decay 调用后 unease 落盘 (不 monkeypatch, 验证真实行为)。"""
        from datetime import timedelta
        from mortis.growth.model import Dimension
        from mortis.steiner import UneaseState, save_unease, load_unease, DECAY_PER_DAY

        _make_vault_with_sessions(tmp_path, n=2)
        provider = _make_mock_provider(deep=False)
        _patch_provider(monkeypatch, provider)

        # 预置一个 10 天前的 0.9 unease
        vault = Vault(tmp_path)
        old = datetime.now(tz=timezone.utc) - timedelta(days=10)
        state = UneaseState(
            per_dimension={d: 0.9 for d in Dimension},
            last_decay=old.isoformat(),
        )
        save_unease(vault, state)

        from mortis.cli.goodnight import run_goodnight
        results = run_goodnight(
            vault_path=str(tmp_path),
            provider_kind="mock",
            seed_path=_repo_seed(),
            deep=False,
        )

        assert results["erode_ok"] is True
        new_state = load_unease(vault)
        expected = 0.9 * (DECAY_PER_DAY ** 10)
        for dim in Dimension:
            assert new_state.per_dimension[dim] < 0.9
            assert new_state.per_dimension[dim] == pytest.approx(expected, rel=1e-6)

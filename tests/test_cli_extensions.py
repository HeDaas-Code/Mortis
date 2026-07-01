"""Test mortis.cli.extensions — dream / reflect / status 命令 (issue #56)。

验收:
- dream --level light/medium 命令执行 (MockProvider + tmp vault + sessions)
- reflect 命令扫描 sessions 并执行
- reflect 无 session 时友好报错 (rc=1)
- status 命令输出 phase + unease + growth count
- parser 能解析新命令
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from mortis.cli.commands import COMMANDS, build_parser, main
from mortis.dream.crystallize import reset_counter
from mortis.memory import Session
from mortis.reflect import clear_emotion_cache
from mortis.vault import Vault

# ============================================================
# helpers
# ============================================================


def _today() -> str:
    """UTC today — 与 dreamer / executor 内部 datetime.now 同源,避免跨日 flaky。"""
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


def _make_vault_with_sessions(td: Path, n: int = 2) -> Path:
    """在 tmp 目录建 vault + 今天日期目录 + n 个 session。"""
    sessions_dir = td / "mortis-journal" / "sessions" / _today()
    sessions_dir.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        Session(session_id=f"session-{i}", threads=[f"th-{i}"]).save(sessions_dir)
    return td


# ============================================================
# parser 解析
# ============================================================


class TestParser:
    """build_parser 能解析新命令及其参数。"""

    def test_parse_dream_defaults(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["dream"])
        assert args.command == "dream"
        assert args.level == "light"
        assert args.k == 4
        assert args.provider == "auto"

    def test_parse_dream_medium_with_k(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["dream", "--level", "medium", "--k", "8"])
        assert args.command == "dream"
        assert args.level == "medium"
        assert args.k == 8

    def test_parse_dream_deep(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["dream", "--level", "deep"])
        assert args.level == "deep"

    def test_parse_dream_invalid_level(self) -> None:
        """非法 level 应被 choices 拒绝。"""
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["dream", "--level", "invalid"])

    def test_parse_reflect_with_sessions(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["reflect", "--sessions", "a.json", "b.json"])
        assert args.command == "reflect"
        assert args.sessions == ["a.json", "b.json"]

    def test_parse_reflect_no_sessions(self) -> None:
        """不传 --sessions → None (扫描模式)。"""
        parser = build_parser()
        args = parser.parse_args(["reflect"])
        assert args.command == "reflect"
        assert args.sessions is None

    def test_parse_status(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["status"])
        assert args.command == "status"
        assert args.vault == "vault"

    def test_parse_web_defaults(self) -> None:
        """web 命令默认 port=8765, vault=vault。"""
        parser = build_parser()
        args = parser.parse_args(["web"])
        assert args.command == "web"
        assert args.port == 8765
        assert args.vault == "vault"

    def test_parse_web_custom_port(self) -> None:
        """web --port 9999 解析正确。"""
        parser = build_parser()
        args = parser.parse_args(["web", "--port", "9999"])
        assert args.command == "web"
        assert args.port == 9999

    def test_commands_dict_has_new_entries(self) -> None:
        """COMMANDS dict 包含 dream / reflect / status / daemon / goodnight / web。"""
        assert "dream" in COMMANDS
        assert "reflect" in COMMANDS
        assert "status" in COMMANDS
        assert "daemon" in COMMANDS
        assert "goodnight" in COMMANDS
        assert "web" in COMMANDS
        assert len(COMMANDS) == 14  # 8 原有 + 3 (issue #56) + 1 (issue #60) + 1 (issue #61) + 1 (issue #52)


# ============================================================
# dream 命令
# ============================================================


class TestCmdDream:
    """dream --level light/medium 命令端到端执行。"""

    def test_dream_light_with_sessions(self, tmp_path: Path) -> None:
        """dream --level light 有 session → 跑完 5 phase → 写 growth 候选。

        issue #94: Light 追加 EXPRESSION_DISTILL phase (无 stats 时跳过, 不写 growth)。
        """
        _make_vault_with_sessions(tmp_path, n=2)
        rc = main([
            "dream", "--level", "light",
            "--vault", str(tmp_path),
            "--seed", _repo_seed(),
            "--provider", "mock",
        ])
        assert rc == 0

        vault = Vault(tmp_path)
        growths = vault.list_growths()
        assert len(growths) == 1
        assert growths[0].startswith("mortis-growth/")

    def test_dream_light_no_sessions(self, tmp_path: Path) -> None:
        """dream --level light 无 session → 5 phase 全 ok,不写 growth。"""
        # tmp_path 是空 vault (Vault.__post_init__ 会建 journal 目录)
        Vault(tmp_path)
        rc = main([
            "dream", "--level", "light",
            "--vault", str(tmp_path),
            "--seed", _repo_seed(),
            "--provider", "mock",
        ])
        assert rc == 0
        vault = Vault(tmp_path)
        assert vault.list_growths() == []

    def test_dream_medium_with_sessions(self, tmp_path: Path) -> None:
        """dream --level medium 有 session → 跑完 5 phase → 写 growth 候选。"""
        _make_vault_with_sessions(tmp_path, n=2)
        rc = main([
            "dream", "--level", "medium", "--k", "2",
            "--vault", str(tmp_path),
            "--seed", _repo_seed(),
            "--provider", "mock",
        ])
        assert rc == 0

        vault = Vault(tmp_path)
        growths = vault.list_growths()
        assert len(growths) == 1


# ============================================================
# reflect 命令
# ============================================================


class TestCmdReflect:
    """reflect 命令端到端执行。"""

    def test_reflect_scans_latest_sessions(self, tmp_path: Path) -> None:
        """reflect 不传 --sessions → 扫最近一天 sessions → 写反思。"""
        _make_vault_with_sessions(tmp_path, n=2)
        rc = main([
            "reflect",
            "--vault", str(tmp_path),
            "--seed", _repo_seed(),
            "--provider", "mock",
        ])
        assert rc == 0

        vault = Vault(tmp_path)
        from mortis.reflect import list_pending_reflections
        pending = list_pending_reflections(vault)
        assert len(pending) == 1
        assert "pending-reflections" in pending[0]

    def test_reflect_no_sessions_dir(self, tmp_path: Path) -> None:
        """reflect 无 sessions 目录 → 友好报错 + rc=1。"""
        Vault(tmp_path)  # 建 vault 但无 sessions
        rc = main([
            "reflect",
            "--vault", str(tmp_path),
            "--seed", _repo_seed(),
            "--provider", "mock",
        ])
        assert rc == 1

    def test_reflect_empty_date_dir(self, tmp_path: Path) -> None:
        """reflect 有日期目录但无 session 文件 → 友好报错 + rc=1。"""
        sessions_dir = tmp_path / "mortis-journal" / "sessions" / _today()
        sessions_dir.mkdir(parents=True, exist_ok=True)
        # 不放任何 .json
        rc = main([
            "reflect",
            "--vault", str(tmp_path),
            "--seed", _repo_seed(),
            "--provider", "mock",
        ])
        assert rc == 1

    def test_reflect_explicit_sessions(self, tmp_path: Path) -> None:
        """reflect --sessions 显式传文件名 → 走默认 sessions_dir。"""
        _make_vault_with_sessions(tmp_path, n=2)
        # 传带日期子目录的相对路径 (executor 默认 sessions_dir = vault/sessions)
        today = _today()
        rc = main([
            "reflect",
            "--sessions", f"{today}/session-0.json", f"{today}/session-1.json",
            "--vault", str(tmp_path),
            "--seed", _repo_seed(),
            "--provider", "mock",
        ])
        assert rc == 0

        vault = Vault(tmp_path)
        from mortis.reflect import list_pending_reflections
        pending = list_pending_reflections(vault)
        assert len(pending) == 1


# ============================================================
# status 命令
# ============================================================


class TestCmdStatus:
    """status 命令输出 phase + unease + pending + growth count。"""

    def test_status_empty_vault(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """status 空 vault → phase + unease 0 + 0 pending + 0 growths。"""
        rc = main(["status", "--vault", str(tmp_path)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "phase:" in out
        assert "unease max:" in out
        assert "pending reflections: 0" in out
        assert "growths: 0" in out

    def test_status_with_growth(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """status 有 growth → growths count 正确。"""
        from mortis.growth.model import Dimension, DreamLevel, Growth

        vault = Vault(tmp_path)
        now = datetime.now(tz=timezone.utc).isoformat()
        g = Growth(
            id="test-growth-001",
            dimension=Dimension.VALUES,
            confidence=0.5,
            created_at=now,
            last_validated=now,
            source_sessions=(),
            dream_level=DreamLevel.LIGHT,
            emotional_valence=0.0,
            emotional_arousal=0.0,
            tags=(),
            body="测试 growth",
        )
        vault.write_growth(g)

        rc = main(["status", "--vault", str(tmp_path)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "growths: 1" in out

    def test_status_phase_value(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """status 输出的 phase 是 ConsciousnessState.value 之一。"""
        from mortis.clock import ConsciousnessState

        rc = main(["status", "--vault", str(tmp_path)])
        assert rc == 0
        out = capsys.readouterr().out
        valid_phases = {s.value for s in ConsciousnessState}
        # 找到 "phase: xxx" 行
        phase_line = [line for line in out.splitlines() if line.startswith("phase:")]
        assert len(phase_line) == 1
        phase_val = phase_line[0].split(":", 1)[1].strip()
        assert phase_val in valid_phases

    def test_status_with_unease(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """status 有 unease → 输出 max + per-dimension。"""
        from mortis.growth.model import Dimension
        from mortis.steiner import UneaseState, save_unease

        vault = Vault(tmp_path)
        # 写一个有 unease 的状态
        state = UneaseState()
        from dataclasses import replace
        state = replace(
            state,
            per_dimension={**state.per_dimension, Dimension.VALUES: 0.45},
        )
        save_unease(vault, state)

        rc = main(["status", "--vault", str(tmp_path)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "unease max: 0.45" in out
        assert "values: 0.45" in out

"""Test mortis.reflect.executor — ReflectExecutor 主流程。

issue #21 acceptance:
- ReflectExecutor.run(session_paths) -> Reflection
- 写盘: mortis-subconscious/pending-reflections/<id>.md
- frontmatter 包含 id / session_paths / valence / arousal / created_at
- H1 标题 + body + > [!note] callout
- id 格式: reflect-YYYY-MM-DD-NNN(当天序号从 001 开始)
- 同一 session 的 emotion 缓存命中
- 二次 run 同 vault → id 自增
"""
from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from mortis.memory import Session
from mortis.provider import MockProvider
from mortis.reflect import (
    PENDING_REFLECTIONS_SUBDIR,
    SUBCONSCIOUS_ROOT,
    ReflectExecutor,
    Reflection,
    clear_emotion_cache,
    list_pending_reflections,
    reflection_rel,
)
from mortis.vault import Vault


# ============================================================
# fixtures
# ============================================================


@pytest.fixture
def vault_dir() -> Path:
    """每次测试一个 tmp 目录 + 配好 sessions 子目录(2 个 session)。"""
    with tempfile.TemporaryDirectory(prefix="mortis-reflect-") as td:
        d = Path(td)
        sessions_dir = d / "mortis-journal" / "sessions" / "2026-06-22"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        s1 = Session(session_id="session-a", threads=["th-1"])
        s1.save(sessions_dir)
        s2 = Session(session_id="session-b", threads=["th-2", "th-3"])
        s2.save(sessions_dir)
        yield d, sessions_dir


@pytest.fixture(autouse=True)
def _reset_emotion_cache() -> None:
    clear_emotion_cache()
    yield
    clear_emotion_cache()


def _make_provider(reflection: str, valence: float, arousal: float) -> MockProvider:
    """构造一个预设两轮的 MockProvider(反思文本 + 情绪 JSON)。"""
    return MockProvider(responses=[
        reflection,
        f'{{"valence": {valence}, "arousal": {arousal}}}',
    ])


# ============================================================
# 主流程
# ============================================================


class TestRunEndToEnd:
    """完整 run → 写盘 → 读回 流程。"""

    def test_run_returns_reflection(self, vault_dir: tuple[Path, Path]) -> None:
        """run 返回 Reflection frozen dataclass,字段对齐。"""
        d, sessions_dir = vault_dir
        vault = Vault(d)
        provider = _make_provider(
            "今天主要在写代码,语气平和。结论先行效果不错。",
            0.4, 0.3,
        )
        ex = ReflectExecutor(vault, provider, mortis_name="Mortis")
        r = ex.run(["session-a.json", "session-b.json"], sessions_dir=sessions_dir)

        assert isinstance(r, Reflection)
        assert r.id == "reflect-2026-06-22-001"
        assert r.session_paths == ("session-a.json", "session-b.json")
        assert r.valence == 0.4
        assert r.arousal == 0.3
        assert r.body == "今天主要在写代码,语气平和。结论先行效果不错。"
        assert r.rel_path.endswith(".md")
        assert "pending-reflections" in r.rel_path

    def test_run_writes_file(self, vault_dir: tuple[Path, Path]) -> None:
        """run 后文件落在 pending-reflections/ 下,且内容含 frontmatter。"""
        d, sessions_dir = vault_dir
        vault = Vault(d)
        provider = _make_provider("反思文本", 0.5, 0.5)
        ex = ReflectExecutor(vault, provider, mortis_name="Mortis")
        r = ex.run(["session-a.json"], sessions_dir=sessions_dir)

        target = d / r.rel_path
        assert target.exists()
        content = target.read_text(encoding="utf-8")
        # frontmatter
        assert content.startswith("---\n")
        assert "id: reflect-2026-06-22-001" in content
        assert "session_paths:" in content
        assert "  - session-a.json" in content
        assert "valence: 0.5" in content
        assert "arousal: 0.5" in content
        assert "created_at:" in content

    def test_run_writes_h1_and_callout(self, vault_dir: tuple[Path, Path]) -> None:
        """md 含 H1 标题 + body + `> [!note]` callout。"""
        d, sessions_dir = vault_dir
        vault = Vault(d)
        provider = _make_provider("先给结论。", 0.0, 0.0)
        ex = ReflectExecutor(vault, provider, mortis_name="Mortis")
        r = ex.run(["session-a.json"], sessions_dir=sessions_dir)
        content = (d / r.rel_path).read_text(encoding="utf-8")
        assert "# " in content  # H1
        assert "先给结论。" in content
        assert "> [!note]" in content
        assert "REFLECT phase" in content

    def test_run_uses_default_sessions_dir(
        self, vault_dir: tuple[Path, Path]
    ) -> None:
        """不传 sessions_dir 时从 vault.root/mortis-journal/sessions 读。
        session_path 可含日期子目录(2026-06-22/session-a.json),匹配 vault 实际布局。
        """
        d, _ = vault_dir
        vault = Vault(d)
        provider = _make_provider("默认路径测试。", 0.0, 0.0)
        ex = ReflectExecutor(vault, provider, mortis_name="Mortis")
        # 不传 sessions_dir — 走默认;rel 带日期子目录
        r = ex.run(["2026-06-22/session-a.json", "2026-06-22/session-b.json"])
        assert r.id == "reflect-2026-06-22-001"


# ============================================================
# ID 生成
# ============================================================


class TestReflectionId:
    """id 自增: 同一天第二次 run → 002。"""

    def test_first_id_is_001(self, vault_dir: tuple[Path, Path]) -> None:
        d, sessions_dir = vault_dir
        vault = Vault(d)
        provider = _make_provider("first", 0.0, 0.0)
        ex = ReflectExecutor(vault, provider, mortis_name="M")
        r = ex.run(["session-a.json"], sessions_dir=sessions_dir)
        assert r.id == "reflect-2026-06-22-001"

    def test_second_id_is_002(self, vault_dir: tuple[Path, Path]) -> None:
        d, sessions_dir = vault_dir
        vault = Vault(d)
        provider = _make_provider("first", 0.0, 0.0)
        ex = ReflectExecutor(vault, provider, mortis_name="M")
        r1 = ex.run(["session-a.json"], sessions_dir=sessions_dir)
        r2 = ex.run(["session-b.json"], sessions_dir=sessions_dir)
        assert r1.id == "reflect-2026-06-22-001"
        assert r2.id == "reflect-2026-06-22-002"


# ============================================================
# 情绪缓存集成
# ============================================================


class TestEmotionCacheIntegration:
    """executor 调 score_emotion → 缓存按 session_paths[0] 命中。"""

    def test_emotion_uses_session_path_as_cache_key(
        self, vault_dir: tuple[Path, Path]
    ) -> None:
        d, sessions_dir = vault_dir
        vault = Vault(d)
        # 同 batch: 第一 session 调 provider 一次(emotion),executor 总共 2 调
        provider = _make_provider("body", 0.3, 0.4)
        ex = ReflectExecutor(vault, provider, mortis_name="M")
        ex.run(["session-a.json"], sessions_dir=sessions_dir)
        # reflection(1 次) + emotion(1 次) = 2
        assert provider._call_count == 2

    def test_second_run_same_session_hits_cache(
        self, vault_dir: tuple[Path, Path]
    ) -> None:
        """同 vault 第二次 run 同一首个 session → emotion 缓存命中,
        provider 调用数 = 1(reflection 1 次 + emotion 0 次)。"""
        d, sessions_dir = vault_dir
        vault = Vault(d)
        provider = _make_provider("body", 0.3, 0.4)
        ex = ReflectExecutor(vault, provider, mortis_name="M")
        ex.run(["session-a.json"], sessions_dir=sessions_dir)  # 2 calls
        ex.run(["session-a.json"], sessions_dir=sessions_dir)  # emotion 命中
        # reflection 走 prompt(LLM 重新生成文本) + emotion 命中 → 共 1 次
        assert provider._call_count == 3  # 2 + 1


# ============================================================
# 路径辅助
# ============================================================


class TestPathHelpers:
    def test_reflection_rel_format(self) -> None:
        assert (
            reflection_rel("reflect-2026-06-22-001")
            == f"{SUBCONSCIOUS_ROOT}/{PENDING_REFLECTIONS_SUBDIR}/reflect-2026-06-22-001.md"
        )

    def test_list_pending_reflections_empty(self, vault_dir: tuple[Path, Path]) -> None:
        d, _ = vault_dir
        vault = Vault(d)
        assert list_pending_reflections(vault) == []

    def test_list_pending_reflections_after_runs(
        self, vault_dir: tuple[Path, Path]
    ) -> None:
        d, sessions_dir = vault_dir
        vault = Vault(d)
        provider = _make_provider("x", 0.0, 0.0)
        ex = ReflectExecutor(vault, provider, mortis_name="M")
        ex.run(["session-a.json"], sessions_dir=sessions_dir)
        ex.run(["session-b.json"], sessions_dir=sessions_dir)
        paths = list_pending_reflections(vault)
        assert len(paths) == 2
        assert all("pending-reflections" in p for p in paths)


# ============================================================
# 错误处理
# ============================================================


class TestErrors:
    def test_empty_session_paths_raises(self, vault_dir: tuple[Path, Path]) -> None:
        d, _ = vault_dir
        vault = Vault(d)
        provider = MockProvider()
        ex = ReflectExecutor(vault, provider, mortis_name="M")
        with pytest.raises(ValueError):
            ex.run([])

    def test_missing_session_raises(self, vault_dir: tuple[Path, Path]) -> None:
        d, _ = vault_dir
        vault = Vault(d)
        provider = MockProvider()
        ex = ReflectExecutor(vault, provider, mortis_name="M")
        with pytest.raises(FileNotFoundError):
            ex.run(["nonexistent.json"])

    def test_empty_llm_response_uses_placeholder(
        self, vault_dir: tuple[Path, Path]
    ) -> None:
        """LLM 返回空 → body 用占位符(不抛错)。"""
        d, sessions_dir = vault_dir
        vault = Vault(d)
        provider = MockProvider(responses=["", '{"valence": 0.0, "arousal": 0.0}'])
        ex = ReflectExecutor(vault, provider, mortis_name="M")
        r = ex.run(["session-a.json"], sessions_dir=sessions_dir)
        assert r.body  # 不空(占位符)
        assert "no reflection" in r.body.lower()


# ============================================================
# 文件布局
# ============================================================


class TestFileLayout:
    def test_subconscious_dir_created_lazy(
        self, vault_dir: tuple[Path, Path]
    ) -> None:
        """首次 run 自动创建 mortis-subconscious/pending-reflections/。"""
        d, sessions_dir = vault_dir
        vault = Vault(d)
        # 初始不应有
        assert not (d / "mortis-subconscious").exists()
        provider = _make_provider("body", 0.0, 0.0)
        ex = ReflectExecutor(vault, provider, mortis_name="M")
        ex.run(["session-a.json"], sessions_dir=sessions_dir)
        assert (d / "mortis-subconscious" / "pending-reflections").is_dir()

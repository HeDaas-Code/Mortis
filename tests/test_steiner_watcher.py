"""Test mortis.steiner.watcher — GrowthWatcher handler 逻辑。

issue #24 acceptance:
- watcher 拆 handler 逻辑(可测)和 observer 线程(不真起)
- handler 监听 .md 文件(忽略 .* / 临时文件)
- 创建 + 修改 → callback(dim);删除 → 忽略
- dimension 从 rel path 推断

测试策略:不真起 watchdog observer(耗时+不稳定),
直接构造 FakeEvent 调 handler.on_modified / on_created 验证 callback。
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mortis.growth.model import Dimension
from mortis.steiner.watcher import (
    FakeEvent,
    GrowthWatcher,
    _GrowthEventHandler,
    _infer_dimension_from_path,
    _is_interesting,
)


# ============================================================
# fixtures
# ============================================================


@pytest.fixture
def vault_root() -> Path:
    """临时 vault 根。"""
    with tempfile.TemporaryDirectory(prefix="mortis-steiner-watcher-") as td:
        yield Path(td)


@pytest.fixture
def callback() -> MagicMock:
    """可记录调用的 callback mock。"""
    return MagicMock()


# ============================================================
# Test 1: on_modified 触发 callback
# ============================================================


class TestOnModified:
    """on_modified:正常 .md 触发 callback + dim 正确。"""

    def test_modified_md_triggers_callback_with_dim(
        self, vault_root: Path, callback: MagicMock
    ) -> None:
        """修改 .md → callback 被调 + dim 正确。"""
        handler = _GrowthEventHandler(vault_root, callback)
        target = vault_root / "mortis-growth" / "identity" / "g1.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("body", encoding="utf-8")

        handler.on_modified(FakeEvent(src_path=str(target)))

        callback.assert_called_once_with(Dimension.IDENTITY)


# ============================================================
# Test 2: 忽略规则
# ============================================================


class TestIgnoreRules:
    """非 .md / 目录事件 / 删除 / 临时文件 / 未知 dim → 不调 callback。"""

    def test_non_md_directory_deleted_temp_and_unknown_dim_ignored(
        self, vault_root: Path, callback: MagicMock
    ) -> None:
        """5 类忽略场景全部不调 callback。"""
        handler = _GrowthEventHandler(vault_root, callback)
        base = vault_root / "mortis-growth" / "values"
        base.mkdir(parents=True, exist_ok=True)

        # 1. 非 .md
        handler.on_modified(FakeEvent(src_path=str(base / "g1.txt")))
        # 2. 目录事件
        handler.on_modified(FakeEvent(
            src_path=str(vault_root / "mortis-growth" / "agency"),
            is_directory=True,
        ))
        # 3. 删除事件(用 MagicMock 模拟,内部 type hint 是 FileSystemEvent)
        mock_del = MagicMock()
        mock_del.is_directory = False
        mock_del.src_path = str(base / "g1.md")
        handler.on_deleted(mock_del)
        # 4. 临时文件
        for name in ["g1.md.swp", "g1.md~", ".#g1.md", ".g1.md"]:
            handler.on_modified(FakeEvent(src_path=str(base / name)))
        # 5. 未知 dim 子目录
        unknown = vault_root / "mortis-growth" / "bogus" / "x.md"
        unknown.parent.mkdir(parents=True, exist_ok=True)
        unknown.write_text("body", encoding="utf-8")
        handler.on_modified(FakeEvent(src_path=str(unknown)))

        callback.assert_not_called()


# ============================================================
# Test 3: 7 维度全覆盖
# ============================================================


class TestAllDimensions:
    """7 维度都能正确推断。"""

    def test_all_seven_dimensions_detected(
        self, vault_root: Path, callback: MagicMock
    ) -> None:
        """7 维度的子目录都能被正确识别。"""
        handler = _GrowthEventHandler(vault_root, callback)
        for dim in Dimension:
            target = vault_root / "mortis-growth" / dim.value / "g1.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("body", encoding="utf-8")
            handler.on_created(FakeEvent(src_path=str(target), event_type="created"))
        # callback 被调 7 次,每次对应一个 Dimension
        assert callback.call_count == 7
        called_dims = {c.args[0] for c in callback.call_args_list}
        assert called_dims == set(Dimension)


# ============================================================
# Test 4: on_created
# ============================================================


class TestOnCreated:
    """on_created:创建事件 → callback(dim)。"""

    def test_created_md_triggers_callback(
        self, vault_root: Path, callback: MagicMock
    ) -> None:
        """创建 .md → callback 被调。"""
        handler = _GrowthEventHandler(vault_root, callback)
        target = vault_root / "mortis-growth" / "creativity" / "new.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("body", encoding="utf-8")

        handler.on_created(FakeEvent(src_path=str(target), event_type="created"))

        callback.assert_called_once_with(Dimension.CREATIVITY)


# ============================================================
# Test 5: GrowthWatcher 包装
# ============================================================


class TestGrowthWatcher:
    """GrowthWatcher 类对外 API + callback 透传。"""

    def test_handler_exposed_and_callback_forwarded(
        self, vault_root: Path
    ) -> None:
        """GrowthWatcher.handler 暴露内部 handler + callback 透传。"""
        cb = MagicMock()
        w = GrowthWatcher(vault_root, cb)
        assert isinstance(w.handler, _GrowthEventHandler)
        # 通过 handler 触发,验证 callback 是同一个
        target = vault_root / "mortis-growth" / "mortality" / "x.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("body", encoding="utf-8")
        w.handler.on_modified(FakeEvent(src_path=str(target)))
        cb.assert_called_once_with(Dimension.MORTALITY)

    def test_on_moved_uses_dest_path(
        self, vault_root: Path, callback: MagicMock
    ) -> None:
        """on_moved:用 dest_path 推断 dim(避免 src_path 已是旧位置)。"""
        handler = _GrowthEventHandler(vault_root, callback)
        dest = vault_root / "mortis-growth" / "relations" / "moved.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("body", encoding="utf-8")

        # 模拟 watchdog FileMovedEvent:有 dest_path 属性
        mock_moved = MagicMock()
        mock_moved.is_directory = False
        mock_moved.src_path = "/some/old/path.md"
        mock_moved.dest_path = str(dest)
        handler.on_moved(mock_moved)

        callback.assert_called_once_with(Dimension.RELATIONS)


# ============================================================
# Test 6-8: 路径推断纯函数
# ============================================================


class TestPathHelpers:
    """_infer_dimension_from_path / _is_interesting 单元测试。"""

    def test_infer_dim_handles_invalid_paths(self, vault_root: Path) -> None:
        """_infer_dimension:非 growth 路径 + 未知子目录 → None。"""
        # 非 mortis-growth 根
        p1 = vault_root / "mortis-journal" / "notes" / "x.md"
        assert _infer_dimension_from_path(p1, vault_root) is None
        # growth 下但子目录不是 7 维度之一
        p2 = vault_root / "mortis-growth" / "bogus" / "x.md"
        assert _infer_dimension_from_path(p2, vault_root) is None
        # 正常路径
        p3 = vault_root / "mortis-growth" / "creativity" / "x.md"
        assert _infer_dimension_from_path(p3, vault_root) == Dimension.CREATIVITY

    def test_is_interesting_accepts_md_rejects_temp(self) -> None:
        """_is_interesting:正常 .md 接受,临时文件拒绝。"""
        assert _is_interesting("foo.md")
        assert _is_interesting("mortis-growth/identity/x.md")
        assert not _is_interesting("foo.md.swp")
        assert not _is_interesting("foo.md~")
        assert not _is_interesting(".foo.md")
        assert not _is_interesting("foo.txt")

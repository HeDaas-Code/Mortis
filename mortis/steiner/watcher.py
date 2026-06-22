"""Mortis steiner — GrowthWatcher: 检测 mortis-growth/ 文件变更。

issue #24: 用 watchdog 监控 `mortis-growth/` 目录,owner 编辑 growth 时
触发 callback(Dimension)。

设计要点:
- 拆 handler 逻辑(可测)和 observer 线程(只 start/stop) — 测试不真起线程
- FileSystemEventHandler 处理 .md 文件(忽略 .* 和临时文件)
- 创建 + 修改 → callback(dim);删除 → 忽略(删除=信任 owner)
- dimension 从 rel path 推断:`mortis-growth/<dim>/<id>.md` 的 `<dim>`
- 不在白名单(steiner/ 不在 GROWTH_WHITELIST) — 用 Path 操作直接读 vault_root
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

try:
    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer
except ImportError:  # pragma: no cover - watchdog 是 issue #24 必要依赖
    FileSystemEvent = object  # type: ignore[assignment,misc]
    FileSystemEventHandler = object  # type: ignore[assignment,misc]
    Observer = None  # type: ignore[assignment]

from mortis.growth.model import Dimension
from mortis.growth.vault_layout import DIMENSION_DIRS, GROWTH_DIR


_logger = logging.getLogger(__name__)

# 反向映射:dim_dir 字符串 → Dimension
_DIM_FROM_DIR: dict[str, Dimension] = {v: k for k, v in DIMENSION_DIRS.items()}


@dataclass
class FakeEvent:
    """测试用 — 模拟 watchdog FileSystemEvent。

    is_directory: 目录事件(忽略)
    src_path: 绝对路径
    event_type: 'created' / 'modified' / 'deleted' / 'moved'
    """

    src_path: str
    event_type: str = "modified"
    is_directory: bool = False


def _infer_dimension_from_path(path: str | Path, root: Path) -> Optional[Dimension]:
    """从文件绝对路径推断 Dimension。

    路径形如: <root>/mortis-growth/<dim_dir>/<id>.md
    返回对应的 Dimension,无法推断(不在 growth 目录 / 维度子目录不识别)→ None。
    """
    p = Path(path)
    try:
        rel = p.relative_to(root)
    except ValueError:
        return None
    parts = rel.parts
    if len(parts) < 3:
        return None
    if parts[0] != GROWTH_DIR:
        return None
    dim_dir = parts[1]
    return _DIM_FROM_DIR.get(dim_dir)


def _is_interesting(path: str | Path) -> bool:
    """判断路径是否值得回调:是 .md 文件,不是隐藏文件,不是临时文件。"""
    p = Path(path)
    name = p.name
    if not name.endswith(".md"):
        return False
    if name.startswith("."):
        return False
    # 常见编辑器临时文件:foo.md.swp, .#foo.md, foo.md~
    if name.endswith((".swp", ".tmp", ".bak", "~")):
        return False
    if name.startswith(".#"):
        return False
    return True


class _GrowthEventHandler(FileSystemEventHandler):
    """watchdog event handler — 把文件事件转成 callback(Dimension)。

    公共类(不导出)— 测试直接调 on_modified/on_created 验证。
    """

    def __init__(
        self,
        root: Path,
        callback: Callable[[Dimension], None],
    ) -> None:
        self._root = root
        self._callback = callback

    def on_modified(self, event: FileSystemEvent) -> None:  # type: ignore[override]
        if getattr(event, "is_directory", False):
            return
        self._dispatch(event.src_path)

    def on_created(self, event: FileSystemEvent) -> None:  # type: ignore[override]
        if getattr(event, "is_directory", False):
            return
        self._dispatch(event.src_path)

    def on_deleted(self, event: FileSystemEvent) -> None:  # type: ignore[override]
        # 删除 = 信任 owner。issue #24 契约明确不触发。
        return

    def on_moved(self, event: FileSystemEvent) -> None:  # type: ignore[override]
        # move = 视为新位置出现 + 旧位置消失;这里简化为 modified 行为
        if getattr(event, "is_directory", False):
            return
        # watchdog FileMovedEvent 有 dest_path
        dest = getattr(event, "dest_path", None)
        if dest:
            self._dispatch(dest)
        else:
            self._dispatch(event.src_path)

    def _dispatch(self, path: str | Path) -> None:
        if not _is_interesting(path):
            return
        dim = _infer_dimension_from_path(path, self._root)
        if dim is None:
            return
        try:
            self._callback(dim)
        except Exception:  # pragma: no cover - 防御 callback 异常
            _logger.exception("growth watcher callback raised for %s", path)


class GrowthWatcher:
    """监控 vault.mortis-growth/,owner 编辑时调 callback(Dimension)。

    Args:
        vault_root: vault 根目录绝对路径。
        callback: 收到 .md 文件变更时调,参数是推断出的 Dimension。
                  同一事件的多次回调由调用方去重(本类不做 debounce)。

    生命周期:
        start() 启动 watchdog Observer 线程;
        stop() 停止并 join。
    """

    def __init__(
        self,
        vault_root: Path,
        callback: Callable[[Dimension], None],
    ) -> None:
        self._root = Path(vault_root).resolve()
        self._callback = callback
        self._observer: Optional["Observer"] = None
        # 抽出 handler 实例 — 测试可单独使用
        self._handler = _GrowthEventHandler(self._root, callback)

    @property
    def handler(self) -> _GrowthEventHandler:
        """返回内部的 event handler(测试可拿到它直接调 on_modified 验证)。"""
        return self._handler

    def start(self) -> None:
        """启动 watchdog Observer 监听 mortis-growth/。

        - 若目录不存在则先建(空目录占位,允许后续写入触发事件)
        - 若 watchdog 未安装则不启动(单元测试不依赖)
        """
        if Observer is None:
            _logger.warning("watchdog not installed; GrowthWatcher.start() is a no-op")
            return

        growth_dir = self._root / GROWTH_DIR
        growth_dir.mkdir(parents=True, exist_ok=True)

        self._observer = Observer()
        self._observer.schedule(self._handler, str(growth_dir), recursive=True)
        self._observer.start()

    def stop(self) -> None:
        """停止 observer,join 线程。重复 stop 幂等。"""
        if self._observer is None:
            return
        try:
            self._observer.stop()
            self._observer.join(timeout=2.0)
        finally:
            self._observer = None

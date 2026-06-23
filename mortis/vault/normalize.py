"""Mortis vault local — 栈式路径归一化工具 (issue #67 audit Critical-A)。

公开 API:
    normalize_rel_path(rel_path: str) -> str

设计:
- PurePosixPath 不消除 ..,需手动栈式归一化
- 空段 (a//b) 和 . 都跳过
- 栈空时 .. 被丢弃 (不允许逃出根)
- 返回纯字符串,方便后续 startswith / == 比较
"""
from __future__ import annotations


def normalize_rel_path(rel_path: str) -> str:
    """归一化相对路径,消除 .. 和 . 。

    Args:
        rel_path: 原始相对路径。

    Returns:
        归一化后的相对路径字符串(无前导 /,无 .. 或 . 段)。

    Examples:
        >>> normalize_rel_path("foo/bar")
        'foo/bar'
        >>> normalize_rel_path("foo/../bar")
        'bar'
        >>> normalize_rel_path("./foo/./bar")
        'foo/bar'
        >>> normalize_rel_path("../etc/passwd")
        'etc/passwd'  # 栈空时 .. 被丢弃(不允许逃出根)
        >>> normalize_rel_path("a/b/../c/./d//e")
        'a/c/d/e'
    """
    if not rel_path:
        return ""
    parts: list[str] = []
    for segment in rel_path.lstrip("/").split("/"):
        if segment == "" or segment == ".":
            continue
        if segment == "..":
            if parts:  # 弹掉上一级
                parts.pop()
            # 栈空时 .. 被丢弃(不允许逃出根)
            continue
        parts.append(segment)
    return "/".join(parts)
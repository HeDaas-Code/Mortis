"""Mortis growth frontmatter — 自写 YAML 子集解析。

issue #18 决定 override PyYAML：
- 零依赖（requirements.txt 只有 pytest）
- RFC §12 Vault-Native 原则 — 简单 `key: value` 语法足矣
- 字段类型简单（str / float / list[str] / None）

支持：
- key: string_value
- key: 0.5 (float)
- key: ["a", "b"] (inline list)
- key:  (block list, 缩进 dash 开头)

不支持：嵌套 dict / 多行 string / anchor / 复杂类型（用 PyYAML）。
"""

from __future__ import annotations

import re
from typing import Any

from .model import Dimension, DreamLevel, Growth


class FrontmatterError(ValueError):
    """frontmatter 解析错误。"""


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """从 md 文本提取 frontmatter dict + 剩余 body。

    文本必须以 `---\\n` 开头，并以 `---\\n` 结束 frontmatter 段。
    """
    m = _FRONTMATTER_RE.match(text)
    if m is None:
        raise FrontmatterError("missing or malformed frontmatter (---)")
    raw_meta, body = m.group(1), m.group(2)
    meta = _parse_meta_lines(raw_meta.splitlines())
    return meta, body


def serialize_frontmatter(meta: dict[str, Any], body: str) -> str:
    """frontmatter dict + body → 完整 md 文本。"""
    lines = ["---"]
    for key, value in meta.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {item}")
        elif value is None:
            lines.append(f"{key}:")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    if body:
        return "\n".join(lines) + "\n" + body
    return "\n".join(lines) + "\n"


def parse_growth_file(text: str) -> Growth:
    """md 文本 → Growth dataclass。"""
    meta, body = parse_frontmatter(text)
    try:
        return Growth(
            id=meta["id"],
            dimension=Dimension(meta["dimension"]),
            confidence=float(meta["confidence"]),
            created_at=meta["created_at"],
            last_validated=meta["last_validated"],
            source_sessions=tuple(meta.get("source_sessions", []) or []),
            dream_level=(
                DreamLevel(meta["dream_level"]) if meta.get("dream_level") else None
            ),
            emotional_valence=float(meta["emotional_valence"]),
            emotional_arousal=float(meta["emotional_arousal"]),
            tags=tuple(meta.get("tags", []) or []),
            body=body.rstrip("\n"),
        )
    except KeyError as e:
        raise FrontmatterError(f"missing required field: {e.args[0]}") from e
    except (ValueError, TypeError) as e:
        raise FrontmatterError(f"invalid field value: {e}") from e


def serialize_growth_file(growth: Growth) -> str:
    """Growth dataclass → md 文本。"""
    meta: dict[str, Any] = {
        "id": growth.id,
        "dimension": growth.dimension.value,
        "confidence": growth.confidence,
        "created_at": growth.created_at,
        "last_validated": growth.last_validated,
        "source_sessions": list(growth.source_sessions),
        "dream_level": growth.dream_level.value if growth.dream_level else "",
        "emotional_valence": growth.emotional_valence,
        "emotional_arousal": growth.emotional_arousal,
        "tags": list(growth.tags),
    }
    return serialize_frontmatter(meta, growth.body)


# ---------- 内部 ----------

def _parse_meta_lines(lines: list[str]) -> dict[str, Any]:
    """解析 frontmatter 内的 key: value 行（支持 block list）。"""
    meta: dict[str, Any] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if not line.startswith((" ", "\t")) and ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if value == "":
                # 可能是 block list（下一行缩进 dash）或空值
                block: list[str] = []
                j = i + 1
                while j < len(lines) and lines[j].lstrip().startswith("- "):
                    block.append(lines[j].lstrip()[2:].strip())
                    j += 1
                if block:
                    meta[key] = block
                    i = j
                else:
                    meta[key] = None
                    i += 1
            else:
                meta[key] = _coerce_scalar(value)
                i += 1
        else:
            raise FrontmatterError(f"unexpected frontmatter line: {line!r}")
    return meta


def _coerce_scalar(value: str) -> Any:
    """字符串 → Python 原生类型（仅支持 int / float / str / inline list）。"""
    # inline list: [a, b, c]
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_coerce_scalar(item.strip()) for item in inner.split(",")]
    # quoted string
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    # int / float
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    # 裸字符串（如 ISO8601、enum 值、None）
    if value == "null" or value == "~":
        return None
    return value

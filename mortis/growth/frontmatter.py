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

issue #19 增量：
- `parse_growth_file` 在反序列化时把 Obsidian-Native 结构（H1 标题 /
  `## 来源` 段 / `## 关联` 段 / `> [!note]` callout / `%%潜意识%%` 段）
  从 body 字段里剥离,只保留**用户原始的纯文本 body**。Obsidian-Native
  字段(wikilinks/tags_inline/callout/subconscious)由 vault 读写层
  (`_enrich_growth_with_obsidian`) 根据 vault 原文再回填。
- `serialize_growth_file` 保留旧行为（纯 frontmatter + body） — 给测试 /
  老调用方用。新写入路径走 `mortis.growth.writer.write_growth_obsidian`。
"""

from __future__ import annotations

import re
from typing import Any

from .model import Dimension, DreamLevel, Growth


class FrontmatterError(ValueError):
    """frontmatter 解析错误。"""


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)

# 剥离规则（issue #19 round-trip）:
# - 顶层 `# 标题` 行
# - `## 来源` / `## 关联` 段（及其下属列表项）
# - `## 验证历史` 段(issue #19 暂不实现写入,但解析时也剥离)
# - `> [!kind] ...` callout 块
# - `%%...%%` 块(单行 / 折叠)
_H1_LINE = re.compile(r"^#\s+.+?\n", re.MULTILINE)
_H2_SECTION = re.compile(
    r"^##\s+(?:来源|关联|验证历史)\s*\n(?:(?:\s*-\s+.+|\|.+\||\s*\n)+)?",
    re.MULTILINE,
)
_CALLOUT_BLOCK = re.compile(r"^>\s*\[!\w+\][^\n]*(?:\n>\s*[^\n]*)*", re.MULTILINE)
_COMMENT_BLOCK = re.compile(r"%%\n.*?\n%%", re.DOTALL)
_COMMENT_INLINE = re.compile(r"%%[^%\n][^%\n]*?%%")


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
    """frontmatter dict + body → 完整 md 文本。

    body 不参与 frontmatter 序列化 — 调用方自行拼装到 `---\\n` 之后。
    若 body 为空,只输出 frontmatter 段。
    """
    lines = ["---"]
    for key, value in meta.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {item}")
        elif value is None:
            lines.append(f"{key}:")
        elif isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    if body:
        return "\n".join(lines) + "\n" + body
    return "\n".join(lines) + "\n"


def parse_growth_file(text: str) -> Growth:
    """md 文本 → Growth dataclass。

    body 字段经过 Obsidian 剥离:移除 H1 标题 / `## 来源` 段 / `## 关联` 段 /
    `> [!kind]` callout 块 / `%%...%%` 注释块,只保留用户原始的纯文本。
    Obsidian-Native 字段(wikilinks / tags_inline / callout / subconscious)
    由 `mortis.vault.local._enrich_growth_with_obsidian` 在更上层根据
    vault 原文回填 — 本函数只保证 frontmatter 段 + 剥离后的 body 字段契约。
    """
    meta, body = parse_frontmatter(text)
    stripped_body = _strip_obsidian_structure(body)
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
            body=stripped_body,
        )
    except KeyError as e:
        raise FrontmatterError(f"missing required field: {e.args[0]}") from e
    except (ValueError, TypeError) as e:
        raise FrontmatterError(f"invalid field value: {e}") from e


def serialize_growth_file(growth: Growth) -> str:
    """Growth dataclass → md 文本（旧版,纯 frontmatter + body）。

    新写入路径应使用 `mortis.growth.writer.write_growth_obsidian` —
    生成完整的 Obsidian-Native 格式 (含 H1 / callout / subconscious 段)。
    本函数保留为**纯序列化**的底层工具（无 Obsidian 结构加成）,
    供 frontmatter 层测试和反序列化 round-trip 用。
    """
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


# ----- 内部: Obsidian 结构剥离 (issue #19) -----


def _strip_obsidian_structure(body: str) -> str:
    """从 body 字段中移除 Obsidian-Native 结构段。

    移除顺序:先块(折叠/callout),再 H1 / H2 段(避免顺序依赖)。
    返回的 body 保留用户原始纯文本 + 普通 markdown 段落(双链/标签原样)。
    """
    if not body:
        return body
    out = body
    out = _COMMENT_BLOCK.sub("", out)
    out = _COMMENT_INLINE.sub("", out)
    out = _CALLOUT_BLOCK.sub("", out)
    out = _H2_SECTION.sub("", out)
    out = _H1_LINE.sub("", out)
    # 规范化:合并连续空行,strip 首尾
    lines = out.split("\n")
    normalized: list[str] = []
    prev_blank = True
    for line in lines:
        is_blank = line.strip() == ""
        if is_blank and prev_blank:
            continue
        normalized.append(line)
        prev_blank = is_blank
    while normalized and normalized[-1].strip() == "":
        normalized.pop()
    return "\n".join(normalized)


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

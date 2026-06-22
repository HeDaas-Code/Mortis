"""Mortis growth Obsidian-Native writer — 按 RFC §12.3 生成完整 md 文本。

issue #19: 把 Growth dataclass 序列化为 Obsidian 风格 md 文件。

布局(RFC §12.3):
```
---
<frontmatter — id/dimension/confidence/created_at/last_validated/
              source_sessions/dream_level/emotional_valence/emotional_arousal/tags>
---

# <H1 标题 — body 第一句>

<body — 纯文本,含双链/标签/callout 原样>

## 来源
- [[session-xxx]] — <可选描述>

## 关联
- [[growth-yyy]] — <可选描述>

## 验证历史
| 日期 | 场景 | 结果 |
|------|------|------|
| <date> | <scene> | <result> |

> [!note]
> <callout 内容>   (callout 字段非空时)

%%<subconscious>%%   (subconscious 字段非空时)
```

设计原则:
- frontmatter 段:复用 frontmatter.serialize_frontmatter(序列化元数据)。
- body 段:手工拼装(不通用模板 — Obsidian-Native 是 growth 专用结构)。
- 缺失的可选段(来源/关联/验证历史/callout/subconscious)按字段是否为空**自动跳过**。
- **重复写入幂等性**:writer 在追加 `%%subconscious%%` 段之前会先剥离 body
  里**已存在**的 `%%...%%` 注释/折叠块。否则 write→read→write 会在 body
  末尾出现 `%%content%%%%content%%` 重复(vault.read 时 Obsidian 解析
  subconscious 字段是 body 原 `%%` 块的内容,新写时再拼一份就重复)。
- round-trip:write_growth_obsidian(g) 产生的文本能被
  `parse_growth_file + Obsidian parse` 还原出等价的 Growth。
"""

from __future__ import annotations

from typing import Iterable

from mortis.vault.obsidian import (
    Wikilink,
    parse as parse_obsidian,
    render_callout,
    render_subconscious,
    render_wikilink,
)

from .frontmatter import serialize_frontmatter
from .model import DreamLevel, Growth


def write_growth_obsidian(
    growth: Growth,
    related_growths: Iterable[Growth] = (),
) -> str:
    """生成 Obsidian-Native 格式的 growth md 文本。

    Args:
        growth: 待序列化的 Growth。
        related_growths: 关联 growth 列表 — 用于 ## 关联 段的双链。
            默认空(REFLECT 写时,owner 还没指定关联)。

    Returns:
        完整 md 文本(含 frontmatter + Obsidian 结构)。
    """
    # 幂等:剥离 body 中已存在的潜意识注释/折叠块 — writer 末尾会重新生成
    clean_body = _strip_existing_subconscious(growth.body)

    parts: list[str] = []
    parts.append(serialize_frontmatter(_frontmatter_meta(growth), ""))
    parts.append("")  # frontmatter 收尾空行
    parts.append(_title(growth, clean_body))
    parts.append("")
    parts.append(clean_body.rstrip())
    parts.append("")

    if growth.source_sessions:
        parts.append("## 来源")
        for sid in growth.source_sessions:
            parts.append(f"- {render_wikilink(sid)}")
        parts.append("")

    related_list = list(related_growths)
    if related_list:
        parts.append("## 关联")
        for rg in related_list:
            parts.append(f"- {render_wikilink(rg.id)}")
        parts.append("")

    if growth.callout:
        parts.append(render_callout("note", growth.callout))
        parts.append("")

    if growth.subconscious:
        parts.append(render_subconscious(growth.subconscious))
        parts.append("")

    text = "\n".join(parts)
    # 收尾:确保恰好一个换行
    return text.rstrip() + "\n"


def extract_wikilinks_from_body(body: str) -> tuple[str, ...]:
    """从 body 提取 `[[双链]]` 目标名列表(去重,保序)。

    工具函数 — 反向回填 Growth.wikilinks 字段时用。
    """
    parsed = parse_obsidian(body)
    seen: set[str] = set()
    out: list[str] = []
    for link in parsed.wikilinks:
        if link.target not in seen:
            seen.add(link.target)
            out.append(link.target)
    return tuple(out)


def extract_tags_inline_from_body(body: str) -> tuple[str, ...]:
    """从 body 提取 `#tag` 列表(去重,保序)。

    工具函数 — 反向回填 Growth.tags_inline 字段时用。
    """
    parsed = parse_obsidian(body)
    seen: set[str] = set()
    out: list[str] = []
    for tag in parsed.tags_inline:
        if tag not in seen:
            seen.add(tag)
            out.append(tag)
    return tuple(out)


# ============================================================
# 内部
# ============================================================


def _frontmatter_meta(growth: Growth) -> dict[str, object]:
    """Growth → frontmatter dict。

    dream_level 为 None 时序列化为空字符串(旧 serialize_growth_file 约定)。
    """
    return {
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


def _title(growth: Growth, body: str | None = None) -> str:
    """生成 `# <H1 标题>` 段。

    策略:取 body 第一句(按中文/英文/句号分句)作为标题。
    失败时回退到 `id`。
    """
    src = (body if body is not None else growth.body).strip()
    if not src:
        return f"# {growth.id}"
    for sep in ("。", ".", "!", "?", "！", "?"):
        idx = src.find(sep)
        if idx != -1 and idx < 80:
            return f"# {src[: idx + 1].strip()}"
    head = src.split("\n", 1)[0].strip()
    if len(head) <= 80:
        return f"# {head}"
    return f"# {head[:80]}…"


def _strip_existing_subconscious(body: str) -> str:
    """从 body 中剥离已存在的 `%%...%%` 注释(单行 + 折叠块)。

    目的:writer 幂等性 — 避免 write→read→write 重复追加潜意识段。
    复用 Obsidian 解析层得到的 fold/comments 信息,**只移除**这些块,
    保留双链/标签/callout 等其他 Obsidian 结构(这些是用户原意,不应清掉)。
    """
    parsed = parse_obsidian(body)
    if not parsed.comments and not parsed.foldable_sections:
        return body
    out = body
    # 折叠块(块形式 `%%\\n...\\n%%`)逐个剥离
    for fold in parsed.foldable_sections:
        # 用 Fold.render() 重构块文本(含 `%%\\n...\\n%%`)再 sub
        marker = render_subconscious(fold.body)
        out = out.replace(marker, "", 1)
    # 单行注释 `%%xxx%%` 逐个剥离
    for comment in parsed.comments:
        marker = f"%%{comment}%%"
        out = out.replace(marker, "", 1)
    # 规范化空行
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

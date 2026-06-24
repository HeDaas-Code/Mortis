"""Mortis runtime — growth 检索与 system prompt 生成。

issue #20: 主人格能检索 growth,注入 system prompt。

设计原则:
- search_growths 是**纯函数** — 接收 vault + filter 参数,返回 Growth 列表。
  不依赖 RuntimeContext 状态(便于测试 + sub API 复用)。
- growth_system_prompt 是**格式化函数** — 接收已查好的 Growth 列表,返回 markdown。
  排序:同维度内按 last_validated 降序(最新的优先);整体按 confidence 降序。
- 注入点:RuntimeContext.messages_for_provider 内部追加 — tone 段后,
  step output 之前。**不破坏**既有 msgs[0] == tone system 的契约
  (issue #18 阶段),而是用额外 system message 追加。
"""

from __future__ import annotations

from typing import Iterable

from mortis.growth.frontmatter import FrontmatterError
from mortis.growth.model import Dimension, DreamLevel, Growth
from mortis.redact import redact_snippet
from mortis.vault.local import Vault


# ============================================================
# 检索
# ============================================================


def search_growths(
    vault: Vault,
    *,
    dimension: Dimension | None = None,
    tag: str | None = None,
    query: str | None = None,
    min_confidence: float = 0.0,
    limit: int = 10,
) -> list[Growth]:
    """按维度/标签/全文/置信度过滤 growth。

    Args:
        vault: 目标 vault。
        dimension: 可选维度过滤。
        tag: 可选 frontmatter tag 过滤(精确匹配)。
        query: 全文关键词 — 命中 body 文本 / wikilink target / tags_inline
            任一即算命中(case-insensitive substring match)。
        min_confidence: 置信度下界(>= 边界,非 >)。
        limit: 返回数量上限。

    Returns:
        排序后的 Growth 列表: 先按 confidence 降序,后按 last_validated 降序。
        解析失败的文件跳过(不污染结果)。
    """
    # 1. 取路径候选 — list_growths 按 dimension 子目录过滤
    try:
        paths = vault.list_growths(dimension=dimension)
    except Exception:
        return []

    # 2. 逐个 read + 多重过滤
    candidates: list[Growth] = []
    for rel in paths:
        try:
            g = vault.read_growth(rel)
        except (FileNotFoundError, FrontmatterError):
            continue
        if g.confidence < min_confidence:
            continue
        if tag is not None and tag not in g.tags:
            continue
        if query is not None and not _matches_query(g, query):
            continue
        candidates.append(g)

    # 3. 排序: confidence 降序 → last_validated 降序
    candidates.sort(
        key=lambda g: (g.confidence, g.last_validated),
        reverse=True,
    )
    # 4. limit
    return candidates[:limit]


def _matches_query(g: Growth, query: str) -> bool:
    """全文搜索匹配 — body / wikilinks / tags_inline / frontmatter tags 都参与。"""
    q = query.lower()
    haystacks: list[str] = [
        g.body.lower(),
        " ".join(g.wikilinks).lower(),
        " ".join(g.tags_inline).lower(),
        " ".join(g.tags).lower(),
    ]
    if g.callout is not None:
        haystacks.append(g.callout.lower())
    return any(q in h for h in haystacks)


# ============================================================
# System prompt 生成
# ============================================================


def growth_system_prompt(growths: Iterable[Growth]) -> str:
    """把 Growth 列表格式化为注入 system 的 markdown 段。

    格式:
        ## 当前人格成长（来自长期记忆）
        ### <dimension 中文/英文>（N 条）
        - <body 第一行 / 截断>
        ### ...

    Returns:
        完整 markdown 段(含头标题)。如果 growths 为空,返回空字符串
        (调用方不注入 — 避免无意义空白)。
    """
    items = list(growths)
    if not items:
        return ""

    by_dim: dict[Dimension, list[Growth]] = {}
    for g in items:
        by_dim.setdefault(g.dimension, []).append(g)

    lines: list[str] = ["## 当前人格成长（来自长期记忆）"]
    for dim, group in by_dim.items():
        # 同维度内按 last_validated 降序(最新优先)
        group.sort(key=lambda g: g.last_validated, reverse=True)
        lines.append(f"### {dim.value}（{len(group)} 条）")
        for g in group:
            preview = _preview_body(g)
            lines.append(f"- {preview}")

    return "\n".join(lines)


def _preview_body(g: Growth) -> str:
    """生成单条 growth 的 preview 行 — body 第一句(截断 60 字符)。

    issue #85: body 注入 system prompt 前先 redact — 过滤 dream callout /
    emotion 标签 / subconscious 注释等 owner 私密字段 (HARNESS.md '数据不外流')。
    只 redact body; growth 的其他字段 (dimension, confidence, tags 等) 不受影响。
    """
    src = redact_snippet(g.body).strip()
    if not src:
        return f"[{g.id}] (empty body)"
    for sep in ("。", ".", "!", "?", "！", "?"):
        idx = src.find(sep)
        if idx != -1 and idx < 80:
            src = src[: idx + 1]
            break
    else:
        # 没找到分句符 — 按换行取首行
        src = src.split("\n", 1)[0]
    if len(src) > 60:
        src = src[:60] + "…"
    return f"[{g.id}] {src}"

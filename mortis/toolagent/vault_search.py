"""Mortis toolagent — VaultSearchAgent: 全文搜索 + 标签 + 双链图遍历。

issue #25: vault 只读 Agent。组合 search_growths + Obsidian 解析做双链图。

输入 schema (input dict):
    query: str | None = None         # 全文关键词
    tags: list[str] | None = None    # frontmatter tag 过滤
    traverse_links: bool = False     # 双链图遍历
    max_depth: int = 2               # BFS 深度 (1=只查 matched; 2=查 matched + 邻居)

输出 schema (ToolResult.data dict):
    matches: list[dict]   # [{"rel_path": str, "title": str, "snippet": str}, ...]
    graph: dict | None    # traverse_links=True 时 {target: [source1, source2, ...]}
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from mortis.toolagent.base import ToolResult
from mortis.vault import Vault
from mortis.vault.obsidian import parse as parse_obsidian


class VaultSearchAgent:
    """vault 全文 + tag + 双链图搜索。"""

    agent_id: str = "vault:search"

    def __init__(self, vault: Vault) -> None:
        self.vault = vault

    def execute(self, input: dict) -> ToolResult:
        query = input.get("query")
        tags = input.get("tags")
        traverse_links = bool(input.get("traverse_links", False))
        max_depth = int(input.get("max_depth", 2))
        if max_depth < 1:
            max_depth = 1

        try:
            # 1. 先用 search_growths 拿候选(基于 tag / query 粗筛)
            if tags:
                rels_by_tag: set[str] = set()
                for t in tags:
                    rels_by_tag.update(self.vault.list_growths_by_tag(t))
                rels = sorted(rels_by_tag)
            else:
                rels = self.vault.list_growths()

            # 2. 全文过滤
            matches: list[dict] = []
            if query:
                q = query.lower()
                for rel in rels:
                    try:
                        g = self.vault.read_growth(rel)
                    except Exception:
                        continue
                    if q in g.body.lower() or any(q in t.lower() for t in g.tags_inline):
                        matches.append({
                            "rel_path": rel,
                            "title": g.id,
                            "snippet": _snippet(g.body, q),
                        })
            else:
                # 无 query → 全返回(只过滤 tag)
                for rel in rels:
                    matches.append({"rel_path": rel, "title": rel.split("/")[-1], "snippet": ""})

            # 3. 双链图遍历
            graph: dict[str, list[str]] | None = None
            if traverse_links and matches:
                graph = self._bfs_links(matches, max_depth)

            return ToolResult(
                success=True,
                data={"matches": matches, "graph": graph},
                error=None,
            )
        except Exception as e:  # noqa: BLE001
            return ToolResult(success=False, data=None, error=str(e))

    def _bfs_links(
        self, seeds: list[dict], max_depth: int
    ) -> dict[str, list[str]]:
        """BFS 双链图遍历 — 返回 {target: [source1, source2, ...]}。

        seeds 是 matches 列表;BFS 从每个 seed 出发,解析 wikilinks 拿邻居。
        """
        graph: dict[str, list[str]] = defaultdict(list)
        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque()

        for s in seeds:
            rel = s["rel_path"]
            if rel not in visited:
                visited.add(rel)
                queue.append((rel, 0))

        while queue:
            rel, depth = queue.popleft()
            if depth >= max_depth:
                continue
            try:
                g = self.vault.read_growth(rel)
            except Exception:
                continue
            parsed = parse_obsidian(g.body)
            for link in parsed.wikilinks:
                target = link.target
                graph[target].append(rel)
                # 假设 wikilink target 是 relative .md path (没有就 raw)
                # 简化:不加进 visited queue — BFS 已经按 depth 限
                if depth + 1 < max_depth:
                    # 试图 resolve 为完整 rel_path 继续 BFS
                    target_rel = _resolve_link(target, rel)
                    if target_rel and target_rel not in visited:
                        visited.add(target_rel)
                        queue.append((target_rel, depth + 1))

        return dict(graph)


def _snippet(body: str, query: str, context: int = 30) -> str:
    """截 query 前后 30 字符做 snippet。"""
    idx = body.lower().find(query)
    if idx < 0:
        return body[:60]
    start = max(0, idx - context)
    end = min(len(body), idx + len(query) + context)
    return body[start:end]


def _resolve_link(target: str, from_rel: str) -> str | None:
    """把 wikilink target 解析为 vault rel path。

    简化:target 不含 .md → 加 .md;不含 / → 当作与 from_rel 同目录。
    """
    if not target:
        return None
    if "/" in target:
        rel = target if target.endswith(".md") else target + ".md"
        return rel
    # 同目录
    parent = "/".join(from_rel.split("/")[:-1])
    rel = f"{parent}/{target}" if parent else f"{target}.md"
    return rel if rel.endswith(".md") else rel + ".md"


__all__ = ["VaultSearchAgent"]

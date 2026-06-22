"""Mortis toolagent — MarkdownRenderAgent: Obsidian 文本解析。

issue #25: 无 vault 权限 Agent。直接接收 content 字符串,调 Obsidian 解析层。

输入 schema (input dict):
    content: str     # 必填,Obsidian-flavored markdown 文本

输出 schema (ToolResult.data dict):
    wikilinks: list[str]       # 双链 target 列表
    embed_links: list[str]     # 嵌入链接 target 列表
    tags: list[str]            # 行内 #tag
    callouts: list[dict]       # [{"kind": str, "body": str, "title": str|None}, ...]
    frontmatter: dict          # 简单 YAML 风格 frontmatter (key=value 多行合并)
"""

from __future__ import annotations

import re
from typing import Any

from mortis.toolagent.base import ToolResult
from mortis.vault.obsidian import parse as parse_obsidian


_FRONT_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


class MarkdownRenderAgent:
    """Obsidian 文本解析 Agent — 不读 vault,只处理传入的字符串。"""

    agent_id: str = "markdown:render"

    def __init__(self) -> None:
        pass

    def execute(self, input: dict) -> ToolResult:
        content = input.get("content")
        if not isinstance(content, str):
            return ToolResult(
                success=False, data=None, error="missing or invalid 'content'"
            )

        try:
            parsed = parse_obsidian(content)
            fm = _parse_frontmatter(content)
            return ToolResult(
                success=True,
                data={
                    "wikilinks": [w.target for w in parsed.wikilinks],
                    "embed_links": [w.target for w in parsed.embed_links],
                    "tags": list(parsed.tags_inline),
                    "callouts": [
                        {
                            "kind": c.kind,
                            "body": c.body,
                            "title": c.title,
                        }
                        for c in parsed.callouts
                    ],
                    "frontmatter": fm,
                },
                error=None,
            )
        except Exception as e:  # noqa: BLE001
            return ToolResult(success=False, data=None, error=str(e))


def _parse_frontmatter(content: str) -> dict[str, Any]:
    """简易 frontmatter 解析: `key: value` 多行合并为 list。

    不依赖 PyYAML (避免新增依赖)。
    """
    m = _FRONT_RE.match(content)
    if not m:
        return {}
    block = m.group(1)
    result: dict[str, Any] = {}
    current_key: str | None = None
    current_list: list[str] | None = None
    for line in block.splitlines():
        if not line.strip():
            continue
        # list item: "  - value"
        if line.lstrip().startswith("- ") and current_key and current_list is not None:
            current_list.append(line.lstrip()[2:].strip())
            continue
        # key: value or key:
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value == "":
            # 开始新 list
            current_key = key
            current_list = []
            result[key] = current_list
        else:
            current_key = key
            current_list = None
            # 数字 / bool 简单转换
            if value.lower() in ("true", "false"):
                result[key] = value.lower() == "true"
            elif _is_number(value):
                result[key] = _to_number(value)
            else:
                # 去引号
                if (value.startswith('"') and value.endswith('"')) or \
                   (value.startswith("'") and value.endswith("'")):
                    value = value[1:-1]
                result[key] = value
    return result


def _is_number(s: str) -> bool:
    try:
        float(s)
        return True
    except (ValueError, TypeError):
        return False


def _to_number(s: str) -> int | float:
    try:
        return int(s)
    except ValueError:
        return float(s)


__all__ = ["MarkdownRenderAgent"]

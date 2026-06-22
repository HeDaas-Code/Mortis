"""Mortis toolagent — VaultReadAgent: 读 vault 文件 + 双链解析。

issue #25: vault 只读 Agent。读 md 文件 + 可选双链解析。

输入 schema (input dict):
    rel_path: str              # 必填
    resolve_links: bool = False  # 是否调 Obsidian 解析层拆 wikilinks

输出 schema (ToolResult.data dict):
    content: str                # 文件原文
    rel_path: str               # 原 rel_path
    links: list[str] | None     # resolve_links=True 时为 wikilink target 列表
"""

from __future__ import annotations

from typing import Any

from mortis.toolagent.base import ToolAgent, ToolResult
from mortis.vault import Vault
from mortis.vault.obsidian import parse as parse_obsidian


class VaultReadAgent(ToolAgent):
    """读 vault 文件,可选解析 Obsidian 双链。

    用 ToolAgent 包装层 — 不重新定义 ToolResult 翻译,直接复用 base.py。
    agent_id 默认 "vault:read"。
    """

    def __init__(
        self,
        vault: Vault,
        agent_id: str = "vault:read",
    ) -> None:
        self.vault = vault
        self.agent_id = agent_id

    def execute(self, input: dict) -> ToolResult:
        rel_path = input.get("rel_path")
        if not isinstance(rel_path, str) or not rel_path:
            return ToolResult(
                success=False, data=None, error="missing or invalid 'rel_path'"
            )

        resolve_links = bool(input.get("resolve_links", False))

        try:
            entry = self.vault.read(rel_path)
        except FileNotFoundError as e:
            return ToolResult(success=False, data=None, error=str(e))
        except Exception as e:  # noqa: BLE001
            return ToolResult(success=False, data=None, error=f"vault.read failed: {e}")

        data: dict[str, Any] = {
            "content": entry.content,
            "rel_path": rel_path,
        }
        if resolve_links:
            parsed = parse_obsidian(entry.content)
            data["links"] = [w.target for w in parsed.wikilinks]
        else:
            data["links"] = None

        return ToolResult(success=True, data=data, error=None)


__all__ = ["VaultReadAgent"]

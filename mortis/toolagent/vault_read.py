"""Mortis toolagent — VaultReadAgent: 读 vault 文件 + 双链解析 + 摘要。

issue #25: vault 只读 Agent。读 md 文件 + 可选双链解析。

issue #63: 新增摘要能力 — 通过 LLM 对文件内容进行摘要。

输入 schema (input dict):
    rel_path: str              # 必填
    resolve_links: bool = False  # 是否调 Obsidian 解析层拆 wikilinks
    summarize: bool = False      # 是否生成摘要 (issue #63)
    summary_length: int = 100    # 摘要长度(字符数)

输出 schema (ToolResult.data dict):
    content: str                # 文件原文
    rel_path: str               # 原 rel_path
    links: list[str] | None     # resolve_links=True 时为 wikilink target 列表
    summary: str | None         # summarize=True 时的 LLM 摘要
"""

from __future__ import annotations

from typing import Any

from mortis.provider.base import LLMProviderProtocol
from mortis.toolagent.base import ToolAgent, ToolResult
from mortis.vault import Vault
from mortis.vault.normalize import normalize_rel_path
from mortis.vault.obsidian import parse as parse_obsidian


class VaultReadAgent(ToolAgent):
    """读 vault 文件,可选解析 Obsidian 双链 + 生成摘要。

    安全: blocked_prefixes 阻止 Mortis 人格层读取受限目录 (issue #38)。
    默认阻止 mortis-steiner/ — Mortis 不应知道 watcher/unease 的存在。
    """

    # 阻止 Mortis 人格层通过 ToolAgent 读的目录前缀 (issue #38)
    BLOCKED_PREFIXES: tuple[str, ...] = ("mortis-steiner/",)

    def __init__(
        self,
        vault: Vault,
        agent_id: str = "vault:read",
        blocked_prefixes: tuple[str, ...] | None = None,
        provider: LLMProviderProtocol | None = None,
    ) -> None:
        self.vault = vault
        self.agent_id = agent_id
        self._blocked = blocked_prefixes if blocked_prefixes is not None else self.BLOCKED_PREFIXES
        self.provider = provider

    def execute(self, input: dict) -> ToolResult:
        rel_path = input.get("rel_path")
        if not isinstance(rel_path, str) or not rel_path:
            return ToolResult(
                success=False, data=None, error="missing or invalid 'rel_path'"
            )

        # 安全检查: blocked prefix (issue #38)
        # 用栈式归一化消除路径中段的 ..,避免 LLM 构造
        # `mortis-journal/../mortis-steiner/x.md` 绕过白名单 (issue #67 audit Critical-A)。
        rel_path_norm = normalize_rel_path(rel_path)
        for prefix in self._blocked:
            if rel_path_norm.startswith(prefix):
                return ToolResult(
                    success=False, data=None,
                    error=f"access denied: '{rel_path}' matches blocked prefix '{prefix}'",
                )

        resolve_links = bool(input.get("resolve_links", False))
        summarize = bool(input.get("summarize", False))
        summary_length = int(input.get("summary_length", 100))
        if summary_length < 20:
            summary_length = 100

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

        # 生成摘要 (issue #63)
        if summarize and self.provider:
            data["summary"] = self._summarize(entry.content, summary_length)
        else:
            data["summary"] = None

        return ToolResult(success=True, data=data, error=None)

    def _summarize(self, content: str, max_length: int) -> str | None:
        """通过 LLM 生成内容摘要 (issue #63)。

        Args:
            content: 要摘要的文本内容。
            max_length: 摘要最大长度(字符数)。

        Returns:
            摘要文本,或 None (无 provider 或失败)。
        """
        if not self.provider or not content:
            return None

        system_prompt = """你是一个文本摘要助手。请将以下文本浓缩成指定长度的摘要。

要求:
1. 保持原意不变
2. 提取关键信息
3. 语言流畅自然
4. 不超过指定长度
"""

        user_prompt = f"""文本内容:
{content[:2000]}

请生成不超过 {max_length} 字的摘要。"""

        try:
            summary = self.provider.generate_text(user_prompt, system=system_prompt)
            if summary:
                # 截断到指定长度
                return summary[:max_length]
            return None
        except Exception:  # noqa: BLE001
            return None


__all__ = ["VaultReadAgent"]

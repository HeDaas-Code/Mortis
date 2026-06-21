"""Mortis tools vault — vault 读写工具。

issue #6 落地：白名单强制检查下沉到 Vault 层后，这里只透传 whitelist 参数。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .base import ToolProtocol, ToolResult
from mortis.vault import Vault, VaultAccessDenied


@dataclass
class VaultReadTool:
    """vault:read — 读 vault 内文件。"""
    vault: Vault
    name: str = "vault:read"
    description: str = "读取 vault 内的文件内容。参数: path（相对 vault 根的路径）。"
    input_schema: dict = field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "相对 vault 根的路径，如 mortis-journal/notes/today.md",
            },
        },
        "required": ["path"],
    })

    def execute(self, path: str, whitelist: tuple[str, ...] | None = None) -> ToolResult:
        try:
            entry = self.vault.read(path, whitelist=whitelist)
            return ToolResult.ok(self.name, entry.content)
        except VaultAccessDenied as e:
            return ToolResult.err(self.name, str(e))
        except FileNotFoundError:
            return ToolResult.err(self.name, f"file not found in vault: {path!r}")
        except Exception as e:
            return ToolResult.err(self.name, str(e))


@dataclass
class VaultListTool:
    """vault:list — 列举 vault 内文件。"""
    vault: Vault
    name: str = "vault:list"
    description: str = "列举 vault 内某目录下所有文件路径。参数: dir（相对 vault 根的目录，默认根）。"
    input_schema: dict = field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "dir": {
                "type": "string",
                "description": "相对 vault 根的目录（默认空=根）",
                "default": "",
            },
        },
    })

    def execute(self, dir: str = "", whitelist: tuple[str, ...] | None = None) -> ToolResult:
        try:
            entries = self.vault.list_entries(dir, whitelist=whitelist)
            if not entries:
                return ToolResult.ok(self.name, "(no files)")
            return ToolResult.ok(self.name, "\n".join(entries))
        except Exception as e:
            return ToolResult.err(self.name, str(e))


@dataclass
class VaultWriteTool:
    """vault:write — 写 vault 内文件（需审核标记）。"""
    vault: Vault
    name: str = "vault:write"
    description: str = (
        "将内容写入 vault 内的文件。参数: path（相对 vault 根的路径）, content（文件内容）。"
        "注意：此工具写入的文件会标记为 sub 产出，待主人格审阅后才正式入 vault。"
    )
    input_schema: dict = field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "相对 vault 根的路径",
            },
            "content": {
                "type": "string",
                "description": "文件内容",
            },
        },
        "required": ["path", "content"],
    })

    def execute(
        self,
        path: str,
        content: str,
        sub_id: str | None = None,
        whitelist: tuple[str, ...] | None = None,
    ) -> ToolResult:
        try:
            # sub 写文件走 sub-output 路径（待审阅）
            if sub_id:
                # sub-output 路径本身在白名单内（mortis-journal/sub-outputs/），
                # 不需要再次强制检查（check_whitelist 内部实现保证）。
                rel = self.vault.write_sub_output(sub_id, content)
            else:
                self.vault.write(path, content, whitelist=whitelist)
                rel = path
            return ToolResult.ok(self.name, f"written to {rel}")
        except VaultAccessDenied as e:
            return ToolResult.err(self.name, str(e))
        except Exception as e:
            return ToolResult.err(self.name, str(e))


@dataclass
class VaultExistsTool:
    """vault:exists — 检查文件是否存在。"""
    vault: Vault
    name: str = "vault:exists"
    description: str = "检查 vault 内文件是否存在。参数: path（相对 vault 根的路径）。"
    input_schema: dict = field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "相对 vault 根的路径"},
        },
        "required": ["path"],
    })

    def execute(self, path: str, whitelist: tuple[str, ...] | None = None) -> ToolResult:
        return ToolResult.ok(self.name, "yes" if self.vault.exists(path, whitelist=whitelist) else "no")

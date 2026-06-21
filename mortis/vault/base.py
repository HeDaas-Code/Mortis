"""Mortis vault base — vault 抽象协议。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from mortis.seed.schema import SEVEN_DIMENSIONS


@dataclass(frozen=True)
class VaultEntry:
    """vault 单条记录。"""
    path: str  # 相对 vault 根的路径
    content: str
    modified_at: str  # ISO8601


class VaultProtocol(Protocol):
    """vault 抽象协议。任何实现此接口的类都能作为 Mortis 的 vault。"""

    def read(self, rel_path: str) -> VaultEntry:
        """读 vault 内一个文件。"""
        ...

    def write(self, rel_path: str, content: str) -> VaultEntry:
        """写一个文件到 vault。"""
        ...

    def exists(self, rel_path: str) -> bool:
        """检查文件是否存在。"""
        ...

    def list_entries(self, rel_dir: str = "") -> list[str]:
        """列 vault 内某目录的所有文件路径（相对 vault 根）。"""
        ...

    def write_sub_output(self, sub_id: str, content: str) -> str:
        """sub 完成任务后，产出存到 mortis-journal/sub-outputs/<sub_id>.md。

        Returns:
            相对 vault 根的路径。
        """
        ...

    def list_pending_sub_outputs(self) -> list[str]:
        """列出所有待主人审阅的 sub 产出。"""
        ...

    def approve_sub_output(self, rel_path: str, target_rel: str | None = None) -> str:
        """主人审阅通过 sub 产出。

        Args:
            rel_path: 相对 vault 根的 sub 产出路径。
            target_rel: 合并到的目标路径。None = 保留在 journal。

        Returns:
            最终落地路径（相对 vault 根）。
        """
        ...

    def discard_sub_output(self, rel_path: str) -> None:
        """主人拒绝 sub 产出。"""
        ...


class VaultSecurity:
    """vault 安全层 — 白名单检查、权限边界。"""

    @staticmethod
    def check_whitelist(rel_path: str, whitelist: tuple[str, ...]) -> bool:
        """检查路径是否在白名单内。"""
        for pattern in whitelist:
            if pattern.endswith("/"):
                if rel_path.startswith(pattern) or rel_path + "/" in pattern:
                    continue
            if rel_path == pattern or rel_path.startswith(pattern):
                return True
        return False

    @staticmethod
    def deny_reason(rel_path: str, whitelist: tuple[str, ...]) -> str:
        return (
            f"access denied: {rel_path!r} not in vault whitelist "
            f"({', '.join(whitelist)})"
        )
"""Mortis vault 本地目录实现。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from mortis.growth.frontmatter import FrontmatterError, parse_growth_file
from mortis.growth.model import Dimension, Growth
from mortis.growth.vault_layout import (
    DIMENSION_DIRS,
    GROWTH_DIR,
    GROWTH_WHITELIST,
    growth_rel,
)
from mortis.growth.writer import (
    write_growth_obsidian,
    extract_wikilinks_from_body,
    extract_tags_inline_from_body,
)
from mortis.vault.obsidian import parse as parse_obsidian

from .base import VaultEntry, VaultProtocol, VaultSecurity


class VaultAccessDenied(Exception):
    """vault 访问被白名单拒绝。"""


@dataclass
class Vault:
    """本地目录实现的 vault。

    vault 目录布局:
        vault/
            mortis-seed.md      (种子 — 主人格的来源)
            mortis-journal/     (主人格日志 + sub 产出待审稿)
                sub-outputs/    (sub 完成任务后的产出,待主人审阅)
                notes/          (主人格正式笔记)
    """

    root: Path

    def __post_init__(self) -> None:
        self.root = Path(self.root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "mortis-journal" / "sub-outputs").mkdir(parents=True, exist_ok=True)
        (self.root / "mortis-journal" / "notes").mkdir(parents=True, exist_ok=True)

    def _safe_path(self, rel_path: str) -> Path:
        """归一化路径并确保在 vault 根内。

        防御：
        - 拒绝绝对路径
        - resolve 后检查是否在 root 内（消除 ../ 遍历）
        """
        if rel_path.startswith("/"):
            raise VaultAccessDenied(f"absolute path not allowed: {rel_path}")
        target = (self.root / rel_path).resolve()
        try:
            target.relative_to(self.root)
        except ValueError:
            raise VaultAccessDenied(
                f"path traversal detected: {rel_path!r} escapes vault root"
            )
        return target

    def _enforce(self, rel_path: str, whitelist: tuple[str, ...] | None, op: str) -> None:
        """白名单强制检查（issue #6 落地）。

        不传 whitelist 时不强制（保持向后兼容）。
        传 whitelist 时调 VaultSecurity.check_whitelist，失败抛 VaultAccessDenied。
        """
        if whitelist is None:
            return
        if not VaultSecurity.check_whitelist(rel_path, whitelist):
            raise VaultAccessDenied(VaultSecurity.deny_reason(rel_path, whitelist))

    def read(self, rel_path: str, whitelist: tuple[str, ...] | None = None) -> VaultEntry:
        """读 vault 内一个文件。

        Args:
            rel_path: 相对 vault 根的路径。
            whitelist: 可选白名单。传了则强制检查，不通过抛 VaultAccessDenied。
        """
        self._enforce(rel_path, whitelist, "read")
        p = self._safe_path(rel_path)
        if not p.exists():
            raise FileNotFoundError(f"vault entry not found: {rel_path}")
        stat = p.stat()
        return VaultEntry(
            path=rel_path,
            content=p.read_text(encoding="utf-8"),
            modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        )

    def write(
        self,
        rel_path: str,
        content: str,
        whitelist: tuple[str, ...] | None = None,
    ) -> VaultEntry:
        """写一个文件到 vault。

        Args:
            rel_path: 相对 vault 根的路径。
            content: 文件内容。
            whitelist: 可选白名单。传了则强制检查，不通过抛 VaultAccessDenied。
        """
        self._enforce(rel_path, whitelist, "write")
        p = self._safe_path(rel_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        stat = p.stat()
        return VaultEntry(
            path=rel_path,
            content=content,
            modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        )

    def exists(self, rel_path: str, whitelist: tuple[str, ...] | None = None) -> bool:
        """检查文件是否存在（不抛错，仅返回 bool）。

        白名单不通过时返回 False（不抛异常 — exists 是探测型 API）。
        """
        if whitelist is not None and not VaultSecurity.check_whitelist(rel_path, whitelist):
            return False
        try:
            p = self._safe_path(rel_path)
        except VaultAccessDenied:
            return False
        return p.exists()

    def list_entries(
        self,
        rel_dir: str = "",
        whitelist: tuple[str, ...] | None = None,
    ) -> list[str]:
        """列 vault 内某目录的所有文件路径（相对 vault 根）。

        Args:
            rel_dir: 相对 vault 根的目录（默认根）。
            whitelist: 可选白名单。传了则只返回白名单内的路径。
        """
        p = self._safe_path(rel_dir)
        if not p.exists():
            return []
        all_entries = sorted(
            str(f.relative_to(self.root))
            for f in p.rglob("*")
            if f.is_file()
        )
        if whitelist is None:
            return all_entries
        return [
            e for e in all_entries
            if VaultSecurity.check_whitelist(e, whitelist)
        ]

    def write_sub_output(self, sub_id: str, content: str) -> str:
        """sub 完成任务后，产出存到 mortis-journal/sub-outputs/<sub_id>.md。"""
        rel = f"mortis-journal/sub-outputs/{sub_id}.md"
        header = (
            f"<!-- sub-output: {sub_id} -->\n"
            f"<!-- created_at: {datetime.now(tz=timezone.utc).isoformat()} -->\n"
            f"<!-- status: pending_review -->\n\n"
        )
        self.write(rel, header + content)
        return rel

    def list_pending_sub_outputs(self) -> list[str]:
        """列出所有待主人审阅的 sub 产出。"""
        return sorted(self.list_entries("mortis-journal/sub-outputs"))

    def approve_sub_output(self, rel_path: str, target_rel: str | None = None) -> str:
        """主人审阅通过 sub 产出。"""
        entry = self.read(rel_path)
        body_lines = [
            line for line in entry.content.splitlines()
            if not line.lstrip().startswith("<!--")
        ]
        body = "\n".join(body_lines).strip()
        if target_rel is None:
            sub_id = Path(rel_path).stem
            target_rel = f"mortis-journal/notes/{sub_id}.md"
        self.write(target_rel, body)
        old_lines = entry.content.splitlines()
        new_lines = [
            line.replace("pending_review", "approved") if "pending_review" in line else line
            for line in old_lines
        ]
        self.write(rel_path, "\n".join(new_lines))
        return target_rel

    def discard_sub_output(self, rel_path: str) -> None:
        """主人拒绝 sub 产出 — 删除文件。"""
        p = self._safe_path(rel_path)
        if p.exists():
            p.unlink()

    # ----- growth CRUD (issue #18 Phase 2) -----

    def _ensure_growth_layout(self) -> None:
        """首次写入前 lazy 创建 mortis-growth/<dimension>/ 子目录。

        __post_init__ 只建 journal 目录 — growth 是后期子系统（#18 决定），
        不抢 vault 初始化时序。空目录占位允许 list_entries() 在零文件时也能 rglob。
        """
        for dim_dir in DIMENSION_DIRS.values():
            (self.root / GROWTH_DIR / dim_dir).mkdir(parents=True, exist_ok=True)

    def write_growth(self, growth: Growth) -> None:
        """把 Growth dataclass 写为 md 文件。

        路径由 vault_layout.growth_rel() 决定 — mortis-growth/<dim>/<id>.md。
        **issue #19 行为变更**：使用 `write_growth_obsidian` 序列化为完整
        Obsidian-Native 格式（H1 标题 / `## 来源` / `> [!note]` callout /
        `%%潜意识%%` 段）。Obsidian-Native 字段（callout / subconscious）由
        writer 根据 Growth 字段值自动生成对应段。
        复用 self.write(..., whitelist=GROWTH_WHITELIST) — 不重写安全检查。
        同 ID 重复写 → 覆盖（self.write 用 p.write_text 语义）。
        首次调用时 lazy 建子目录。
        """
        self._ensure_growth_layout()
        rel = growth_rel(growth.dimension, growth.id)
        content = write_growth_obsidian(growth)
        self.write(rel, content, whitelist=GROWTH_WHITELIST)

    def read_growth(self, rel_path: str) -> Growth:
        """读 vault 内的 growth md 文件 → Growth dataclass。

        文件不存在 → FileNotFoundError（透传 self.read 的行为）。
        frontmatter 解析失败 → FrontmatterError（透传 parse_growth_file 的行为）。

        **issue #19 行为变更**：反序列化后会用 Obsidian 解析层扫描 vault
        原始文本（剥离前的完整 md），提取 wikilinks / tags_inline / callout /
        subconscious 四个新字段并用 `dataclasses.replace` 回填到 Growth 实例。
        旧字段（frontmatter 中没有的）保持空值 — round-trip 仍一致。
        """
        entry = self.read(rel_path, whitelist=GROWTH_WHITELIST)
        growth = parse_growth_file(entry.content)
        return _enrich_growth_with_obsidian(growth, raw_text=entry.content)

    def list_growths(self, dimension: Dimension | None = None) -> list[str]:
        """列 mortis-growth/ 下所有 .md 相对路径。

        Args:
            dimension: 可选过滤。传了只返回该维度子目录的 .md。
        """
        if dimension is not None:
            subdir = f"{GROWTH_DIR}/{DIMENSION_DIRS[dimension]}"
            return sorted(
                e for e in self.list_entries(subdir, whitelist=GROWTH_WHITELIST)
                if e.endswith(".md")
            )
        return sorted(
            e for e in self.list_entries(GROWTH_DIR, whitelist=GROWTH_WHITELIST)
            if e.endswith(".md")
        )

    def list_growths_by_tag(self, tag: str) -> list[str]:
        """列 frontmatter.tags 包含指定 tag 的 growth 文件。

        用 self.read_growth 解析每篇 — 简单可靠，避免单独维护反向索引。
        解析失败的文件跳过（不影响主流程）。
        """
        results: list[str] = []
        for rel in self.list_growths():
            try:
                g = self.read_growth(rel)
            except (FileNotFoundError, FrontmatterError):
                continue
            if tag in g.tags:
                results.append(rel)
        return sorted(results)

    def list_growths_min_confidence(self, min_conf: float) -> list[str]:
        """列 confidence >= min_conf 的 growth 文件。

        边界：>=（不是 >）— 写测试断言此行为。
        解析失败的文件跳过。
        """
        results: list[str] = []
        for rel in self.list_growths():
            try:
                g = self.read_growth(rel)
            except (FileNotFoundError, FrontmatterError):
                continue
            if g.confidence >= min_conf:
                results.append(rel)
        return sorted(results)

    def archive_growth(self, dimension: "Dimension", growth_id: str) -> bool:
        """原子地把 growth 从 active 移到 archive/ (issue #39)。

        用 rename(2) — 原子操作, 避免 copy + unlink 中间失败导致
        同一 growth 同时存在于 active 和 archive。

        Returns:
            True 如果原文件存在且成功移动; False 如果原文件不存在。
        """
        from mortis.growth.vault_layout import growth_archive_rel, growth_rel

        orig_rel = growth_rel(dimension, growth_id)
        archive_rel = growth_archive_rel(dimension, growth_id)
        orig_path = self._safe_path(orig_rel)
        if not orig_path.exists():
            return False
        archive_path = self._safe_path(archive_rel)
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        orig_path.rename(archive_path)
        return True


# ----- growth × Obsidian 集成辅助（issue #19）-----


def _enrich_growth_with_obsidian(growth: Growth, raw_text: str) -> Growth:
    """用 Obsidian 解析层扫描 vault 原始文本，提取 4 个新字段并 dataclasses.replace 回填。

    行为：
    - wikilinks: raw_text 中 `[[双链]]` 的 target 列表（去重保序）
    - tags_inline: raw_text 中 `#tag` 列表（去重保序）
    - callout: raw_text 中**第一个** callout 块的内容(去掉 `> [!kind]` 前缀)。
                None 表示无 callout。
    - subconscious: raw_text 中 `%%...%%` 注释 + 折叠块的内容（用 `\n\n` 连接）。
                    None 表示无注释。
    - body: **不修改** — body 字段已由 `parse_growth_file` 经过 Obsidian
             剥离后回填（保留用户原始纯文本）。调用方按需从 `subconscious`
             字段拿剥离后的内容。
    """
    parsed = parse_obsidian(raw_text)
    wikilinks = extract_wikilinks_from_body(raw_text)
    tags_inline = extract_tags_inline_from_body(raw_text)
    callout: str | None = None
    if parsed.callouts:
        callout = parsed.callouts[0].body
    subconscious: str | None = None
    subconscious_parts: list[str] = list(parsed.comments)
    for fold in parsed.foldable_sections:
        subconscious_parts.append(fold.body)
    if subconscious_parts:
        subconscious = "\n\n".join(subconscious_parts)
    return replace(
        growth,
        wikilinks=wikilinks,
        tags_inline=tags_inline,
        callout=callout,
        subconscious=subconscious,
    )
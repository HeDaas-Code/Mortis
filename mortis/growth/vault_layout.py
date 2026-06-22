"""Mortis growth vault layout — 长期记忆目录结构常量。

issue #18: 一次性定义 vault 里 growth / subconscious 的物理布局。
空目录在第一次写入时由 vault.write_growth() lazy 创建（不抢 __init__）。
"""

from __future__ import annotations

from .model import Dimension

# 白名单：写入必须走这个。vault.write_growth() 内部透传给 self.write(..., whitelist=GROWTH_WHITELIST)
# 复用 mortis.vault.VaultSecurity.check_whitelist + _safe_path，不重写安全检查。
GROWTH_WHITELIST: tuple[str, ...] = ("mortis-growth/",)

# 长期记忆根目录（RFC-001 §六）
GROWTH_DIR = "mortis-growth"

# 反思/梦境工作记忆根目录（RFC-001 §六，#21-#23 写）
SUBCONSCIOUS_DIR = "mortis-subconscious"

# 7 维度子目录名 — 复用 Dimension enum 值，不重写字符串
DIMENSION_DIRS: dict[Dimension, str] = {
    Dimension.IDENTITY: "identity",
    Dimension.VALUES: "values",
    Dimension.TONE: "tone",
    Dimension.AGENCY: "agency",
    Dimension.RELATIONS: "relations",
    Dimension.CREATIVITY: "creativity",
    Dimension.MORTALITY: "mortality",
}

# 长期记忆内子目录：侵蚀归档（#23 ERODE phase）
GROWTH_ARCHIVE_DIR = "archive"

# 潜意识子目录：#21-#23 各占一个
SUBCONSCIOUS_SUBDIRS: tuple[str, ...] = (
    "pending-reflections",  # #21 REFLECT 写
    "associations",         # #22 DREAM-LIGHT 写
    "conflicts",            # #23 DREAM-MEDIUM 写（RECONCILE phase）
)


def growth_rel(dimension: Dimension, growth_id: str, ext: str = ".md") -> str:
    """生成 growth 文件相对路径：mortis-growth/<dimension>/<id><ext>。"""
    return f"{GROWTH_DIR}/{DIMENSION_DIRS[dimension]}/{growth_id}{ext}"


def list_dimension_dirs() -> tuple[str, ...]:
    """返回所有 7 维度子目录名（保持 SEVEN_DIMENSIONS 顺序）。"""
    return tuple(DIMENSION_DIRS[d] for d in Dimension)

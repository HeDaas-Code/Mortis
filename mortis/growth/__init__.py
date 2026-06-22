"""Mortis growth — 长期记忆子系统（人格生长）。

issue #18: Phase 1 — 数据模型 + vault 结构扩展 + 读写 API。
issue #19: Phase 2 — Obsidian-Native 格式（解析层 + writer + 反向回填）。
不实现写入逻辑（reflect/dream/owner edit 是 #21-#24 的事）。
"""

from __future__ import annotations

from .model import Dimension, DreamLevel, Growth, assert_dimension_consistency
from .vault_layout import (
    DIMENSION_DIRS,
    GROWTH_ARCHIVE_DIR,
    GROWTH_DIR,
    GROWTH_WHITELIST,
    SUBCONSCIOUS_DIR,
    SUBCONSCIOUS_SUBDIRS,
    growth_rel,
    list_dimension_dirs,
)
from .frontmatter import (
    FrontmatterError,
    parse_frontmatter,
    parse_growth_file,
    serialize_frontmatter,
    serialize_growth_file,
)
from .writer import (
    write_growth_obsidian,
    extract_wikilinks_from_body,
    extract_tags_inline_from_body,
)

__all__ = [
    # model
    "Dimension",
    "DreamLevel",
    "Growth",
    "assert_dimension_consistency",
    # vault layout
    "DIMENSION_DIRS",
    "GROWTH_ARCHIVE_DIR",
    "GROWTH_DIR",
    "GROWTH_WHITELIST",
    "SUBCONSCIOUS_DIR",
    "SUBCONSCIOUS_SUBDIRS",
    "growth_rel",
    "list_dimension_dirs",
    # frontmatter
    "FrontmatterError",
    "parse_frontmatter",
    "parse_growth_file",
    "serialize_frontmatter",
    "serialize_growth_file",
    # writer (issue #19)
    "write_growth_obsidian",
    "extract_wikilinks_from_body",
    "extract_tags_inline_from_body",
]

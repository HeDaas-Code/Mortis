"""Mortis vault — 认知存储层。"""

from __future__ import annotations

from .base import VaultEntry, VaultProtocol, VaultSecurity
from .local import Vault, VaultAccessDenied
from .obsidian import (
    Callout,
    Fold,
    ParsedObsidian,
    Wikilink,
    parse,
    render_callout,
    render_embed,
    render_subconscious,
    render_wikilink,
)
from .review import ReviewDecision, ReviewGate, ReviewResult

__all__ = [
    "Vault",
    "VaultAccessDenied",
    "VaultEntry",
    "VaultProtocol",
    "VaultSecurity",
    "ReviewDecision",
    "ReviewGate",
    "ReviewResult",
    # Obsidian 解析层 (issue #19)
    "Callout",
    "Fold",
    "ParsedObsidian",
    "Wikilink",
    "parse",
    "render_callout",
    "render_embed",
    "render_subconscious",
    "render_wikilink",
]
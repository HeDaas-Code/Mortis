"""Mortis seed writer — 把 Seed 序列化回 markdown。"""

from __future__ import annotations

from pathlib import Path

from .loader import Seed
from .schema import SEVEN_DIMENSIONS


def save_seed(seed: Seed, path: str | Path) -> None:
    """把 Seed 序列化成 markdown 写回 seed.md。"""
    p = Path(path)
    lines = ["# Mortis seed — 主人格种子", ""]
    for d in SEVEN_DIMENSIONS:
        title = d.capitalize()
        body = getattr(seed, d).strip()
        lines.append(f"## {title}")
        lines.append("")
        lines.append(body)
        lines.append("")
    p.write_text("\n".join(lines), encoding="utf-8")

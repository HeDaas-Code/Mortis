"""Mortis seed — 主人格种子（七维度 schema + loader + writer）。"""

from __future__ import annotations

from .loader import Seed, load_seed
from .schema import SEVEN_DIMENSIONS
from .writer import save_seed

__all__ = [
    "Seed",
    "SEVEN_DIMENSIONS",
    "load_seed",
    "save_seed",
]

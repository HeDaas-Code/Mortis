"""Mortis seed loader — 从 markdown 文件加载七维度人格种子。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .schema import SEVEN_DIMENSIONS

_HEADING_TO_DIM: dict[str, str] = {d.lower(): d for d in SEVEN_DIMENSIONS}


@dataclass(frozen=True)
class Seed:
    """Mortis 主人格种子。七维度任一缺失 = 种子不完整。"""

    identity: str
    values: str
    tone: str
    agency: str
    relations: str
    creativity: str
    mortality: str

    def get_dimension(self, name: str) -> str:
        """按维度名取值。未知 key -> KeyError（契约：七维度只有这 7 个）。"""
        if name not in SEVEN_DIMENSIONS:
            raise KeyError(f"unknown dimension: {name!r}")
        return getattr(self, name)

    def to_dict(self) -> dict[str, str]:
        return {d: getattr(self, d) for d in SEVEN_DIMENSIONS}

    def summary(self) -> str:
        """给 sub 用的紧凑摘要 — 维度名 + 段落首行。"""
        lines = []
        for d in SEVEN_DIMENSIONS:
            text = getattr(self, d).strip().splitlines()
            first = text[0] if text else ""
            lines.append(f"- {d}: {first}")
        return "\n".join(lines)

    def is_complete(self) -> bool:
        """种子完整性检查 — 七维度任一为空字符串 = 不完整。"""
        return all(getattr(self, d).strip() for d in SEVEN_DIMENSIONS)

    def missing_dimensions(self) -> list[str]:
        return [d for d in SEVEN_DIMENSIONS if not getattr(self, d).strip()]


def _parse_markdown(text: str) -> dict[str, str]:
    """从 `## <Name>\\n<text>\\n## <Name2>...` 形式解析七维度。

    未声明的维度 = 空字符串（由 Seed 构造时校验完整性）。
    """
    found: dict[str, list[str]] = {d: [] for d in SEVEN_DIMENSIONS}
    current: str | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("## "):
            heading = line[3:].strip()
            dim = _HEADING_TO_DIM.get(heading.lower())
            current = dim
        elif current is not None:
            found[current].append(raw)
    return {d: "\n".join(lines).strip() for d, lines in found.items()}


def load_seed(path: str | Path) -> Seed:
    """从 seed.md 加载主人格种子。

    Raises:
        FileNotFoundError: 文件不存在
        ValueError: 七维度任一缺失（种子不完整）
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"seed file not found: {p}")
    text = p.read_text(encoding="utf-8")
    parsed = _parse_markdown(text)
    seed = Seed(**parsed)
    if not seed.is_complete():
        missing = seed.missing_dimensions()
        raise ValueError(f"seed incomplete, missing dimensions: {missing}")
    return seed

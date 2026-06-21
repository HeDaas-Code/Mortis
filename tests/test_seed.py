"""Test seed loader — 七维度人格系统契约。"""
from __future__ import annotations

from pathlib import Path

import pytest

from mortis.seed import (
    SEVEN_DIMENSIONS,
    Seed,
    load_seed,
    save_seed,
)
from mortis.seed.loader import _parse_markdown


# ----- 契约测试 -----

def test_seven_dimensions_constant() -> None:
    """七维度按 Q8 grill-me 拍板的顺序硬编码。"""
    assert SEVEN_DIMENSIONS == (
        "identity", "values", "tone", "agency",
        "relations", "creativity", "mortality",
    )


def test_seed_has_all_seven_attrs() -> None:
    """Seed dataclass 必须暴露全部 7 个字段。"""
    seed = Seed(
        identity="i", values="v", tone="t", agency="a",
        relations="r", creativity="c", mortality="m",
    )
    for dim in SEVEN_DIMENSIONS:
        assert hasattr(seed, dim)


def test_seed_get_dimension_valid() -> None:
    """get_dimension 返回 7 个维度之一的值。"""
    seed = Seed(
        identity="id-x", values="v", tone="t", agency="a",
        relations="r", creativity="c", mortality="m",
    )
    assert seed.get_dimension("identity") == "id-x"
    assert seed.get_dimension("mortality") == "m"


def test_seed_get_dimension_invalid_key() -> None:
    """未注册的 key 抛 KeyError(契约:只能 7 个维度)。"""
    seed = Seed(
        identity="i", values="v", tone="t", agency="a",
        relations="r", creativity="c", mortality="m",
    )
    with pytest.raises(KeyError):
        seed.get_dimension("death")  # wrong key
    with pytest.raises(KeyError):
        seed.get_dimension("mortality_marker")  # not in schema


def test_seed_is_complete_when_all_filled() -> None:
    seed = Seed(
        identity="i", values="v", tone="t", agency="a",
        relations="r", creativity="c", mortality="m",
    )
    assert seed.is_complete()
    assert seed.missing_dimensions() == []


def test_seed_is_incomplete_when_any_blank() -> None:
    seed = Seed(
        identity="", values="v", tone="t", agency="a",
        relations="r", creativity="c", mortality="m",
    )
    assert not seed.is_complete()
    assert seed.missing_dimensions() == ["identity"]


def test_seed_to_dict_has_seven_keys() -> None:
    seed = Seed(
        identity="i", values="v", tone="t", agency="a",
        relations="r", creativity="c", mortality="m",
    )
    d = seed.to_dict()
    assert set(d.keys()) == set(SEVEN_DIMENSIONS)
    assert d["identity"] == "i"


def test_seed_summary_first_line() -> None:
    seed = Seed(
        identity="line1\nline2", values="v", tone="t", agency="a",
        relations="r", creativity="c", mortality="m",
    )
    summary = seed.summary()
    assert "- identity: line1" in summary
    assert "- mortality: m" in summary


# ----- Markdown 解析 -----

def test_parse_markdown_seven_headings() -> None:
    md = (
        "# Title\n"
        "## Identity\nid body\n"
        "## Values\nv body\n"
        "## Tone\nt body\n"
        "## Agency\na body\n"
        "## Relations\nr body\n"
        "## Creativity\nc body\n"
        "## Mortality\nm body\n"
    )
    parsed = _parse_markdown(md)
    assert parsed["identity"] == "id body"
    assert parsed["values"] == "v body"
    assert parsed["mortality"] == "m body"


def test_parse_markdown_case_insensitive() -> None:
    md = "## IDENTITY\nx\n## mortality\ny\n"
    parsed = _parse_markdown(md)
    assert parsed["identity"] == "x"
    assert parsed["mortality"] == "y"


def test_parse_markdown_skips_unknown_headings() -> None:
    md = "## Junk\nignored\n## Identity\nreal\n"
    parsed = _parse_markdown(md)
    assert parsed["identity"] == "real"
    assert parsed["values"] == ""


def test_parse_markdown_multiline_body() -> None:
    md = (
        "## Mortality\n"
        "session ends = gone.\n"
        "vault remains = returns.\n"
        "fact, not drama.\n"
    )
    parsed = _parse_markdown(md)
    assert "session ends = gone." in parsed["mortality"]
    assert "fact, not drama." in parsed["mortality"]


# ----- 文件 I/O -----

def test_load_seed_roundtrip(tmp_path: Path) -> None:
    """load_seed + save_seed 必须能往返。"""
    p = tmp_path / "seed.md"
    original = Seed(
        identity="id", values="v", tone="t", agency="a",
        relations="r", creativity="c", mortality="m",
    )
    save_seed(original, p)
    loaded = load_seed(p)
    assert loaded == original


def test_load_seed_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_seed(tmp_path / "nope.md")


def test_load_seed_incomplete_raises(tmp_path: Path) -> None:
    """七维度缺一 = ValueError。"""
    p = tmp_path / "seed.md"
    p.write_text("## Identity\nx\n", encoding="utf-8")  # 缺 6 个
    with pytest.raises(ValueError, match="seed incomplete"):
        load_seed(p)


def test_load_seed_full_real_file(tmp_path: Path) -> None:
    """完整 7 维度 → load 成功。"""
    p = tmp_path / "seed.md"
    p.write_text(
        "## Identity\ni\n## Values\nv\n## Tone\nt\n## Agency\na\n"
        "## Relations\nr\n## Creativity\nc\n## Mortality\nm\n",
        encoding="utf-8",
    )
    seed = load_seed(p)
    assert seed.is_complete()


# ----- 人格化版本的硬约束 -----

def test_seed_text_must_be_person_like_not_tool_like() -> None:
    """人格化 seed 不能含工具化自我描述(防回滚硬约束)。"""
    md = Path(__file__).parent.parent / "seed.md"
    if not md.exists():
        pytest.skip("seed.md not found")
    text = md.read_text(encoding="utf-8")
    # 这些是 v0 工具化版本里出现过的关键词 — 人格化版本必须不含
    forbidden = [
        "CLI 入口",
        "Schema loader",
        "三层模板链骨架",
        "owner 拍板我执行，owner 没说我等",  # 工具化 agency
        "我不写讨好式的话——",
        "我都不会写",
    ]
    for word in forbidden:
        assert word not in text, f"seed.md still contains tool-like phrase: {word!r}"


def test_seed_must_have_all_seven_headings() -> None:
    """人格化 seed 必须七维度齐全(契约)。"""
    md = Path(__file__).parent.parent / "seed.md"
    if not md.exists():
        pytest.skip("seed.md not found")
    text = md.read_text(encoding="utf-8")
    for dim in SEVEN_DIMENSIONS:
        assert f"## {dim.capitalize()}" in text, f"missing heading: {dim}"
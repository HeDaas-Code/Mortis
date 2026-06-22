"""Test mortis.clock.logical — LogicalClock + 6 时段。

issue #26: 6 时段判断 + 边界 + next_transition。
"""

from __future__ import annotations

from datetime import datetime

import pytest

from mortis.clock import ConsciousnessState, LogicalClock


# ============================================================
# 6 时段判断 (hour-only 比较)
# ============================================================


def test_07_00_is_awake() -> None:
    """07:00 — AWAKE 时段 (06:00 ≤ h < 22:00)。"""
    clk = LogicalClock()
    assert clk.state(datetime(2026, 6, 22, 7, 0)) is ConsciousnessState.AWAKE


def test_14_00_is_awake() -> None:
    """14:00 — AWAKE 时段中段。"""
    clk = LogicalClock()
    assert clk.state(datetime(2026, 6, 22, 14, 0)) is ConsciousnessState.AWAKE


def test_22_00_is_reflect() -> None:
    """22:00 — REFLECT 起点 (22:00 ≤ h < 23:00)。"""
    clk = LogicalClock()
    assert clk.state(datetime(2026, 6, 22, 22, 0)) is ConsciousnessState.REFLECT


def test_23_30_is_dream_light() -> None:
    """23:30 — DREAM_LIGHT 时段 (23:00 ≤ h < 24:00)。"""
    clk = LogicalClock()
    assert clk.state(datetime(2026, 6, 22, 23, 30)) is ConsciousnessState.DREAM_LIGHT


def test_01_30_is_dream_light() -> None:
    """01:30 — DREAM_LIGHT 跨午夜 (00:00 ≤ h < 02:00)。"""
    clk = LogicalClock()
    assert clk.state(datetime(2026, 6, 22, 1, 30)) is ConsciousnessState.DREAM_LIGHT


def test_03_30_is_dream_deep() -> None:
    """03:30 — DREAM_DEEP (02:00 ≤ h < 04:00)。"""
    clk = LogicalClock()
    assert clk.state(datetime(2026, 6, 22, 3, 30)) is ConsciousnessState.DREAM_DEEP


def test_05_30_is_erode() -> None:
    """05:30 — ERODE (04:00 ≤ h < 06:00)。"""
    clk = LogicalClock()
    assert clk.state(datetime(2026, 6, 22, 5, 30)) is ConsciousnessState.ERODE


# ============================================================
# next_transition 边界
# ============================================================


def test_next_transition_from_10am_is_reflect() -> None:
    """10:00 (AWAKE) → 22:00 REFLECT。"""
    clk = LogicalClock()
    at = datetime(2026, 6, 22, 10, 0)
    target, state = clk.next_transition(at)
    assert state is ConsciousnessState.REFLECT
    assert target.hour == 22
    assert target.minute == 0
    assert target.day == 22


def test_next_transition_from_22_30_is_dream_light() -> None:
    """22:30 (REFLECT) → 23:00 DREAM_LIGHT。"""
    clk = LogicalClock()
    at = datetime(2026, 6, 22, 22, 30)
    target, state = clk.next_transition(at)
    assert state is ConsciousnessState.DREAM_LIGHT
    assert target.hour == 23
    assert target.minute == 0
    assert target.day == 22


def test_next_transition_from_03_30_is_erode() -> None:
    """03:30 (DREAM_DEEP) → 04:00 ERODE。"""
    clk = LogicalClock()
    at = datetime(2026, 6, 22, 3, 30)
    target, state = clk.next_transition(at)
    assert state is ConsciousnessState.ERODE
    assert target.hour == 4
    assert target.minute == 0
    assert target.day == 22
"""owner「晚安」触发 — 执行完整夜间认知周期。

流程:
1. REFLECT: 读当天 sessions → 写反思
2. DREAM_LIGHT: LightDreamer.run() — 整理当天记忆
3. DREAM_DEEP (可选, --deep): DeepDreamer.run() — 深度梦境 + drift 检查
4. ERODE: SteinerController.tick_decay() — 衰减 unease
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from mortis.provider import make_provider
from mortis.seed import load_seed
from mortis.steiner import SteinerController
from mortis.vault import Vault

_logger = logging.getLogger(__name__)


def run_goodnight(
    vault_path: str = "vault",
    provider_kind: str = "auto",
    seed_path: str = "seed.md",
    deep: bool = False,
) -> dict:
    """执行「晚安」认知周期。

    Args:
        vault_path: vault 目录路径
        provider_kind: provider 类型
        seed_path: seed 文件路径
        deep: 是否执行深度梦境

    Returns:
        dict with keys: reflect_ok, dream_light_ok, dream_deep_ok (if deep), erode_ok
    """
    vault = Vault(vault_path)
    provider = make_provider(provider_kind)
    seed = load_seed(seed_path)
    steiner = SteinerController(vault)

    results = {}

    # Phase 1: REFLECT
    results["reflect_ok"] = _do_reflect(vault, provider)

    # Phase 2: DREAM_LIGHT
    results["dream_light_ok"] = _do_dream_light(vault, provider)

    # Phase 3: DREAM_DEEP (optional)
    if deep:
        results["dream_deep_ok"] = _do_dream_deep(vault, provider, seed)

    # Phase 4: ERODE
    results["erode_ok"] = _do_erode(steiner)

    return results


def _do_reflect(vault: Vault, provider) -> bool:
    """执行反思。"""
    try:
        from mortis.reflect import ReflectExecutor
        executor = ReflectExecutor(vault, provider, mortis_name="Mortis")
        sessions_dir = vault.root / "mortis-journal" / "sessions"
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        today_dir = sessions_dir / today
        if not today_dir.exists():
            _logger.info("goodnight: no sessions for %s, skipping reflect", today)
            return True  # 无 session 不算失败
        session_paths = [f.name for f in today_dir.glob("*.json")]
        if not session_paths:
            _logger.info("goodnight: no session files in %s, skipping reflect", today)
            return True
        executor.run(session_paths, sessions_dir=today_dir)
        _logger.info("goodnight: reflect done (%d sessions)", len(session_paths))
        return True
    except Exception as e:
        _logger.error("goodnight: reflect failed: %s", e)
        return False


def _do_dream_light(vault: Vault, provider) -> bool:
    """执行 Light Dream。"""
    try:
        from mortis.dream import LightDreamer
        dreamer = LightDreamer(vault, provider)
        result = dreamer.run()
        _logger.info("goodnight: dream_light ok=%s, phases=%d", result.ok, len(result.traces))
        return result.ok
    except Exception as e:
        _logger.error("goodnight: dream_light failed: %s", e)
        return False


def _do_dream_deep(vault: Vault, provider, seed) -> bool:
    """执行 Deep Dream。"""
    try:
        from mortis.dream.deep import DeepDreamer
        dreamer = DeepDreamer(vault, provider, seed)
        result = dreamer.run()
        _logger.info("goodnight: dream_deep ok=%s, phases=%d", result.ok, len(result.traces))
        return result.ok
    except Exception as e:
        _logger.error("goodnight: dream_deep failed: %s", e)
        return False


def _do_erode(steiner: SteinerController) -> bool:
    """执行 unease decay。"""
    try:
        steiner.tick_decay()
        _logger.info("goodnight: erode (decay) done")
        return True
    except Exception as e:
        _logger.error("goodnight: erode failed: %s", e)
        return False

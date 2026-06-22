"""Mortis runtime — 运行时层。"""

from __future__ import annotations

from .context import RuntimeContext
from .master import MasterRuntime, MORTIS_NAME
from .sub import (
    SubRuntime, SubTemplate, L0SubTemplate, L2SubInstance,
    SUB_HARD_CONSTRAINTS, SUB_VAULT_WHITELIST,
)
from .growth_search import growth_system_prompt, search_growths

__all__ = [
    "RuntimeContext",
    "MasterRuntime",
    "MORTIS_NAME",
    "SubRuntime",
    "SubTemplate",
    "L0SubTemplate",
    "L2SubInstance",
    "SUB_HARD_CONSTRAINTS",
    "SUB_VAULT_WHITELIST",
    # issue #20
    "growth_system_prompt",
    "search_growths",
]

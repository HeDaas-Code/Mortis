"""Mortis — 基于 vault 生长出来的自研智能体框架。

Mortis 是一个人格化的任务执行框架:
- vault = 认知系统（不是数据库）
- seed = 不可变人格（OOC 防御）
- pipeline = 多步骤编排（Think / Plan / Act / Review）
- sub = 主人格派的临时执行体（隔离工作区 + 白名单授权）
"""

from __future__ import annotations

from mortis.seed import Seed, load_seed, SEVEN_DIMENSIONS
from mortis.vault import Vault, VaultEntry, VaultProtocol, VaultSecurity, ReviewDecision, ReviewGate
from mortis.provider import (
    LLMProviderProtocol,
    Message,
    ToolCall,
    ToolResult,
    MockProvider,
    MinimaxProvider,
    make_provider,
)
from mortis.memory import Session, Thread, StepRecord, MemoryArchive, ArchiveEntry
from mortis.runtime import (
    MasterRuntime,
    SubRuntime,
    SubTemplate,
    L0SubTemplate,
    L2SubInstance,
    RuntimeContext,
    SUB_HARD_CONSTRAINTS,
    SUB_VAULT_WHITELIST,
)
from mortis.tools import (
    ToolProtocol,
    ToolResult,
    ToolRegistry,
    make_default_registry,
    VaultReadTool,
    VaultListTool,
    VaultWriteTool,
    VaultExistsTool,
)
from mortis.growth import Dimension, Growth


# ----- growth CRUD 顶层包装（issue #18 Phase 2）-----
# Vault.write_growth / read_growth / list_growths 等是实例方法。
# 顶层包装让外部代码不必每次都 `vault.write_growth(g)`，可 `mortis.write_growth(vault, g)`。
# 也方便 sub API / 工具调用层统一入口。

def write_growth(vault: Vault, growth: Growth) -> None:
    """把 Growth 写为 mortis-growth/<dim>/<id>.md。"""
    vault.write_growth(growth)


def read_growth(vault: Vault, rel_path: str) -> Growth:
    """读 vault 内的 growth md → Growth dataclass。"""
    return vault.read_growth(rel_path)


def list_growths(
    vault: Vault, dimension: Dimension | None = None
) -> list[str]:
    """列 mortis-growth/ 下所有 .md 相对路径。可选按 dimension 过滤。"""
    return vault.list_growths(dimension=dimension)


def list_growths_by_tag(vault: Vault, tag: str) -> list[str]:
    """列 frontmatter.tags 包含指定 tag 的 growth 文件。"""
    return vault.list_growths_by_tag(tag)


def list_growths_min_confidence(vault: Vault, min_conf: float) -> list[str]:
    """列 confidence >= min_conf 的 growth 文件（边界包含）。"""
    return vault.list_growths_min_confidence(min_conf)
from mortis.pipeline import (
    PipelineExecutor,
    PipelineResult,
    TaskRouter,
    RouteDecision,
    ThinkStep,
    PlanStep,
    ActStep,
    ReviewStep,
    StepOutput,
    parse_tool_calls_from_text,
)
from mortis.cli import main as cli_main

__version__ = "0.2.0"
__all__ = [
    # 入口
    "cli_main",
    # seed
    "Seed",
    "load_seed",
    "SEVEN_DIMENSIONS",
    # vault
    "Vault",
    "VaultEntry",
    "VaultProtocol",
    "VaultSecurity",
    "ReviewDecision",
    "ReviewGate",
    # growth CRUD (issue #18 Phase 2 — methods on Vault)
    "write_growth",
    "read_growth",
    "list_growths",
    "list_growths_by_tag",
    "list_growths_min_confidence",
    # provider
    "LLMProviderProtocol",
    "Message",
    "ToolCall",
    "ToolResult",
    "MockProvider",
    "MinimaxProvider",
    "make_provider",
    # memory
    "Session",
    "Thread",
    "StepRecord",
    "MemoryArchive",
    "ArchiveEntry",
    # runtime
    "MasterRuntime",
    "SubRuntime",
    "SubTemplate",
    "L0SubTemplate",
    "L2SubInstance",
    "RuntimeContext",
    "SUB_HARD_CONSTRAINTS",
    "SUB_VAULT_WHITELIST",
    # tools
    "ToolProtocol",
    "ToolResult",
    "ToolRegistry",
    "make_default_registry",
    "VaultReadTool",
    "VaultListTool",
    "VaultWriteTool",
    "VaultExistsTool",
    # pipeline
    "PipelineExecutor",
    "PipelineResult",
    "TaskRouter",
    "RouteDecision",
    "ThinkStep",
    "PlanStep",
    "ActStep",
    "ReviewStep",
    "StepOutput",
    "parse_tool_calls_from_text",
]

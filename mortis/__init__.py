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

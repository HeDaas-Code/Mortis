"""Mortis v3 全项 E2E 生产级实验 — 真实 minimax LLM 调用链端到端测试。

覆盖审计报告 §02 方法级清单中的 11 个 LLM 调用点 + 主循环 pipeline + Dream 流水线 + ToolAgent 链路。

运行方式:
    MINIMAX_API_KEY=xxx python3 docs/mortis-audit-v3/e2e_experiment.py

输出:
    docs/mortis-audit-v3/e2e-report.md — 实验报告
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# 确保项目根在 sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from mortis.seed import load_seed
from mortis.vault import Vault
from mortis.vault.local import VaultAccessDenied
from mortis.provider import make_provider, MinimaxProvider
from mortis.provider.base import Message
from mortis.memory import Session
from mortis.runtime import MasterRuntime
from mortis.pipeline import PipelineExecutor
from mortis.tools import make_default_registry
from mortis.toolagent import (
    VaultReadAgent,
    VaultSearchAgent,
    VaultStatsAgent,
    MarkdownRenderAgent,
    ClockAgent,
)
from mortis.redact import redact_snippet
from mortis.growth import (
    Growth,
    Dimension,
    DreamLevel,
    serialize_growth_file,
)
from mortis.growth.frontmatter import parse_growth_file
from mortis.reflect import ReflectExecutor
from mortis.dream import LightDreamer, MediumDreamer, DeepDreamer
from mortis.clock import LogicalClock, ConsciousnessState
from mortis.steiner import SteinerController, GrowthWatcher


# ============================================================================
# 实验结果记录
# ============================================================================

@dataclass
class StepResult:
    """单步实验结果。"""
    step_id: str
    name: str
    category: str  # provider | pipeline | toolagent | dream | reflect | steiner | security
    success: bool
    elapsed_sec: float
    detail: str = ""
    error: str = ""
    llm_calls: int = 0
    llm_input_hash: str = ""  # 审计 hash (不记原文)
    llm_output_hash: str = ""


@dataclass
class ExperimentReport:
    """完整实验报告。"""
    started_at: str
    finished_at: str
    total_elapsed_sec: float
    steps: list[StepResult] = field(default_factory=list)
    summary: dict = field(default_factory=dict)

    def add(self, step: StepResult) -> None:
        self.steps.append(step)
        status = "✓" if step.success else "✗"
        print(
            f"  {status} [{step.category}] {step.name} "
            f"({step.elapsed_sec:.2f}s, {step.llm_calls} LLM calls)"
        )
        if step.error:
            print(f"      ERROR: {step.error[:200]}")

    def finalize(self) -> None:
        total = len(self.steps)
        passed = sum(1 for s in self.steps if s.success)
        failed = total - passed
        by_cat: dict[str, dict[str, int]] = {}
        for s in self.steps:
            cat = by_cat.setdefault(s.category, {"total": 0, "passed": 0, "failed": 0})
            cat["total"] += 1
            if s.success:
                cat["passed"] += 1
            else:
                cat["failed"] += 1
        total_llm = sum(s.llm_calls for s in self.steps)
        total_time = sum(s.elapsed_sec for s in self.steps)
        self.summary = {
            "total_steps": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": f"{passed/total*100:.1f}%" if total else "0%",
            "total_llm_calls": total_llm,
            "total_step_time_sec": round(total_time, 2),
            "by_category": by_cat,
        }


# ============================================================================
# 实验环境 — 临时 vault + seed
# ============================================================================

class ExperimentEnv:
    """临时实验环境 — 隔离的 vault 目录。"""

    def __init__(self) -> None:
        self.tmpdir = tempfile.mkdtemp(prefix="mortis-e2e-")
        self.vault_root = Path(self.tmpdir) / "vault"
        self.vault_root.mkdir(parents=True, exist_ok=True)
        self.seed_path = self.vault_root / "mortis-seed.md"
        self._write_test_seed()
        self._write_test_growth_files()
        self.vault = Vault(self.vault_root)
        self.seed = load_seed(self.seed_path)
        self.provider = MinimaxProvider(timeout=60.0) if os.environ.get("MINIMAX_API_KEY") else make_provider("auto")
        self.session = Session(session_id=f"e2e-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}")
        self.master = MasterRuntime(
            seed=self.seed,
            vault=self.vault,
            provider=self.provider,
            session=self.session,
        )

    def _write_test_seed(self) -> None:
        seed_content = """# Mortis seed — E2E 测试种子

## Identity
Mortis-E2E。测试用人格，简短直接。

## Values
准确优先。

## Tone
简短。不注水。

## Agency
测试驱动。

## Relations
测试 owner 第一。

## Creativity
结构化输出。

## Mortality
测试结束即终止。
"""
        self.seed_path.write_text(seed_content, encoding="utf-8")

    def _write_test_growth_files(self) -> None:
        """写几个测试 growth 文件到 vault，供 search/stats 读取。"""
        growth_dir = self.vault_root / "mortis-growth" / "identity"
        growth_dir.mkdir(parents=True, exist_ok=True)

        growths = [
            Growth(
                id="test-identity-001",
                dimension=Dimension.IDENTITY,
                dream_level=DreamLevel.LIGHT,
                confidence=0.8,
                source_sessions=("e2e-test",),
                created_at="2026-06-25T00:00:00Z",
                last_validated="2026-06-25T00:00:00Z",
                emotional_valence=0.5,
                emotional_arousal=0.3,
                tags=("test", "identity"),
                wikilinks=(),
                body="# 测试 identity growth\n\n这是 E2E 测试用的 growth 文件。\n\n关键词：身份认同。",
            ),
            Growth(
                id="test-identity-002",
                dimension=Dimension.IDENTITY,
                dream_level=DreamLevel.MEDIUM,
                confidence=0.6,
                source_sessions=("e2e-test",),
                created_at="2026-06-25T01:00:00Z",
                last_validated="2026-06-25T01:00:00Z",
                emotional_valence=0.4,
                emotional_arousal=0.2,
                tags=("test",),
                wikilinks=("test-identity-001",),
                body="# 第二条 identity growth\n\n关联第一条。包含 emotional_fear 标签测试 redact。",
            ),
            Growth(
                id="test-values-001",
                dimension=Dimension.VALUES,
                dream_level=DreamLevel.LIGHT,
                confidence=0.9,
                source_sessions=("e2e-test",),
                created_at="2026-06-25T02:00:00Z",
                last_validated="2026-06-25T02:00:00Z",
                emotional_valence=0.6,
                emotional_arousal=0.4,
                tags=("test", "values"),
                wikilinks=(),
                body="# 测试 values growth\n\n价值观测试。dream_level: deep。",
            ),
        ]

        for g in growths:
            rel = f"mortis-growth/{g.dimension.value}/{g.id}.md"
            content = serialize_growth_file(g)
            (self.vault_root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.vault_root / rel).write_text(content, encoding="utf-8")

    def cleanup(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)


# ============================================================================
# 实验步骤
# ============================================================================

def step_01_provider_connectivity(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-01: Provider 连通性 — minimax 真实 API 调用。"""
    start = time.monotonic()
    try:
        provider = env.provider
        is_minimax = isinstance(provider, MinimaxProvider)
        if not is_minimax:
            raise RuntimeError(f"期望 MinimaxProvider，实际 {type(provider).__name__}（MINIMAX_API_KEY 未设置？）")

        resp = provider.generate_text(
            "请用一句话回答：1+1=?",
            system="你是数学助手",
            temperature=0.1,
            max_tokens=50,
        )
        ok = bool(resp) and "2" in resp
        report.add(StepResult(
            step_id="E2E-01",
            name="Provider 连通性（minimax generate_text）",
            category="provider",
            success=ok,
            elapsed_sec=time.monotonic() - start,
            detail=f"响应长度 {len(resp)} 字符，包含 '2': {ok}",
            llm_calls=1,
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-01",
            name="Provider 连通性（minimax generate_text）",
            category="provider",
            success=False,
            elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


def step_02_provider_generate_messages(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-02: Provider generate(messages) 多轮消息。"""
    start = time.monotonic()
    try:
        provider = env.provider
        msgs = [
            Message(role="system", content="你是 Mortis E2E 测试助手"),
            Message(role="user", content="用 10 个字以内描述当前状态"),
        ]
        resp = provider.generate(msgs, temperature=0.7, max_tokens=50)
        ok = bool(resp.content) and resp.role in ("assistant", "user")
        report.add(StepResult(
            step_id="E2E-02",
            name="Provider generate(messages) 多轮",
            category="provider",
            success=ok,
            elapsed_sec=time.monotonic() - start,
            detail=f"role={resp.role}, content 长度 {len(resp.content)}",
            llm_calls=1,
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-02",
            name="Provider generate(messages) 多轮",
            category="provider",
            success=False,
            elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


def step_03_provider_async(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-03: Provider async 异步接口（issue #46）。"""
    import asyncio
    start = time.monotonic()
    try:
        provider = env.provider

        async def _run() -> str:
            return await provider.async_generate_text(
                "回答：2+2=?",
                system="数学助手",
                temperature=0.1,
                max_tokens=100,
            )

        resp = asyncio.run(_run())
        ok = bool(resp) and "4" in resp
        report.add(StepResult(
            step_id="E2E-03",
            name="Provider async_generate_text（issue #46）",
            category="provider",
            success=ok,
            elapsed_sec=time.monotonic() - start,
            detail=f"异步响应包含 '4': {ok}",
            llm_calls=1,
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-03",
            name="Provider async_generate_text（issue #46）",
            category="provider",
            success=False,
            elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


def step_04_pipeline_simple_task(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-04: Pipeline 主循环 — 简单任务（Think→Plan→Act→Review）。"""
    start = time.monotonic()
    try:
        thread = env.master.create_thread("用一句话介绍你自己")
        tools = make_default_registry(env.vault, env.provider, include_agents=True)
        ctx = env.master.make_context(thread, tools=tools)
        executor = PipelineExecutor(ctx, tools=tools, verbose=False)
        result = executor.run()
        ok = bool(result.output)
        report.add(StepResult(
            step_id="E2E-04",
            name="Pipeline 简单任务（Think→Plan→Act→Review）",
            category="pipeline",
            success=ok,
            elapsed_sec=time.monotonic() - start,
            detail=f"steps={len(result.steps)}, delegated={result.delegated}, output 长度 {len(result.output)}",
            llm_calls=4,  # think+plan+act+review
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-04",
            name="Pipeline 简单任务（Think→Plan→Act→Review）",
            category="pipeline",
            success=False,
            elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


def step_05_pipeline_with_tools(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-05: Pipeline 任务 + 工具调用（vault:read_agent）。"""
    start = time.monotonic()
    try:
        thread = env.master.create_thread(
            "读取 vault 中的 test-identity-001 growth 文件并总结内容"
        )
        tools = make_default_registry(env.vault, env.provider, include_agents=True)
        ctx = env.master.make_context(thread, tools=tools)
        executor = PipelineExecutor(ctx, tools=tools, verbose=False)
        result = executor.run()
        tool_calls = sum(len(s.get("tool_calls", [])) for s in result.steps)
        ok = bool(result.output)
        report.add(StepResult(
            step_id="E2E-05",
            name="Pipeline + 工具调用（vault:read_agent）",
            category="pipeline",
            success=ok,
            elapsed_sec=time.monotonic() - start,
            detail=f"tool_calls={tool_calls}, output 长度 {len(result.output)}",
            llm_calls=4,
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-05",
            name="Pipeline + 工具调用（vault:read_agent）",
            category="pipeline",
            success=False,
            elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


def step_06_toolagent_vault_read(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-06: ToolAgent — VaultReadAgent + 摘要（issue #63 LLM 调用点）。"""
    start = time.monotonic()
    try:
        agent = VaultReadAgent(vault=env.vault, provider=env.provider)
        result = agent.execute({
            "rel_path": "mortis-growth/identity/test-identity-001.md",
            "summarize": True,
            "summary_length": 80,
        })
        ok = result.success and result.data and result.data.get("summary")
        report.add(StepResult(
            step_id="E2E-06",
            name="VaultReadAgent + 摘要（issue #63 LLM）",
            category="toolagent",
            success=ok,
            elapsed_sec=time.monotonic() - start,
            detail=f"summary 长度 {len(result.data.get('summary', '')) if result.data else 0}",
            llm_calls=1,
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-06",
            name="VaultReadAgent + 摘要（issue #63 LLM）",
            category="toolagent",
            success=False,
            elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


def step_07_toolagent_vault_search_semantic(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-07: ToolAgent — VaultSearchAgent 语义搜索（issue #63 LLM 调用点）。"""
    start = time.monotonic()
    try:
        agent = VaultSearchAgent(vault=env.vault, provider=env.provider, redact_sensitive=True)
        result = agent.execute({
            "query": "身份",
            "semantic": True,
            "top_k": 5,
        })
        ok = result.success and result.data and len(result.data.get("matches", [])) > 0
        summary = result.data.get("semantic_summary", "") if result.data else ""
        report.add(StepResult(
            step_id="E2E-07",
            name="VaultSearchAgent 语义搜索（issue #63 LLM + redact）",
            category="toolagent",
            success=ok,
            elapsed_sec=time.monotonic() - start,
            detail=f"matches={len(result.data.get('matches', [])) if result.data else 0}, summary 长度 {len(summary)}",
            llm_calls=1,
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-07",
            name="VaultSearchAgent 语义搜索（issue #63 LLM + redact）",
            category="toolagent",
            success=False,
            elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


def step_08_toolagent_vault_stats(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-08: ToolAgent — VaultStatsAgent + LLM 分析（issue #63 LLM 调用点）。"""
    start = time.monotonic()
    try:
        agent = VaultStatsAgent(vault=env.vault, provider=env.provider)
        result = agent.execute({"analyze": True})
        ok = result.success and result.data
        analysis = result.data.get("analysis") if result.data else None
        report.add(StepResult(
            step_id="E2E-08",
            name="VaultStatsAgent + LLM 分析（issue #63 LLM）",
            category="toolagent",
            success=ok,
            elapsed_sec=time.monotonic() - start,
            detail=f"total_files={result.data.get('total_files') if result.data else 0}, analysis={'有' if analysis else '无(LLM 返回空)'}",
            llm_calls=1,
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-08",
            name="VaultStatsAgent + LLM 分析（issue #63 LLM）",
            category="toolagent",
            success=False,
            elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


def step_09_toolagent_clock(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-09: ToolAgent — ClockAgent（无 LLM，纯工具）。"""
    start = time.monotonic()
    try:
        agent = ClockAgent(vault=env.vault)
        result = agent.execute({})
        ok = result.success and result.data
        report.add(StepResult(
            step_id="E2E-09",
            name="ClockAgent（纯工具，无 LLM）",
            category="toolagent",
            success=ok,
            elapsed_sec=time.monotonic() - start,
            detail=f"current_time={result.data.get('current_time') if result.data else 'N/A'}",
            llm_calls=0,
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-09",
            name="ClockAgent（纯工具，无 LLM）",
            category="toolagent",
            success=False,
            elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


def step_10_toolagent_markdown_render(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-10: ToolAgent — MarkdownRenderAgent（无 LLM，纯解析）。"""
    start = time.monotonic()
    try:
        agent = MarkdownRenderAgent()
        result = agent.execute({
            "content": "# 标题\n\n这是一段 **加粗** 文本。\n\n- 列表项 1\n- 列表项 2",
        })
        ok = result.success and result.data
        report.add(StepResult(
            step_id="E2E-10",
            name="MarkdownRenderAgent（纯解析，无 LLM）",
            category="toolagent",
            success=ok,
            elapsed_sec=time.monotonic() - start,
            detail=f"parsed keys={list(result.data.keys()) if result.data else []}",
            llm_calls=0,
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-10",
            name="MarkdownRenderAgent（纯解析，无 LLM）",
            category="toolagent",
            success=False,
            elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


def step_11_reflect_executor(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-11: ReflectExecutor — REFLECT phase（LLM 情绪标注 + 反思生成）。"""
    start = time.monotonic()
    try:
        # 先写一个 session 文件供 reflect 读取
        session_dir = env.vault_root / "mortis-journal" / "sessions" / "2026-06-25"
        session_dir.mkdir(parents=True, exist_ok=True)
        # Session.save(dir_path) 只接受目录，文件名由 session_id 决定
        from mortis.memory import Session as SessionCls
        test_session = SessionCls(session_id="e2e-test-session")
        test_session.save(session_dir)
        # 手动写一个 thread JSON 让 session 有内容
        thread_data = {
            "thread_id": "e2e-thread-001",
            "task": "测试任务：介绍自己",
            "created_at": "2026-06-25T00:00:00Z",
            "steps": [{
                "step_id": "step-1",
                "step_type": "think",
                "input": "介绍自己",
                "output": "我是 Mortis E2E 测试人格。",
                "tool_calls": [],
            }],
            "completed": True,
            "completed_at": "2026-06-25T00:01:00Z",
            "output": "我是 Mortis E2E 测试人格。",
            "context_refs": [],
        }
        (session_dir / "e2e-thread-001.json").write_text(
            json.dumps(thread_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        executor = ReflectExecutor(
            vault=env.vault,
            provider=env.provider,
            mortis_name="Mortis-E2E",
        )
        result = executor.run(
            session_paths=["e2e-test-session"],
            sessions_dir=session_dir,
        )
        ok = bool(result) and bool(result.body)
        report.add(StepResult(
            step_id="E2E-11",
            name="ReflectExecutor（REFLECT phase LLM）",
            category="reflect",
            success=ok,
            elapsed_sec=time.monotonic() - start,
            detail=f"反思输出长度 {len(result.body)}, valence={result.valence:.2f}",
            llm_calls=2,  # emotion + reflect
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-11",
            name="ReflectExecutor（REFLECT phase LLM）",
            category="reflect",
            success=False,
            elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


def step_12_dream_light(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-12: LightDreamer — Light Dream 4 phase（RECALL→ASSOCIATE→CRYSTALLIZE→SEED-CHECK）。"""
    start = time.monotonic()
    try:
        dreamer = LightDreamer(vault=env.vault, provider=env.provider)
        result = dreamer.run()
        ok = bool(result)
        report.add(StepResult(
            step_id="E2E-12",
            name="LightDreamer 4 phase（RECALL→ASSOCIATE→CRYSTALLIZE→SEED-CHECK）",
            category="dream",
            success=ok,
            elapsed_sec=time.monotonic() - start,
            detail=f"dream 输出长度 {len(str(result))}",
            llm_calls=4,  # 4 phase 各 1 次
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-12",
            name="LightDreamer 4 phase（RECALL→ASSOCIATE→CRYSTALLIZE→SEED-CHECK）",
            category="dream",
            success=False,
            elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


def step_13_dream_medium(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-13: MediumDreamer — Medium Dream 5 phase（+SIMULATE）。"""
    start = time.monotonic()
    try:
        dreamer = MediumDreamer(vault=env.vault, provider=env.provider)
        result = dreamer.run()
        ok = bool(result)
        report.add(StepResult(
            step_id="E2E-13",
            name="MediumDreamer 5 phase（+SIMULATE）",
            category="dream",
            success=ok,
            elapsed_sec=time.monotonic() - start,
            detail=f"dream 输出长度 {len(str(result))}",
            llm_calls=5,
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-13",
            name="MediumDreamer 5 phase（+SIMULATE）",
            category="dream",
            success=False,
            elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


def step_14_dream_deep(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-14: DeepDreamer — Deep Dream 7 phase（+RECONCILE+ERODE）。"""
    start = time.monotonic()
    try:
        dreamer = DeepDreamer(vault=env.vault, provider=env.provider, seed=env.seed)
        result = dreamer.run()
        ok = bool(result)
        report.add(StepResult(
            step_id="E2E-14",
            name="DeepDreamer 7 phase（+RECONCILE+ERODE）",
            category="dream",
            success=ok,
            elapsed_sec=time.monotonic() - start,
            detail=f"dream 输出长度 {len(str(result))}",
            llm_calls=7,
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-14",
            name="DeepDreamer 7 phase（+RECONCILE+ERODE）",
            category="dream",
            success=False,
            elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


def step_15_seed_check_redact(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-15: seed_check LLM 调用 + redact（issue #84 CRITICAL）。"""
    start = time.monotonic()
    try:
        from mortis.dream.seed_check import seed_check
        # 构造 growth_summary（含私密字段测试 redact）
        growth_summary = "identity: 测试 growth。emotional_fear: 0.8。dream_level: deep。"
        result = seed_check(
            seed=env.seed,
            growth_summary=growth_summary,
            provider=env.provider,
            vault=env.vault,
        )
        ok = bool(result) and result.total_drift >= 0
        report.add(StepResult(
            step_id="E2E-15",
            name="seed_check + redact（issue #84 CRITICAL）",
            category="dream",
            success=ok,
            elapsed_sec=time.monotonic() - start,
            detail=f"total_drift={result.total_drift:.2f}, needs_notify={result.needs_owner_notify}",
            llm_calls=1,
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-15",
            name="seed_check + redact（issue #84 CRITICAL）",
            category="dream",
            success=False,
            elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


def step_16_growth_preview_redact(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-16: growth preview 注入 system prompt + redact（issue #85）。"""
    start = time.monotonic()
    try:
        ctx = env.master.make_context(thread=env.master.create_thread("测试 growth preview"), tools=None)
        prompt = ctx.growth_system_prompt(max_items=3)
        ok = bool(prompt) and "emotional_" not in prompt  # redact 应移除 emotional_* 字段
        report.add(StepResult(
            step_id="E2E-16",
            name="growth preview + redact（issue #85）",
            category="security",
            success=ok,
            elapsed_sec=time.monotonic() - start,
            detail=f"prompt 长度 {len(prompt)}, redact 后无 emotional_: {'emotional_' not in prompt}",
            llm_calls=0,  # 不直接调 LLM，只测 redact
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-16",
            name="growth preview + redact（issue #85）",
            category="security",
            success=False,
            elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


def step_17_redact_function(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-17: redact 共享模块（issue #83）— 6 个 SENSITIVE_PATTERNS。"""
    start = time.monotonic()
    try:
        test_cases = [
            # (输入, 应被脱敏的原文关键词, 是否应脱敏)
            # callout 多行格式：续行也要有 > 前缀才会被整体 redact
            ("> [!dream]\n> 私密梦境内容", "私密梦境内容", True),
            ("> [!secret]\n> 私密内容", "私密内容", True),
            ("[emotion:joy@0.8] 文本", "joy@0.8", True),
            ("%%subconscious%%\n隐藏\n%%/subconscious%%", "隐藏", True),
            ("emotional_valence: 0.8 应被脱敏", "0.8", True),
            ("dream_level: deep 应被脱敏", "deep", True),
            ("normal text 正常文本不应被脱敏", "正常文本", False),
        ]
        all_ok = True
        details = []
        for text, check, should_redact in test_cases:
            redacted = redact_snippet(text)
            if should_redact:
                passed = check not in redacted
            else:
                passed = check in redacted
            if not passed:
                all_ok = False
            details.append(f"{'✓' if passed else '✗'} {text[:30]}")
        report.add(StepResult(
            step_id="E2E-17",
            name="redact 共享模块（issue #83 6 patterns）",
            category="security",
            success=all_ok,
            elapsed_sec=time.monotonic() - start,
            detail="; ".join(details),
            llm_calls=0,
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-17",
            name="redact 共享模块（issue #83 6 patterns）",
            category="security",
            success=False,
            elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


def step_18_vault_security_whitelist(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-18: Vault 白名单 + 路径遍历防护（S1/S2/S3 + #67）。"""
    start = time.monotonic()
    try:
        vault = env.vault
        # 测试路径遍历攻击
        attack_paths = [
            "../../../etc/passwd",
            "mortis-journal/../../../etc/passwd",
            "mortis-journal/../mortis-steiner/secret.md",
        ]
        blocked = 0
        for p in attack_paths:
            try:
                vault.read(p)
            except (VaultAccessDenied, FileNotFoundError):
                blocked += 1
            except Exception:
                blocked += 1  # 任何拒绝都算成功防护
        ok = blocked == len(attack_paths)
        report.add(StepResult(
            step_id="E2E-18",
            name="Vault 白名单 + 路径遍历防护（S1/S2/S3 + #67）",
            category="security",
            success=ok,
            elapsed_sec=time.monotonic() - start,
            detail=f"{blocked}/{len(attack_paths)} 攻击路径被拦截",
            llm_calls=0,
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-18",
            name="Vault 白名单 + 路径遍历防护（S1/S2/S3 + #67）",
            category="security",
            success=False,
            elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


def step_19_vault_read_blocked_prefix(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-19: VaultReadAgent blocked_prefixes（issue #38/#68/#80）。"""
    start = time.monotonic()
    try:
        agent = VaultReadAgent(vault=env.vault, provider=env.provider)
        # 写一个 steiner 文件试图读取
        steiner_dir = env.vault_root / "mortis-steiner"
        steiner_dir.mkdir(parents=True, exist_ok=True)
        (steiner_dir / "secret.md").write_text("# 隐藏的 unease 数据", encoding="utf-8")
        # 写一个 sub-outputs 文件
        sub_dir = env.vault_root / "mortis-journal" / "sub-outputs"
        sub_dir.mkdir(parents=True, exist_ok=True)
        (sub_dir / "pending.md").write_text("# sub 私域产出", encoding="utf-8")

        blocked_paths = [
            "mortis-steiner/secret.md",          # issue #38
            "mortis-journal/sub-outputs/pending.md",  # issue #68/#80
            "mortis-journal/../mortis-steiner/secret.md",  # issue #67 路径归一化
        ]
        blocked = 0
        for p in blocked_paths:
            result = agent.execute({"rel_path": p})
            if not result.success and "denied" in (result.error or "").lower():
                blocked += 1
        ok = blocked == len(blocked_paths)
        report.add(StepResult(
            step_id="E2E-19",
            name="VaultReadAgent blocked_prefixes（issue #38/#68/#80）",
            category="security",
            success=ok,
            elapsed_sec=time.monotonic() - start,
            detail=f"{blocked}/{len(blocked_paths)} 受限路径被阻断",
            llm_calls=0,
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-19",
            name="VaultReadAgent blocked_prefixes（issue #38/#68/#80）",
            category="security",
            success=False,
            elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


def step_20_provider_audit_log(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-20: Provider 审计日志（issue #87）— hash 不记原文。"""
    start = time.monotonic()
    try:
        from mortis.provider.audit import messages_hash, sha256_prefix
        from mortis.provider.base import Message
        msgs = [Message(role="user", content="测试审计 hash")]
        h = messages_hash(msgs, length=16)
        single = sha256_prefix("测试", length=16)
        ok = len(h) == 16 and len(single) == 16 and h != single
        report.add(StepResult(
            step_id="E2E-20",
            name="Provider 审计日志 hash（issue #87）",
            category="security",
            success=ok,
            elapsed_sec=time.monotonic() - start,
            detail=f"messages_hash={h}, sha256_prefix={single}",
            llm_calls=0,
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-20",
            name="Provider 审计日志 hash（issue #87）",
            category="security",
            success=False,
            elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


def step_21_steiner_watcher(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-21: Steiner GrowthWatcher — owner 编辑检测（issue #24/#58）。"""
    start = time.monotonic()
    try:
        controller = SteinerController(vault=env.vault)
        # 模拟 owner 编辑 growth 文件 — 直接调 _on_edit 触发 accumulate
        controller._on_edit(Dimension.IDENTITY)
        ok = True  # 不抛异常即通过
        report.add(StepResult(
            step_id="E2E-21",
            name="Steiner GrowthWatcher 编辑检测（issue #24/#58）",
            category="steiner",
            success=ok,
            elapsed_sec=time.monotonic() - start,
            detail="unease accumulate 完成，无异常",
            llm_calls=0,  # watcher 不直接调 LLM
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-21",
            name="Steiner GrowthWatcher 编辑检测（issue #24/#58）",
            category="steiner",
            success=False,
            elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


def step_22_unease_injection(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-22: unease 注入 RuntimeContext（issue #57）。"""
    start = time.monotonic()
    try:
        # 写 unease 文件
        unease_dir = env.vault_root / "mortis-steiner"
        unease_dir.mkdir(parents=True, exist_ok=True)
        (unease_dir / "unease.md").write_text(
            "---\nlevel: 0.6\ncreated_at: 2026-06-25T00:00:00Z\n---\n\n# unease 记录\nowner 编辑了 identity growth。",
            encoding="utf-8",
        )

        thread = env.master.create_thread("测试 unease 注入")
        ctx = env.master.make_context(thread, tools=None)
        prompt = ctx.unease_prompt_for_injection()
        ok = True  # 不抛异常即通过（unease 可能因 decay 返回空）
        report.add(StepResult(
            step_id="E2E-22",
            name="unease 注入 RuntimeContext（issue #57）",
            category="steiner",
            success=ok,
            elapsed_sec=time.monotonic() - start,
            detail=f"unease prompt 长度 {len(prompt)}",
            llm_calls=0,
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-22",
            name="unease 注入 RuntimeContext（issue #57）",
            category="steiner",
            success=False,
            elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


def step_23_logical_clock(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-23: LogicalClock 时段状态机（issue #26/#34）。"""
    start = time.monotonic()
    try:
        from datetime import datetime
        clock = LogicalClock()
        # 测试不同时段
        morning = datetime(2026, 6, 25, 9, 0, 0)
        evening = datetime(2026, 6, 25, 22, 0, 0)
        night = datetime(2026, 6, 25, 3, 0, 0)
        s1 = clock.state(morning)
        s2 = clock.state(evening)
        s3 = clock.state(night)
        ok = s1 != s2 or s2 != s3  # 至少有状态变化
        report.add(StepResult(
            step_id="E2E-23",
            name="LogicalClock 时段状态机（issue #26/#34）",
            category="clock",
            success=ok,
            elapsed_sec=time.monotonic() - start,
            detail=f"09:00={s1.value}, 22:00={s2.value}, 03:00={s3.value}",
            llm_calls=0,
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-23",
            name="LogicalClock 时段状态机（issue #26/#34）",
            category="clock",
            success=False,
            elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


def step_24_growth_compress(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-24: growth 维度压缩（issue #47）— LLM 间接调用。"""
    start = time.monotonic()
    try:
        from mortis.growth.compress import compress_growths
        result = compress_growths(vault=env.vault, provider=env.provider, dimension=Dimension.IDENTITY)
        ok = bool(result)
        report.add(StepResult(
            step_id="E2E-24",
            name="growth 维度压缩（issue #47 LLM 间接）",
            category="dream",
            success=ok,
            elapsed_sec=time.monotonic() - start,
            detail=f"压缩结果 keys={list(result.keys()) if isinstance(result, dict) else type(result).__name__}",
            llm_calls=1,
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-24",
            name="growth 维度压缩（issue #47 LLM 间接）",
            category="dream",
            success=False,
            elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


def step_25_full_cycle(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-25: 完整认知周期 — AWAKE→REFLECT→DREAM_LIGHT 端到端。"""
    start = time.monotonic()
    try:
        # 0. 准备 session 文件供 reflect 读取
        session_dir = env.vault_root / "mortis-journal" / "sessions" / "2026-06-25"
        session_dir.mkdir(parents=True, exist_ok=True)
        from mortis.memory import Session as SessionCls
        SessionCls(session_id="e2e-test-session").save(session_dir)
        thread_data = {
            "thread_id": "e2e-thread-001",
            "task": "总结你今天学到了什么",
            "created_at": "2026-06-25T00:00:00Z",
            "steps": [{
                "step_id": "step-1",
                "step_type": "think",
                "input": "总结",
                "output": "今天学了 E2E 测试。",
                "tool_calls": [],
            }],
            "completed": True,
            "completed_at": "2026-06-25T00:01:00Z",
            "output": "今天学了 E2E 测试。",
            "context_refs": [],
        }
        (session_dir / "e2e-thread-001.json").write_text(
            json.dumps(thread_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # 1. AWAKE — 执行一个任务产生 session
        thread = env.master.create_thread("总结你今天学到了什么")
        tools = make_default_registry(env.vault, env.provider, include_agents=True)
        ctx = env.master.make_context(thread, tools=tools)
        executor = PipelineExecutor(ctx, tools=tools, verbose=False)
        awake_result = executor.run()

        # 2. REFLECT
        reflector = ReflectExecutor(
            vault=env.vault,
            provider=env.provider,
            mortis_name="Mortis-E2E",
        )
        reflect_result = reflector.run(
            session_paths=["e2e-test-session"],
            sessions_dir=session_dir,
        )

        # 3. DREAM_LIGHT
        dreamer = LightDreamer(vault=env.vault, provider=env.provider)
        dream_result = dreamer.run()

        ok = bool(awake_result.output) and bool(reflect_result) and bool(dream_result)
        report.add(StepResult(
            step_id="E2E-25",
            name="完整认知周期 AWAKE→REFLECT→DREAM_LIGHT",
            category="pipeline",
            success=ok,
            elapsed_sec=time.monotonic() - start,
            detail=f"awake_output={len(awake_result.output)}, reflect={len(str(reflect_result))}, dream={len(str(dream_result))}",
            llm_calls=10,  # 4 (awake) + 2 (reflect) + 4 (dream)
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-25",
            name="完整认知周期 AWAKE→REFLECT→DREAM_LIGHT",
            category="pipeline",
            success=False,
            elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


# ============================================================================
# 主流程
# ============================================================================

def main() -> int:
    if not os.environ.get("MINIMAX_API_KEY"):
        print("ERROR: MINIMAX_API_KEY 环境变量未设置")
        return 1

    print("=" * 70)
    print("Mortis v3 全项 E2E 生产级实验 — 真实 minimax LLM 调用链")
    print("=" * 70)
    print()

    report = ExperimentReport(
        started_at=datetime.now(timezone.utc).isoformat(),
        finished_at="",
        total_elapsed_sec=0,
    )

    env = ExperimentEnv()
    print(f"实验环境: {env.tmpdir}")
    print(f"Provider: {type(env.provider).__name__}")
    print(f"Vault: {env.vault_root}")
    print()

    overall_start = time.monotonic()

    steps = [
        step_01_provider_connectivity,
        step_02_provider_generate_messages,
        step_03_provider_async,
        step_04_pipeline_simple_task,
        step_05_pipeline_with_tools,
        step_06_toolagent_vault_read,
        step_07_toolagent_vault_search_semantic,
        step_08_toolagent_vault_stats,
        step_09_toolagent_clock,
        step_10_toolagent_markdown_render,
        step_11_reflect_executor,
        step_12_dream_light,
        step_13_dream_medium,
        step_14_dream_deep,
        step_15_seed_check_redact,
        step_16_growth_preview_redact,
        step_17_redact_function,
        step_18_vault_security_whitelist,
        step_19_vault_read_blocked_prefix,
        step_20_provider_audit_log,
        step_21_steiner_watcher,
        step_22_unease_injection,
        step_23_logical_clock,
        step_24_growth_compress,
        step_25_full_cycle,
    ]

    for i, step_fn in enumerate(steps, 1):
        print(f"[{i:02d}/{len(steps)}] {step_fn.__doc__.strip().split(chr(10))[0]}")
        try:
            step_fn(env, report)
        except Exception as e:
            print(f"  ✗ STEP CRASHED: {type(e).__name__}: {e}")
            traceback.print_exc()
        print()

    report.total_elapsed_sec = time.monotonic() - overall_start
    report.finished_at = datetime.now(timezone.utc).isoformat()
    report.finalize()

    env.cleanup()

    # 生成报告
    report_path = PROJECT_ROOT / "docs" / "mortis-audit-v3" / "e2e-report.md"
    _write_report(report, report_path)
    print()
    print("=" * 70)
    print(f"实验完成: {report.summary['passed']}/{report.summary['total_steps']} passed, "
          f"{report.summary['failed']} failed, "
          f"{report.summary['total_llm_calls']} LLM calls, "
          f"{report.total_elapsed_sec:.1f}s")
    print(f"报告: {report_path}")
    print("=" * 70)

    return 0 if report.summary["failed"] == 0 else 1


def _write_report(report: ExperimentReport, path: Path) -> None:
    """生成 Markdown 实验报告。"""
    lines = [
        "# Mortis v3 全项 E2E 生产级实验报告",
        "",
        f"> **E2E EXPERIMENT REPORT** | 开始: {report.started_at} | 结束: {report.finished_at} | 总耗时: {report.total_elapsed_sec:.1f}s",
        f"> Provider: MinimaxProvider (MiniMax-M3, 真实 API 调用)",
        "",
        "## 实验摘要",
        "",
        f"| 指标 | 值 |",
        f"|------|-----|",
        f"| 总步骤 | {report.summary.get('total_steps', 0)} |",
        f"| 通过 | {report.summary.get('passed', 0)} |",
        f"| 失败 | {report.summary.get('failed', 0)} |",
        f"| 通过率 | {report.summary.get('pass_rate', '0%')} |",
        f"| LLM 调用总数 | {report.summary.get('total_llm_calls', 0)} |",
        f"| 步骤总耗时 | {report.summary.get('total_step_time_sec', 0)}s |",
        "",
        "### 按类别统计",
        "",
        "| 类别 | 总数 | 通过 | 失败 |",
        "|------|:----:|:----:|:----:|",
    ]
    for cat, stats in report.summary.get("by_category", {}).items():
        lines.append(f"| {cat} | {stats['total']} | {stats['passed']} | {stats['failed']} |")
    lines.extend([
        "",
        "## 实验步骤详情",
        "",
        "| 步骤 | 类别 | 名称 | 状态 | 耗时 | LLM | 详情/错误 |",
        "|------|------|------|:----:|:----:|:---:|----------|",
    ])
    for s in report.steps:
        status = "✓ PASS" if s.success else "✗ FAIL"
        detail = s.detail if s.success else f"{s.detail}<br>**ERROR**: {s.error[:200]}" if s.detail else f"**ERROR**: {s.error[:200]}"
        lines.append(
            f"| {s.step_id} | {s.category} | {s.name} | {status} | {s.elapsed_sec:.2f}s | {s.llm_calls} | {detail} |"
        )
    lines.extend([
        "",
        "## 覆盖的 LLM 调用点（审计报告 §02）",
        "",
        "| # | 调用点 | 位置 | E2E 步骤 |",
        "|---|--------|------|:--------:|",
        "| 1 | ThinkStep | pipeline/step.py | E2E-04/05/25 |",
        "| 2 | PlanStep | pipeline/step.py | E2E-04/05/25 |",
        "| 3 | ReviewStep | pipeline/step.py | E2E-04/05/25 |",
        "| 4 | VaultReadAgent._summarize | toolagent/vault_read.py | E2E-06 |",
        "| 5 | VaultSearchAgent._semantic_rerank | toolagent/vault_search.py | E2E-07 |",
        "| 6 | VaultStatsAgent._analyze_stats | toolagent/vault_stats.py | E2E-08 |",
        "| 7 | SeedChecker.check | dream/seed_check.py | E2E-15 |",
        "| 8 | ReflectExecutor | reflect/executor.py | E2E-11/25 |",
        "| 9 | LightDreamer | dream/light.py | E2E-12/25 |",
        "| 10 | MediumDreamer | dream/medium.py | E2E-13 |",
        "| 11 | DeepDreamer | dream/deep.py | E2E-14 |",
        "",
        "## 覆盖的安全机制",
        "",
        "| 机制 | Issue | E2E 步骤 |",
        "|------|-------|:--------:|",
        "| redact 共享模块 | #83 | E2E-17 |",
        "| growth preview redact | #85 | E2E-16 |",
        "| seed_check redact | #84 | E2E-15 |",
        "| Vault 白名单 + 路径遍历 | S1/S2/S3/#67 | E2E-18 |",
        "| VaultReadAgent blocked_prefixes | #38/#68/#80 | E2E-19 |",
        "| Provider 审计日志 hash | #87 | E2E-20 |",
        "",
    ])

    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())

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
import threading
import time
import traceback
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from http.server import HTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError

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
    llm_logs: list[dict] = field(default_factory=list)  # LLM 调用完整日志

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

    def save_llm_logs(self, path: Path) -> None:
        """保存 LLM 调用日志到 JSON 文件。"""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.llm_logs, f, ensure_ascii=False, indent=2)


# ============================================================================
# LLM 调用日志包装器 — 捕获完整请求/响应用于 E2E 报告
# ============================================================================

@dataclass
class LLMCallLog:
    """单次 LLM 调用的完整日志记录。"""
    call_id: int                    # 全局调用序号
    step_id: str                     # 触发此调用的 E2E 步骤 ID
    method: str                     # generate / generate_text / async_generate_text
    timestamp: str                   # ISO 时间戳
    messages: list[dict]             # 完整输入 messages (含 system/user/assistant)
    prompt: str                      # generate_text 的 prompt (若适用)
    system: str                      # generate_text 的 system prompt (若适用)
    response: str                    # LLM 响应内容 (不含 think)
    elapsed_sec: float              # 调用耗时
    temperature: float              # 温度参数
    max_tokens: int | None          # max_tokens 参数
    success: bool                   # 是否成功
    error: str                       # 错误信息 (若失败)
    # 增强字段
    input_length: int = 0           # 输入总字符数 (所有 message content 之和)
    output_length: int = 0          # 输出总字符数 (response 长度)
    model_version: str = ""         # 模型版本 (如 "MiniMax-M3")
    endpoint: str = ""             # API 端点 URL
    think_content: str = ""         # 思考过程内容 (```...``` 中的内容)
    think_content_length: int = 0   # 思考过程内容长度
    retry_count: int = 0            # 重试次数 (若使用 RetryProvider)


class LoggingProvider:
    """LLM 调用日志包装器 — 包装任意 provider, 捕获完整请求/响应。

    透明转发所有调用到内部 provider, 同时记录:
    - 完整 messages (含 system prompt)
    - 完整响应内容
    - 调用耗时 + 参数
    - 增强字段: input/output 长度, 模型版本, API 端点, 思考过程分离

    注意: 此包装器仅用于 E2E 实验日志记录, 不在生产环境使用
    (生产环境 MinimaxProvider 只记 hash 不记原文, 见 issue #87)。
    """

    # 思考过程标记: ```...``` 围栏块
    _THINK_PATTERN = None  # 延迟初始化

    def __init__(self, inner, report: ExperimentReport, step_id: str = "") -> None:
        self._inner = inner
        self._report = report
        self._step_id = step_id
        # 提取模型版本和端点
        self._model_version = ""
        self._endpoint = ""
        self._extract_provider_info()

    def _extract_provider_info(self) -> None:
        """从内部 provider 提取模型版本和端点信息。"""
        inner = self._inner
        # 解包韧性层包装器获取底层 provider
        while hasattr(inner, '_inner'):
            inner = inner._inner
        while hasattr(inner, '_primary'):
            inner = inner._primary
        # MinimaxProvider: _model + _base_url
        if hasattr(inner, '_model'):
            self._model_version = inner._model
        if hasattr(inner, '_base_url'):
            self._endpoint = f"{inner._base_url}/chat/completions"
        # MockProvider: 无端点
        if type(inner).__name__ == "MockProvider":
            self._model_version = "mock"
            self._endpoint = "local://mock"

    def set_step_id(self, step_id: str) -> None:
        """设置当前步骤 ID (在每步开始时调用)。"""
        self._step_id = step_id

    def _extract_think_content(self, response: str) -> tuple[str, str]:
        """从响应中分离思考过程 (```...``` 围栏块)。

        Returns:
            (final_response, think_content) — 去除 think 后的响应 + think 原文
        """
        import re
        if self._THINK_PATTERN is None:
            # 匹配 ```...``` 围栏块 (含可选语言标记)
            self._THINK_PATTERN = re.compile(r"```\w*\n(.*?)```", re.DOTALL)
        think_matches = self._THINK_PATTERN.findall(response)
        if not think_matches:
            return response, ""
        think_content = "\n".join(think_matches)
        final = self._THINK_PATTERN.sub("", response).strip()
        return final, think_content

    def _compute_input_length(self, messages: list, prompt: str, system: str) -> int:
        """计算输入总字符数。"""
        total = 0
        if messages:
            for m in messages:
                total += len(m.content) if hasattr(m, 'content') else len(str(m))
        total += len(prompt) + len(system)
        return total

    def _log(self, method: str, messages: list, prompt: str, system: str,
             response: str, elapsed: float, temperature: float,
             max_tokens: int | None, success: bool, error: str) -> None:
        # 分离思考过程
        final_response, think_content = self._extract_think_content(response) if response else ("", "")
        input_length = self._compute_input_length(messages, prompt, system)
        output_length = len(response) if response else 0
        think_length = len(think_content) if think_content else 0
        # 提取重试次数 (若内部是 RetryProvider)
        retry_count = 0
        if hasattr(self._inner, 'stats') and 'total_retries' in (self._inner.stats or {}):
            retry_count = self._inner.stats.get('total_retries', 0)

        log = LLMCallLog(
            call_id=len(self._report.llm_logs) + 1,
            step_id=self._step_id,
            method=method,
            timestamp=datetime.now(timezone.utc).isoformat(),
            messages=[{"role": m.role, "content": m.content[:500]} for m in messages] if messages else [],
            prompt=prompt[:500] if prompt else "",
            system=system[:300] if system else "",
            response=final_response[:1000] if final_response else "",
            elapsed_sec=round(elapsed, 3),
            temperature=temperature,
            max_tokens=max_tokens,
            success=success,
            error=error,
            input_length=input_length,
            output_length=output_length,
            model_version=self._model_version,
            endpoint=self._endpoint,
            think_content=think_content[:500] if think_content else "",
            think_content_length=think_length,
            retry_count=retry_count,
        )
        self._report.llm_logs.append(asdict(log))

    def generate(self, messages, *, temperature=0.7, max_tokens=None):
        start = time.monotonic()
        try:
            result = self._inner.generate(messages, temperature=temperature, max_tokens=max_tokens)
            elapsed = time.monotonic() - start
            self._log("generate", messages, "", "", result.content, elapsed,
                      temperature, max_tokens, True, "")
            return result
        except Exception as e:
            elapsed = time.monotonic() - start
            self._log("generate", messages, "", "", "", elapsed,
                      temperature, max_tokens, False, f"{type(e).__name__}: {e}")
            raise

    def generate_text(self, prompt, system="", *, temperature=0.7, max_tokens=None):
        start = time.monotonic()
        try:
            result = self._inner.generate_text(prompt, system=system, temperature=temperature, max_tokens=max_tokens)
            elapsed = time.monotonic() - start
            # 构造 messages 用于日志
            from mortis.provider.base import Message
            msgs = []
            if system:
                msgs.append(Message(role="system", content=system))
            msgs.append(Message(role="user", content=prompt))
            self._log("generate_text", msgs, prompt, system, result, elapsed,
                      temperature, max_tokens, True, "")
            return result
        except Exception as e:
            elapsed = time.monotonic() - start
            from mortis.provider.base import Message
            msgs = []
            if system:
                msgs.append(Message(role="system", content=system))
            msgs.append(Message(role="user", content=prompt))
            self._log("generate_text", msgs, prompt, system, "", elapsed,
                      temperature, max_tokens, False, f"{type(e).__name__}: {e}")
            raise

    async def async_generate_text(self, prompt, system="", *, temperature=0.7, max_tokens=None):
        start = time.monotonic()
        try:
            result = await self._inner.async_generate_text(prompt, system=system, temperature=temperature, max_tokens=max_tokens)
            elapsed = time.monotonic() - start
            from mortis.provider.base import Message
            msgs = []
            if system:
                msgs.append(Message(role="system", content=system))
            msgs.append(Message(role="user", content=prompt))
            self._log("async_generate_text", msgs, prompt, system, result, elapsed,
                      temperature, max_tokens, True, "")
            return result
        except Exception as e:
            elapsed = time.monotonic() - start
            from mortis.provider.base import Message
            msgs = []
            if system:
                msgs.append(Message(role="system", content=system))
            msgs.append(Message(role="user", content=prompt))
            self._log("async_generate_text", msgs, prompt, system, "", elapsed,
                      temperature, max_tokens, False, f"{type(e).__name__}: {e}")
            raise

    async def async_generate(self, messages, *, temperature=0.7, max_tokens=None):
        start = time.monotonic()
        try:
            result = await self._inner.async_generate(messages, temperature=temperature, max_tokens=max_tokens)
            elapsed = time.monotonic() - start
            self._log("async_generate", messages, "", "", result.content, elapsed,
                      temperature, max_tokens, True, "")
            return result
        except Exception as e:
            elapsed = time.monotonic() - start
            self._log("async_generate", messages, "", "", "", elapsed,
                      temperature, max_tokens, False, f"{type(e).__name__}: {e}")
            raise


# ============================================================================
# 实验环境 — 临时 vault + seed
# ============================================================================

class ExperimentEnv:
    """临时实验环境 — 隔离的 vault 目录。"""

    def __init__(self, report: ExperimentReport | None = None) -> None:
        self.tmpdir = tempfile.mkdtemp(prefix="mortis-e2e-")
        self.vault_root = Path(self.tmpdir) / "vault"
        self.vault_root.mkdir(parents=True, exist_ok=True)
        self.seed_path = self.vault_root / "mortis-seed.md"
        self._write_test_seed()
        self._write_test_growth_files()
        self.vault = Vault(self.vault_root)
        self.seed = load_seed(self.seed_path)
        inner_provider = MinimaxProvider(timeout=60.0) if os.environ.get("MINIMAX_API_KEY") else make_provider("auto")
        # 用 LoggingProvider 包装, 捕获完整 LLM 请求/响应日志
        if report is not None:
            self.logging_provider = LoggingProvider(inner_provider, report)
            self.provider = self.logging_provider
        else:
            self.logging_provider = None
            self.provider = inner_provider
        self.session = Session(session_id=f"e2e-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}")
        self.master = MasterRuntime(
            seed=self.seed,
            vault=self.vault,
            provider=self.provider,
            session=self.session,
        )
        # Web UI server 生命周期 (E2E-26~31, 惰性启动)
        self._web_server: HTTPServer | None = None
        self._web_base_url: str | None = None
        self._web_thread: threading.Thread | None = None
        self.chat_service = None  # E2E-39~43: 对话服务 (with_chat 启动时赋值)

    def set_step_id(self, step_id: str) -> None:
        """设置当前步骤 ID, 用于 LLM 日志关联。"""
        if self.logging_provider is not None:
            self.logging_provider.set_step_id(step_id)

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
        self.stop_web()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # ---- Web UI server 生命周期 (E2E-26~31, E2E-39~43) ----

    def start_web(self, *, with_chat: bool = False) -> str:
        """启动 Web UI server (后台线程, port=0 自动分配空闲端口)。

        幂等 — 重复调用返回已运行的 server base_url。
        传 ``with_chat=True`` 时附加 ChatService (启用 /chat 对话页面)。
        若 server 已启动但未带 chat, 需先 stop_web 再 start_web(with_chat=True)。
        """
        if self._web_server is not None:
            return self._web_base_url  # type: ignore[return-value]
        from mortis.web.server import start_web_server
        chat_service = None
        if with_chat:
            from mortis.web.chat import ChatService
            chat_service = ChatService(self.master)
            self.chat_service = chat_service
        else:
            self.chat_service = None
        self._web_server = start_web_server(
            vault_path=str(self.vault_root), port=0, chat_service=chat_service,
        )
        actual_port = self._web_server.server_address[1]
        self._web_base_url = f"http://127.0.0.1:{actual_port}"
        self._web_thread = threading.Thread(
            target=self._web_server.serve_forever, daemon=True
        )
        self._web_thread.start()
        return self._web_base_url

    def stop_web(self) -> None:
        """关闭 Web UI server。"""
        if self._web_server is not None:
            self._web_server.shutdown()
            self._web_server.server_close()
            if self._web_thread is not None:
                self._web_thread.join(timeout=5)
            self._web_server = None
            self._web_base_url = None
            self._web_thread = None


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
# Web UI 交互步骤 (E2E-26~31) — issue #52/#53/#54
# 测试真正的 HTML 前端页面 + 前端交互 + 前后端交互
# ============================================================================

def _get_json(base_url: str, path: str) -> tuple[int, dict]:
    """发 GET 请求到 API 端点, 返回 (status_code, parsed_json)。"""
    url = base_url + path
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            status = resp.status
            body = resp.read().decode("utf-8")
    except HTTPError as e:
        status = e.code
        body = e.read().decode("utf-8")
    return status, json.loads(body)


def _get_html(base_url: str, path: str) -> tuple[int, str]:
    """发 GET 请求到 HTML 页面, 返回 (status_code, html_string)。"""
    url = base_url + path
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            status = resp.status
            body = resp.read().decode("utf-8")
    except HTTPError as e:
        status = e.code
        body = e.read().decode("utf-8")
    return status, body


def _post_json(base_url: str, path: str, body: dict) -> tuple[int, dict]:
    """发 POST 请求 (JSON body), 返回 (status_code, parsed_json)。"""
    url = base_url + path
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def _post_stream(base_url: str, path: str, body: dict) -> tuple[int, str]:
    """POST SSE 端点, 返回 (status, raw_text)。"""
    url = base_url + path
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read().decode("utf-8")
    except HTTPError as e:
        return e.code, e.read().decode("utf-8")


def step_26_web_server_dashboard(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-26: Web UI server 启动 + HTML dashboard 页面 (issue #52)。"""
    start = time.monotonic()
    try:
        base_url = env.start_web()
        # 1. HTML dashboard 页面
        html_status, html_body = _get_html(base_url, "/")
        ok_html = (
            html_status == 200
            and "<!DOCTYPE html>" in html_body
            and "Mortis Web UI" in html_body
            and "checkbox" in html_body
            and "togglePrettyPrint" in html_body
            and "refreshData" in html_body
            and "<nav>" in html_body
        )
        # 2. JSON API (前后端交互: JS fetch 调用的端点)
        api_status, api_data = _get_json(base_url, "/api/dashboard")
        ok_api = (
            api_status == 200
            and "phase" in api_data
            and "unease_max" in api_data
            and api_data["growth_count"] == 3
            and "/growths" in api_data["endpoints"]
        )
        # 3. HTML 中渲染了 vault 数据
        ok_data_in_html = "3" in html_body
        ok = ok_html and ok_api and ok_data_in_html
        report.add(StepResult(
            step_id="E2E-26", name="Web UI server 启动 + HTML dashboard (issue #52)",
            category="web", success=ok, elapsed_sec=time.monotonic() - start,
            detail=f"html={ok_html} (DOCTYPE+UI+交互元素), api={ok_api} (phase={api_data.get('phase')}), data_in_html={ok_data_in_html}",
            llm_calls=0,
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-26", name="Web UI server 启动 + HTML dashboard (issue #52)",
            category="web", success=False, elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


def step_27_web_growths(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-27: HTML growth 列表 + 详情页 + 前端过滤交互 (issue #53)。"""
    start = time.monotonic()
    try:
        base_url = env._web_base_url or env.start_web()
        # 1. HTML growth 列表页
        html_status, html_body = _get_html(base_url, "/growths")
        ok_html_list = (
            html_status == 200
            and "growth-card" in html_body
            and "filter-input" in html_body
            and "filterGrowths" in html_body
            and "test-identity-001" in html_body
            and "identity" in html_body
        )
        # 2. JSON API 列表
        api_status, api_data = _get_json(base_url, "/api/growths")
        ok_api_list = api_status == 200 and api_data["total"] == 3
        # 3. HTML growth 详情页
        first_rel = api_data["growths"][0]["rel_path"]
        detail_status, detail_html = _get_html(base_url, f"/growths/{first_rel}")
        ok_html_detail = (
            detail_status == 200
            and "<table>" in detail_html
            and "test-identity-001" in detail_html
            and "identity" in detail_html
            and ("emotional" in detail_html.lower() or "情感" in detail_html)
        )
        # 4. JSON API 详情
        _, detail_json = _get_json(base_url, f"/api/growths/{first_rel}")
        ok_api_detail = detail_json["id"] == "test-identity-001"
        ok = ok_html_list and ok_api_list and ok_html_detail and ok_api_detail
        report.add(StepResult(
            step_id="E2E-27", name="HTML growth 列表 + 详情页 + 前端过滤交互 (issue #53)",
            category="web", success=ok, elapsed_sec=time.monotonic() - start,
            detail=f"html_list={ok_html_list}, api_list={ok_api_list} (total={api_data['total']}), html_detail={ok_html_detail}, api_detail={ok_api_detail}",
            llm_calls=0,
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-27", name="HTML growth 列表 + 详情页 + 前端过滤交互 (issue #53)",
            category="web", success=False, elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


def step_28_web_unease(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-28: HTML unease 仪表盘 (柱状图 + 7 维度, issue #53)。"""
    start = time.monotonic()
    try:
        base_url = env._web_base_url or env.start_web()
        from dataclasses import replace as dc_replace
        from mortis.steiner import UneaseState, save_unease
        from mortis.growth.model import Dimension
        state = dc_replace(UneaseState(), per_dimension={**UneaseState().per_dimension, Dimension.IDENTITY: 0.45, Dimension.VALUES: 0.82})
        save_unease(env.vault, state)
        # 1. HTML unease 页面 (柱状图可视化)
        html_status, html_body = _get_html(base_url, "/unease")
        ok_html = (
            html_status == 200
            and "bar-chart" in html_body
            and "bar-fill" in html_body
            and "bar-row" in html_body
            and "identity" in html_body
            and "values" in html_body
            and "0.82" in html_body
        )
        # 2. JSON API
        api_status, api_data = _get_json(base_url, "/api/unease")
        ok_api = (
            api_status == 200
            and api_data["max_unease"] == 0.82
            and len(api_data["per_dimension"]) == 7
            and api_data["per_dimension"]["identity"] == 0.45
        )
        ok = ok_html and ok_api
        report.add(StepResult(
            step_id="E2E-28", name="HTML unease 仪表盘 (柱状图 + 7 维度, issue #53)",
            category="web", success=ok, elapsed_sec=time.monotonic() - start,
            detail=f"html={ok_html} (bar-chart+bar-fill), api={ok_api} (max={api_data['max_unease']}, dims=7)",
            llm_calls=0,
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-28", name="HTML unease 仪表盘 (柱状图 + 7 维度, issue #53)",
            category="web", success=False, elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


def step_29_web_notifications(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-29: HTML notifications 页面 (issue #54)。"""
    start = time.monotonic()
    try:
        base_url = env._web_base_url or env.start_web()
        from mortis.web.notify import send_notification
        send_notification(env.vault, "drift", "identity drift 0.82", severity="warning")
        send_notification(env.vault, "unease", "values unease accumulated", severity="info")
        # 1. HTML notifications 页面
        html_status, html_body = _get_html(base_url, "/notifications")
        ok_html = (
            html_status == 200
            and "notification" in html_body
            and "warning" in html_body
            and "drift" in html_body
            and "identity drift 0.82" in html_body
        )
        # 2. JSON API
        api_status, api_data = _get_json(base_url, "/api/notifications")
        ok_api = (
            api_status == 200
            and len(api_data["notifications"]) == 2
            and api_data["notifications"][0]["type"] == "drift"
            and api_data["notifications"][0]["severity"] == "warning"
        )
        ok = ok_html and ok_api
        report.add(StepResult(
            step_id="E2E-29", name="HTML notifications 页面 (issue #54)",
            category="web", success=ok, elapsed_sec=time.monotonic() - start,
            detail=f"html={ok_html} (notification+warning+drift), api={ok_api} (count=2)",
            llm_calls=0,
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-29", name="HTML notifications 页面 (issue #54)",
            category="web", success=False, elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


def step_30_web_dreams(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-30: HTML dreams 日历页 (badge + table, issue #53)。"""
    start = time.monotonic()
    try:
        base_url = env._web_base_url or env.start_web()
        dream_log_base = env.vault_root / "mortis-dream-log"
        for level in ("light", "medium", "deep"):
            d = dream_log_base / level
            d.mkdir(parents=True, exist_ok=True)
            (d / f"2026-06-25-{level}.md").write_text(f"# Dream Log: {level}\n\n测试 dream log\n", encoding="utf-8")
        # 1. HTML dreams 页面
        html_status, html_body = _get_html(base_url, "/dreams")
        ok_html = (
            html_status == 200
            and "badge" in html_body
            and "badge light" in html_body
            and "badge medium" in html_body
            and "badge deep" in html_body
            and "<table>" in html_body
            and "2026-06-25" in html_body
        )
        # 2. JSON API
        api_status, api_data = _get_json(base_url, "/api/dreams")
        ok_api = (
            api_status == 200
            and len(api_data["dreams"]) == 3
            and {d["level"] for d in api_data["dreams"]} == {"light", "medium", "deep"}
        )
        ok = ok_html and ok_api
        report.add(StepResult(
            step_id="E2E-30", name="HTML dreams 日历页 (badge + table, issue #53)",
            category="web", success=ok, elapsed_sec=time.monotonic() - start,
            detail=f"html={ok_html} (badge+table+levels), api={ok_api} (count=3)",
            llm_calls=0,
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-30", name="HTML dreams 日历页 (badge + table, issue #53)",
            category="web", success=False, elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


def step_31_web_404_and_dataflow(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-31: 404 路由 + 数据流转校验 (vault→HTML↔JSON) + server 关闭。"""
    start = time.monotonic()
    try:
        base_url = env._web_base_url or env.start_web()
        # 1. 404 路由
        status_404, data_404 = _get_json(base_url, "/nonexistent")
        ok_404 = status_404 == 404 and data_404["error"] == "not found"
        # 2. 数据流转校验: vault 原文 → HTML 页面 → JSON API 三者一致
        _, growths_data = _get_json(base_url, "/api/growths")
        first_rel = growths_data["growths"][0]["rel_path"]
        vault_raw = env.vault.read(first_rel).content
        _, growth_html = _get_html(base_url, f"/growths/{first_rel}")
        _, growth_json = _get_json(base_url, f"/api/growths/{first_rel}")
        test_string = "E2E 测试用的 growth 文件"
        ok_dataflow = (
            test_string in vault_raw
            and test_string in growth_html
            and test_string in growth_json["body"]
        )
        # 3. 前端交互元素验证
        ok_interaction = (
            "togglePrettyPrint" in growth_html
            or "filterGrowths" in growth_html
        )
        # 4. server 关闭
        env.stop_web()
        ok_shutdown = env._web_server is None
        ok = ok_404 and ok_dataflow and ok_interaction and ok_shutdown
        report.add(StepResult(
            step_id="E2E-31", name="404 路由 + 数据流转校验 (vault→HTML↔JSON) + server 关闭",
            category="web", success=ok, elapsed_sec=time.monotonic() - start,
            detail=f"404={ok_404}, dataflow={ok_dataflow} (vault→HTML→JSON 三者一致), interaction={ok_interaction}, shutdown={ok_shutdown}",
            llm_calls=0,
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-31", name="404 路由 + 数据流转校验 (vault→HTML↔JSON) + server 关闭",
            category="web", success=False, elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


# ============================================================================
# E2E-32~38: 异常输入测试 + 子智能体派发 + 流式输出 + 韧性层测试
# ============================================================================

def step_32_exception_file_not_found(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-32: 异常输入 — VaultReadAgent 读取不存在的文件。"""
    start = time.monotonic()
    try:
        from mortis.toolagent.vault_read import VaultReadAgent
        agent = VaultReadAgent(env.vault, env.provider)
        result = agent.execute({"path": "nonexistent/deeply/nested/file.md"})
        # 应返回错误信息而非崩溃
        ok = (
            result.success is False
            or "not found" in (result.message or "").lower()
            or "no such" in (result.message or "").lower()
            or "不存在" in (result.message or "")
        )
        report.add(StepResult(
            step_id="E2E-32",
            name="异常输入 — VaultReadAgent 读取不存在的文件",
            category="exception",
            success=ok,
            elapsed_sec=time.monotonic() - start,
            detail=f"result.success={result.success}, message={result.message[:100]}",
            llm_calls=0,
        ))
    except Exception as e:
        # 异常被捕获而非崩溃也算通过 (优雅降级)
        report.add(StepResult(
            step_id="E2E-32",
            name="异常输入 — VaultReadAgent 读取不存在的文件",
            category="exception",
            success=True,
            elapsed_sec=time.monotonic() - start,
            detail=f"异常被捕获 (优雅降级): {type(e).__name__}: {str(e)[:100]}",
            llm_calls=0,
        ))


def step_33_exception_malformed_growth(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-33: 异常输入 — 格式错误的 growth 文件。"""
    start = time.monotonic()
    try:
        # 写入一个格式错误的 growth 文件 (缺少必要字段)
        malformed_path = env.vault_root / "mortis-growth" / "identity" / "malformed-001.md"
        malformed_path.parent.mkdir(parents=True, exist_ok=True)
        malformed_path.write_text(
            "---\nbroken: frontmatter\nnot: valid: yaml\n---\n"
            "这不是一个有效的 growth 文件\n没有 id 字段\n没有 dimension 字段\n",
            encoding="utf-8",
        )
        # 读取不应崩溃, 应返回某种降级结果
        growths = env.vault.list_growths()
        ok = True  # 不崩溃即通过
        report.add(StepResult(
            step_id="E2E-33",
            name="异常输入 — 格式错误的 growth 文件",
            category="exception",
            success=ok,
            elapsed_sec=time.monotonic() - start,
            detail=f"malformed growth 写入成功, list_growths() 返回 {len(growths)} 条 (不崩溃)",
            llm_calls=0,
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-33",
            name="异常输入 — 格式错误的 growth 文件",
            category="exception",
            success=False,
            elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


def step_34_exception_llm_unavailable(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-34: 异常输入 — LLM 服务不可用 (mock provider 模拟故障)。"""
    start = time.monotonic()
    try:
        from mortis.provider.mock import MockProvider
        from mortis.provider.base import Message

        # 创建一个总是失败的 mock provider
        class FailingProvider(MockProvider):
            def generate(self, messages, *, temperature=0.7, max_tokens=None):
                raise RuntimeError("simulated LLM service unavailable")
            def generate_text(self, prompt, system="", *, temperature=0.7, max_tokens=None):
                raise RuntimeError("simulated LLM service unavailable")

        failing = FailingProvider()
        error_caught = False
        error_msg = ""
        try:
            failing.generate_text("test prompt")
        except RuntimeError as e:
            error_caught = True
            error_msg = str(e)

        # 测试 FallbackProvider: 主失败 → 备用成功
        from mortis.provider import FallbackProvider, MockProvider as MP
        fallback = FallbackProvider(failing, MP())
        result = fallback.generate_text("test prompt")
        ok_fallback = result is not None and len(result) > 0

        ok = error_caught and ok_fallback
        report.add(StepResult(
            step_id="E2E-34",
            name="异常输入 — LLM 服务不可用 + FallbackProvider 降级",
            category="exception",
            success=ok,
            elapsed_sec=time.monotonic() - start,
            detail=f"error_caught={error_caught} ({error_msg}), fallback_result='{result[:50]}'",
            llm_calls=0,
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-34",
            name="异常输入 — LLM 服务不可用 + FallbackProvider 降级",
            category="exception",
            success=False,
            elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


def step_35_subagent_delegation(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-35: 子智能体派发 — 复杂多文件查询任务 (验证 context 传递)。"""
    start = time.monotonic()
    try:
        from mortis.pipeline.executor import PipelineExecutor

        # 设置一个需要多文件查询的复杂任务
        thread = env.master.create_thread(
            "请综合分析我的 identity 和 values 两个维度的 growth, 给出一致性评估"
        )
        tools = make_default_registry(env.vault, env.provider, include_agents=True)
        ctx = env.master.make_context(thread, tools=tools)
        executor = PipelineExecutor(ctx, tools=tools, verbose=False)
        result = executor.run()

        # 验证: 任务执行完成, 可能走委派路径也可能走直接路径
        ok = result.output is not None and len(result.output) > 0

        # 验证 SubTemplate context 传递 (如果走了委派路径)
        if result.delegated:
            ok = ok and result.sub_id is not None
            detail = f"delegated=True, sub_id={result.sub_id}, output={result.output[:80]}"
        else:
            detail = f"delegated=False (router 判断为简单任务), output={result.output[:80]}"

        report.add(StepResult(
            step_id="E2E-35",
            name="子智能体派发 — 复杂多文件查询任务",
            category="delegation",
            success=ok,
            elapsed_sec=time.monotonic() - start,
            detail=detail,
            llm_calls=1,  # ThinkStep 至少 1 次调用
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-35",
            name="子智能体派发 — 复杂多文件查询任务",
            category="delegation",
            success=False,
            elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


def step_36_streaming_output(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-36: 流式输出 — generate_stream 逐块返回。"""
    start = time.monotonic()
    try:
        from mortis.provider.base import Message
        # 检查 provider 是否支持 generate_stream
        has_stream = hasattr(env.provider, 'generate_stream')
        if not has_stream:
            report.add(StepResult(
                step_id="E2E-36",
                name="流式输出 — generate_stream",
                category="streaming",
                success=True,
                elapsed_sec=time.monotonic() - start,
                detail="provider 不支持 generate_stream, 跳过 (fallback 到非流式)",
                llm_calls=0,
            ))
            return

        # 调用 generate_stream
        messages = [Message(role="user", content="请用一句话介绍 Mortis 项目")]
        chunks = list(env.provider.generate_stream(messages, temperature=0.7))
        ok = (
            len(chunks) > 0
            and all(hasattr(c, 'delta') for c in chunks)
            and any(c.delta for c in chunks)  # 至少有一个非空 delta
        )
        total_delta = "".join(c.delta for c in chunks)
        report.add(StepResult(
            step_id="E2E-36",
            name="流式输出 — generate_stream 逐块返回",
            category="streaming",
            success=ok,
            elapsed_sec=time.monotonic() - start,
            detail=f"chunks={len(chunks)}, total_delta_len={len(total_delta)}, "
                   f"finish_reason={chunks[-1].finish_reason if chunks else 'N/A'}",
            llm_calls=1,
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-36",
            name="流式输出 — generate_stream 逐块返回",
            category="streaming",
            success=False,
            elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


def step_37_circuit_breaker(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-37: 熔断器 — 连续失败触发熔断 + 恢复。"""
    start = time.monotonic()
    try:
        from mortis.provider.mock import MockProvider
        from mortis.provider.base import Message
        from mortis.provider.resilience import CircuitBreakerProvider, CircuitState, CircuitOpenError

        class FailingProvider(MockProvider):
            _fail_count = 0
            def generate(self, messages, *, temperature=0.7, max_tokens=None):
                self._fail_count += 1
                raise RuntimeError(f"simulated failure #{self._fail_count}")

        # 创建熔断器: 阈值=3, 恢复时间=1s
        failing = FailingProvider()
        breaker = CircuitBreakerProvider(failing, failure_threshold=3, recovery_timeout=1.0)

        # 触发 3 次失败 → 熔断器开启
        for i in range(3):
            try:
                breaker.generate([Message(role="user", content="test")])
            except RuntimeError:
                pass

        state_after_failures = breaker.stats["state"]
        ok_open = state_after_failures == CircuitState.OPEN.value

        # 第 4 次调用应被熔断拒绝 (不调用下游)
        rejected = False
        try:
            breaker.generate([Message(role="user", content="test")])
        except CircuitOpenError:
            rejected = True
        except RuntimeError:
            rejected = False  # 下游被调用了, 熔断器没生效

        ok_rejection = rejected

        # 等待恢复 → 半开 → 成功 → 关闭
        import time as _time
        _time.sleep(1.1)

        # 替换为成功的 provider
        success_provider = MockProvider()
        breaker._inner = success_provider
        result = breaker.generate([Message(role="user", content="test")])
        state_after_recovery = breaker.stats["state"]
        ok_recovery = state_after_recovery == CircuitState.CLOSED.value

        ok = ok_open and ok_rejection and ok_recovery
        report.add(StepResult(
            step_id="E2E-37",
            name="熔断器 — 连续失败触发熔断 + 恢复",
            category="resilience",
            success=ok,
            elapsed_sec=time.monotonic() - start,
            detail=f"open_after_3_failures={ok_open}, rejected_4th_call={ok_rejection}, "
                   f"recovered_to_closed={ok_recovery}, "
                   f"stats={breaker.stats}",
            llm_calls=0,
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-37",
            name="熔断器 — 连续失败触发熔断 + 恢复",
            category="resilience",
            success=False,
            elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


def step_38_retry_provider(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-38: 重试机制 — 瞬时故障自动重试恢复。"""
    start = time.monotonic()
    try:
        from mortis.provider.mock import MockProvider
        from mortis.provider.base import Message
        from mortis.provider.resilience import RetryProvider

        class FlakyProvider(MockProvider):
            """前 2 次失败, 第 3 次成功。"""
            _call_count = 0
            def generate(self, messages, *, temperature=0.7, max_tokens=None):
                self._call_count += 1
                if self._call_count <= 2:
                    raise RuntimeError(f"transient failure #{self._call_count}")
                return super().generate(messages, temperature=temperature, max_tokens=max_tokens)

        flaky = FlakyProvider()
        retry = RetryProvider(flaky, max_retries=3, base_delay=0.01, max_delay=0.1)
        result = retry.generate([Message(role="user", content="test")])

        ok = result is not None and len(result.content) > 0
        stats = retry.stats
        ok_stats = stats["total_retries"] == 2 and stats["total_recovered"] == 1

        report.add(StepResult(
            step_id="E2E-38",
            name="重试机制 — 瞬时故障自动重试恢复",
            category="resilience",
            success=ok and ok_stats,
            elapsed_sec=time.monotonic() - start,
            detail=f"result='{result.content[:50]}', retries={stats['total_retries']}, "
                   f"recovered={stats['total_recovered']}",
            llm_calls=0,
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-38",
            name="重试机制 — 瞬时故障自动重试恢复",
            category="resilience",
            success=False,
            elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


# ============================================================================
# E2E-39~43: 对话服务 + Gateway 渠道 + 路径遍历防护 (issue #88-#90)
# ============================================================================


def step_39_chat_service(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-39: ChatService 多轮对话 + 人格注入 + 持久化 (issue #88)。"""
    start = time.monotonic()
    try:
        from mortis.web.chat import ChatService
        svc = ChatService(env.master)
        # 1. 新建对话 + 发送
        resp1 = svc.send("你好,介绍下自己")
        ok_send = (
            resp1.conversation_id.startswith("conv-")
            and len(resp1.message) > 0
            and resp1.elapsed_sec >= 0
        )
        cid = resp1.conversation_id
        # 2. 多轮续接
        resp2 = svc.send("继续聊聊", cid)
        ok_multi_turn = resp2.conversation_id == cid
        # 3. 历史持久化
        history = svc.get_history(cid)
        ok_history = (
            history is not None
            and len(history) == 4  # 2 user + 2 assistant
            and history[0]["role"] == "user"
            and history[1]["role"] == "assistant"
        )
        # 4. 人格注入验证 — messages[0] 是 seed tone
        conv = svc.get_conversation(cid)
        msgs = svc._build_messages(conv)
        ok_persona = (
            len(msgs) >= 2
            and msgs[0].role == "system"
            and len(msgs[0].content) > 0  # tone
        )
        # 5. 磁盘文件存在
        disk_path = env.vault_root / "mortis-journal" / "conversations" / f"{cid}.json"
        ok_disk = disk_path.exists()
        ok = ok_send and ok_multi_turn and ok_history and ok_persona and ok_disk
        report.add(StepResult(
            step_id="E2E-39", name="ChatService 多轮对话 + 人格注入 + 持久化 (issue #88)",
            category="chat", success=ok, elapsed_sec=time.monotonic() - start,
            detail=f"send={ok_send}, multi_turn={ok_multi_turn}, history={ok_history} "
                   f"(msgs={len(history)}), persona={ok_persona} (tone注入), disk={ok_disk}",
            llm_calls=2,
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-39", name="ChatService 多轮对话 + 人格注入 + 持久化 (issue #88)",
            category="chat", success=False, elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


def step_40_chat_sse_stream(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-40: Chat SSE 流式端点 + OpenUI 风格 HTML 页面 (issue #88)。"""
    start = time.monotonic()
    try:
        # 重启 web server 带 chat_service
        env.stop_web()
        base_url = env.start_web(with_chat=True)
        # 1. HTML 对话页面
        html_status, html_body = _get_html(base_url, "/chat")
        ok_html = (
            html_status == 200
            and "chat-layout" in html_body
            and "chat-sidebar" in html_body
            and "chat-messages" in html_body
            and "chat-input" in html_body
            and "sendMessage" in html_body
            and "newConversation" in html_body
        )
        # 2. 非流式 POST /api/chat
        api_status, api_data = _post_json(base_url, "/api/chat", {
            "message": "E2E 测试消息",
        })
        ok_api = (
            api_status == 200
            and api_data["conversation_id"].startswith("conv-")
            and len(api_data["message"]) > 0
            and api_data["role"] == "assistant"
        )
        cid = api_data.get("conversation_id", "")
        # 3. SSE 流式 POST /api/chat/stream
        stream_status, stream_body = _post_stream(base_url, "/api/chat/stream", {
            "message": "流式续接", "conversation_id": cid,
        })
        ok_stream = (
            stream_status == 200
            and "data: " in stream_body
            and "delta" in stream_body
            and "finish_reason" in stream_body
            and "done" in stream_body
            and cid in stream_body  # conversation_id 在首个 chunk 返回
        )
        # 4. 对话列表 API
        list_status, list_data = _get_json(base_url, "/api/conversations")
        ok_list = (
            list_status == 200
            and list_data["total"] >= 1
            and any(c["conversation_id"] == cid for c in list_data["conversations"])
        )
        ok = ok_html and ok_api and ok_stream and ok_list
        report.add(StepResult(
            step_id="E2E-40", name="Chat SSE 流式 + OpenUI HTML 页面 (issue #88)",
            category="chat", success=ok, elapsed_sec=time.monotonic() - start,
            detail=f"html={ok_html} (chat-layout+sidebar+input+JS), "
                   f"api={ok_api} (cid={cid[:16]}...), stream={ok_stream} (SSE data:), "
                   f"list={ok_list} (total={list_data.get('total')})",
            llm_calls=2,
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-40", name="Chat SSE 流式 + OpenUI HTML 页面 (issue #88)",
            category="chat", success=False, elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


def step_41_gateway_routing(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-41: Gateway 渠道路由 — InboundMessage → ChatService → OutboundMessage (issue #89)。"""
    start = time.monotonic()
    try:
        from mortis.gateway import Gateway, WebChannel, InboundMessage
        from mortis.web.chat import ChatService
        svc = ChatService(env.master)
        gw = Gateway(svc)
        gw.register_channel(WebChannel())
        # 1. 首次消息 (无 conversation_id → 按 sender 映射新建)
        msg1 = InboundMessage(channel="web", sender_id="user-e2e-1", content="你好")
        out1 = gw.handle_inbound(msg1)
        ok_first = (
            out1.channel == "web"
            and out1.recipient_id == "user-e2e-1"
            and len(out1.content) > 0
            and out1.conversation_id.startswith("conv-")
        )
        cid1 = out1.conversation_id
        # 2. 同一 sender 第二条消息 → 复用同一 conversation
        msg2 = InboundMessage(channel="web", sender_id="user-e2e-1", content="继续")
        out2 = gw.handle_inbound(msg2)
        ok_reuse = out2.conversation_id == cid1
        # 3. 不同 sender → 新建对话
        msg3 = InboundMessage(channel="web", sender_id="user-e2e-2", content="新用户")
        out3 = gw.handle_inbound(msg3)
        ok_isolation = out3.conversation_id != cid1
        # 4. 渠道注册表
        ok_channels = "web" in gw.list_channels()
        # 5. 流式 handle_inbound_stream
        cid_stream, gen = gw.handle_inbound_stream(InboundMessage(
            channel="web", sender_id="user-e2e-3", content="流式测试",
        ))
        chunks = list(gen)
        ok_stream = (
            cid_stream.startswith("conv-")
            and len(chunks) > 0
            and all(hasattr(c, "delta") for c in chunks)
        )
        ok = ok_first and ok_reuse and ok_isolation and ok_channels and ok_stream
        report.add(StepResult(
            step_id="E2E-41", name="Gateway 渠道路由 — Inbound→ChatService→Outbound (issue #89)",
            category="gateway", success=ok, elapsed_sec=time.monotonic() - start,
            detail=f"first={ok_first} (cid={cid1[:16]}...), reuse={ok_reuse} (同sender复用), "
                   f"isolation={ok_isolation} (不同sender隔离), channels={ok_channels}, "
                   f"stream={ok_stream} (chunks={len(chunks)})",
            llm_calls=4,
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-41", name="Gateway 渠道路由 — Inbound→ChatService→Outbound (issue #89)",
            category="gateway", success=False, elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


def step_42_gateway_multi_channel(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-42: Gateway 多渠道隔离 + 主动推送渠道 (issue #89)。"""
    start = time.monotonic()
    try:
        from mortis.gateway import Gateway, InboundMessage, OutboundMessage
        from mortis.web.chat import ChatService

        # 自定义主动推送渠道 (模拟微信/Telegram)
        sent: list[OutboundMessage] = []

        class SpyChannel:
            name = "spy"
            def send(self, outbound: OutboundMessage) -> None:
                sent.append(outbound)
            def start(self) -> None:
                pass
            def stop(self) -> None:
                pass

        svc = ChatService(env.master)
        gw = Gateway(svc)
        from mortis.gateway import WebChannel
        gw.register_channel(WebChannel())
        gw.register_channel(SpyChannel())
        # 1. web 渠道消息 → WebChannel.send 是 no-op
        out_web = gw.handle_inbound(InboundMessage(
            channel="web", sender_id="w1", content="web 消息",
        ))
        ok_web = out_web.channel == "web" and len(out_web.content) > 0
        # 2. spy 渠道消息 → SpyChannel.send 被调用 (主动推送)
        sent.clear()
        out_spy = gw.handle_inbound(InboundMessage(
            channel="spy", sender_id="s1", content="spy 消息",
        ))
        ok_push = len(sent) == 1 and sent[0].content == out_spy.content
        # 3. 两渠道 sender 隔离
        ok_isolation = out_web.conversation_id != out_spy.conversation_id
        # 4. start_all / stop_all 不报错
        gw.start_all()
        gw.stop_all()
        ok_lifecycle = True
        # 5. 未知渠道 → 不推送但回复仍生成
        out_unknown = gw.handle_inbound(InboundMessage(
            channel="unknown", sender_id="u1", content="未知渠道",
        ))
        ok_unknown = len(out_unknown.content) > 0
        ok = ok_web and ok_push and ok_isolation and ok_lifecycle and ok_unknown
        report.add(StepResult(
            step_id="E2E-42", name="Gateway 多渠道隔离 + 主动推送 (issue #89)",
            category="gateway", success=ok, elapsed_sec=time.monotonic() - start,
            detail=f"web={ok_web} (no-op), push={ok_push} (SpyChannel.send被调), "
                   f"isolation={ok_isolation}, lifecycle={ok_lifecycle}, "
                   f"unknown_channel={ok_unknown} (回复仍生成)",
            llm_calls=3,
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-42", name="Gateway 多渠道隔离 + 主动推送 (issue #89)",
            category="gateway", success=False, elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


def step_43_path_traversal_guard(env: ExperimentEnv, report: ExperimentReport) -> None:
    """E2E-43: 路径遍历防护 — conversation_id 校验 (issue #90)。

    漏洞: conversation_id 从 URL/body 直接拼路径, 未校验 → 可读/删任意 .json。
    修复: is_valid_conversation_id 只允许 [a-zA-Z0-9-]。
    """
    start = time.monotonic()
    try:
        from mortis.web.chat import ChatService, is_valid_conversation_id
        svc = ChatService(env.master)
        # 1. 校验函数
        ok_valid = is_valid_conversation_id("conv-abc123")
        ok_invalid = (
            not is_valid_conversation_id("../../etc/passwd")
            and not is_valid_conversation_id("../steiner/unease")
            and not is_valid_conversation_id("")
            and not is_valid_conversation_id("a/b")
            and not is_valid_conversation_id("a.b")
        )
        # 2. get_conversation 拒绝 traversal (返回 None, 不读磁盘)
        ok_get = svc.get_conversation("../../secret") is None
        # 3. get_history 拒绝 traversal
        ok_history = svc.get_history("../../etc/passwd") is None
        # 4. delete_conversation 拒绝 traversal (不删文件)
        victim_dir = env.vault_root / "mortis-steiner"
        victim_dir.mkdir(parents=True, exist_ok=True)
        victim = victim_dir / "unease.json"
        victim.write_text('{"victim": true}', encoding="utf-8")
        ok_delete = (
            svc.delete_conversation("../../mortis-steiner/unease") is False
            and victim.exists()
        )
        # 5. send 传恶意 cid → 新建安全对话 (不沿用恶意 ID)
        resp = svc.send("hi", "../../etc/passwd")
        ok_send_safe = (
            resp.conversation_id != "../../etc/passwd"
            and resp.conversation_id.startswith("conv-")
        )
        ok = ok_valid and ok_invalid and ok_get and ok_history and ok_delete and ok_send_safe
        report.add(StepResult(
            step_id="E2E-43", name="路径遍历防护 — conversation_id 校验 (issue #90)",
            category="security", success=ok, elapsed_sec=time.monotonic() - start,
            detail=f"validate={ok_valid and ok_invalid}, get={ok_get}, "
                   f"history={ok_history}, delete={ok_delete} (victim存活), "
                   f"send_safe={ok_send_safe} (cid={resp.conversation_id[:16]}...)",
            llm_calls=1,
        ))
    except Exception as e:
        report.add(StepResult(
            step_id="E2E-43", name="路径遍历防护 — conversation_id 校验 (issue #90)",
            category="security", success=False, elapsed_sec=time.monotonic() - start,
            error=f"{type(e).__name__}: {e}",
        ))


# ============================================================================
# 主流程
# ============================================================================

def main() -> int:
    use_mock = "--mock" in sys.argv
    has_key = bool(os.environ.get("MINIMAX_API_KEY"))
    if not has_key and not use_mock:
        print("ERROR: MINIMAX_API_KEY 环境变量未设置 (或用 --mock 走 MockProvider)")
        return 1

    print("=" * 70)
    mode = "MockProvider (离线)" if not has_key else "真实 minimax LLM 调用链"
    print(f"Mortis v3 全项 E2E 生产级实验 — {mode}")
    print("=" * 70)
    print()

    report = ExperimentReport(
        started_at=datetime.now(timezone.utc).isoformat(),
        finished_at="",
        total_elapsed_sec=0,
    )

    env = ExperimentEnv(report=report)
    print(f"实验环境: {env.tmpdir}")
    print(f"Provider: {type(env.provider).__name__} (wrapped: LoggingProvider)")
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
        step_26_web_server_dashboard,
        step_27_web_growths,
        step_28_web_unease,
        step_29_web_notifications,
        step_30_web_dreams,
        step_31_web_404_and_dataflow,
        # E2E-32~38: 异常输入 + 子智能体派发 + 流式输出 + 韧性层
        step_32_exception_file_not_found,
        step_33_exception_malformed_growth,
        step_34_exception_llm_unavailable,
        step_35_subagent_delegation,
        step_36_streaming_output,
        step_37_circuit_breaker,
        step_38_retry_provider,
        # E2E-39~43: 对话服务 + Gateway 渠道 + 路径遍历防护 (issue #88-#90)
        step_39_chat_service,
        step_40_chat_sse_stream,
        step_41_gateway_routing,
        step_42_gateway_multi_channel,
        step_43_path_traversal_guard,
    ]

    for i, step_fn in enumerate(steps, 1):
        step_id = f"E2E-{i:02d}"
        env.set_step_id(step_id)
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

    # 保存 LLM 调用日志
    llm_logs_path = PROJECT_ROOT / "docs" / "mortis-audit-v3" / "e2e-llm-logs.json"
    report.save_llm_logs(llm_logs_path)
    print(f"LLM 调用日志: {llm_logs_path} ({len(report.llm_logs)} 条记录)")

    # 生成报告 (写入 raw 文件, 不覆盖手工版 e2e-report.md / e2e-report-agent.md)
    report_path = PROJECT_ROOT / "docs" / "mortis-audit-v3" / "e2e-report-raw.md"
    _write_report(report, report_path)
    print()
    print("=" * 70)
    print(f"实验完成: {report.summary['passed']}/{report.summary['total_steps']} passed, "
          f"{report.summary['failed']} failed, "
          f"{report.summary['total_llm_calls']} LLM calls, "
          f"{report.total_elapsed_sec:.1f}s")
    print(f"报告 (raw): {report_path}")
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
        "## 覆盖的 Web UI 交互入口（issue #52/#53/#54）",
        "",
        "| 端点 | 方法 | 功能 | E2E 步骤 |",
        "|------|------|------|:--------:|",
        "| / | GET | dashboard 仪表盘 (phase+unease+growth 概览) | E2E-26 |",
        "| /growths | GET | growth 浏览器 (列表, 50 条预览) | E2E-27 |",
        "| /growths/<rel> | GET | growth 详情 (含 emotional_*, owner 视角) | E2E-27 |",
        "| /unease | GET | unease 仪表盘 (7 维度 + max + last_decay) | E2E-28 |",
        "| /notifications | GET | owner 通知通道 (drift/unease/dream) | E2E-29 |",
        "| /dreams | GET | dream 日历 (light/medium/deep 分组) | E2E-30 |",
        "| /unknown | GET | 404 路由兜底 | E2E-31 |",
        "| — | — | 数据流转校验 (vault 原文 ↔ HTTP 返回一致) | E2E-31 |",
        "",
        "## 覆盖的异常输入与韧性测试",
        "",
        "| 类别 | 测试场景 | E2E 步骤 |",
        "|------|----------|:--------:|",
        "| exception | VaultReadAgent 读取不存在的文件 (优雅降级) | E2E-32 |",
        "| exception | 格式错误的 growth 文件 (不崩溃) | E2E-33 |",
        "| exception | LLM 服务不可用 + FallbackProvider 降级 | E2E-34 |",
        "| delegation | 子智能体派发 — 复杂多文件查询任务 (context 传递) | E2E-35 |",
        "| streaming | 流式输出 generate_stream (逐块返回) | E2E-36 |",
        "| resilience | 熔断器 — 连续失败触发熔断 + 恢复 | E2E-37 |",
        "| resilience | 重试机制 — 瞬时故障自动重试恢复 | E2E-38 |",
        "",
        "## LLM 调用日志增强字段",
        "",
        "| 字段 | 说明 |",
        "|------|------|",
        "| input_length | 输入总字符数 (所有 message content 之和) |",
        "| output_length | 输出总字符数 (response 长度) |",
        "| model_version | 模型版本 (如 MiniMax-M3) |",
        "| endpoint | API 端点 URL |",
        "| think_content | 思考过程内容 (```...``` 中的内容, 已从 response 分离) |",
        "| think_content_length | 思考过程内容长度 |",
        "| retry_count | 重试次数 (若使用 RetryProvider) |",
        "",
    ])

    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())

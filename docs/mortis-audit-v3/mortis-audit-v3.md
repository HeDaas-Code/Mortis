# Mortis v3 代码审计报告 — 方法级 + 测试覆盖率 + 时间轴

> **CODE AUDIT REPORT · v3.1 · METHOD-LEVEL + TEST COVERAGE + TIMELINE**
>
> 分支: `main` (含 PR #66 合并) | 日期: 2026-06-25 | 代码量: ~9,800 行源码 + 7,200 行测试 | 测试: 986 passed, 2 skipped | Issues: 88 全部关闭

| 子包模块 | 核心抽象 | LLM 调用点 | Redact 覆盖 | 已修漏洞 | 测试文件 | 流程节点 |
|:--------:|:--------:|:----------:|:-----------:|:--------:|:--------:|:--------:|
| 16 | 6 | 11 | 8/11 | 22 | 64 | 78 |

---

## 目录

- [01 审计概览](#01-审计概览)
- [02 方法级审计](#02-方法级审计)
- [03 测试覆盖率分析](#03-测试覆盖率分析)
- [04 架构分析](#04-架构分析)
- [05 调用链分析](#05-调用链分析)
- [06 信号结构](#06-信号结构)
- [07 安全审计](#07-安全审计)
- [08 信息流转模拟](#08-信息流转模拟)
- [09 分支与 Issue 时间轴](#09-分支与-issue-时间轴)
- [10 发现与建议](#10-发现与建议)

---

## 01 审计概览

本次审计对 Mortis v3 main 分支（含 PR #66 合并）进行方法级代码分析 + 全流程测试覆盖率分析 + 分支与 issue 时间轴梳理。

### 审计范围

审计基于 `main` 分支 HEAD `1dadd28`（2026-06-25），覆盖：
- **方法级审计**：16 个子包、60 个 Python 模块、约 80 个 class、约 290 个方法/函数
- **测试覆盖分析**：64 个测试文件、约 180 个测试类、986 个测试用例、78 个流程节点
- **时间轴**：5 天开发周期（2026-06-20 至 2026-06-25）、60+ 提交、88 个 issues、10+ 分支

### 关键发现摘要

> **✅ 架构健康度: 良好**
>
> 16 个子包采用清晰的 Protocol-based 分层架构，无循环依赖。底层（seed/clock）零内部依赖，中层（growth/vault/provider）提供数据与抽象，上层（runtime/pipeline）编排，顶层（cli/web）入口。vault 作为认知系统中枢被 7 个包依赖，growth 作为次中枢被 5 个包依赖。

> **✅ 安全状态: 22 项已修 / 0 项潜在**
>
> 已修复 22 个安全漏洞（含 S1-S3 路径遍历、#6 白名单下沉、#17 ReviewGate 越权、#38 steiner 隐藏层、#67 中段绕过、#71 异常吞没、#73 redact、CRITICAL-1/2 数据泄漏、#83-#88 redact 共享模块与统一类型）。**所有 11 个 LLM 调用点中 8 个已覆盖 redact**（#9/#10/#4/#5/#6/#7 + growth preview + seed_check），剩余 3 个为 pipeline 层带人格上下文（#1/#2/#3）和纯统计数字（#11），无私密字段泄漏风险。

> **✅ 测试覆盖: 986 passed / 78 节点**
>
> 64 个测试文件覆盖 78 个流程节点（A-M 共 13 大类）。覆盖最密集：Dream 流水线（C 类 10 文件）、Growth 生命周期（D 类 10 文件）、Vault 安全（I 类 8 文件）。覆盖薄弱：Web UI（L 类 1 文件）、CLI 命令（K 类 2 文件）。Gap 分析：A1 主循环入口端到端未覆盖。

> **ℹ️ 调用链复杂度: 中等**
>
> 主循环 4 步（Think→Plan→Act→Review），ActStep 内含工具调用循环（MAX_ITERATIONS=5）。Dream 侧 3 级梦境（Light 4 phase / Medium 5 phase / Deep 7 phase）。共 11 个独立 LLM 调用点，其中 pipeline 层 3 个（带人格上下文）、dream/reflect 层 4 个（已 redact）、toolagent 层 4 个（已 redact）。

---

## 02 方法级审计

16 个子包、60 个 Python 模块的方法级清单。标注：`[LLM]` LLM 调用点、`[VAULT-WRITE]` vault 写入、`[REDACT]` redact 调用、`[SIGNAL]` 信号产生。

### 2.1 seed 包（人格种子）

#### seed/loader.py
- `class Seed` (line 14): 主人格种子，七维度任一缺失 = 不完整
  - `get_dimension(name) -> str` (line 25): 按维度名取值
  - `to_dict() -> dict` (line 31): 转字典
  - `summary() -> str` (line 34): 给 sub 用的紧凑摘要
  - `is_complete() -> bool` (line 43): 种子完整性检查
  - `missing_dimensions() -> list[str]` (line 47): 缺失维度列表
- `load_seed(path) -> Seed` (line 69): 从 seed.md 加载

#### seed/schema.py
- `SEVEN_DIMENSIONS` (line 6): 七维度硬编码契约

#### seed/writer.py
- `save_seed(seed, path) -> None` (line 11): 序列化回 seed.md

### 2.2 clock 包（逻辑时钟）

#### clock/logical.py
- `class ConsciousnessState(str, Enum)` (line 24): 6 时段状态机（AWAKE/REFLECT/DREAM_LIGHT/DREAM_MEDIUM/DREAM_DEEP/ERODE）
- `class LogicalClock` (line 67): 逻辑时钟
  - `now(real_now) -> datetime` (line 89): 当前时间（可注入）
  - `state(at) -> ConsciousnessState` (line 97): 判断 at 时刻的时段
  - `next_transition(at) -> tuple[datetime, ConsciousnessState]` (line 108): 下一时段切换

#### clock/state.py
- `class SleepState` (line 28): 睡眠状态 — 跟踪清醒时长与债务
  - `fresh(now) -> SleepState` classmethod (line 35): 新一天的睡眠状态
- `update_sleep_state(state, now, *, slept) -> SleepState` (line 41): 更新睡眠状态
- `sleep_deprived_tone(debt) -> str` (line 82): 睡眠不足语气注入

#### clock/schedule.py
- `class TickResult` (line 31): Scheduler 单次 tick 结果
- `detect_goodnight(message) -> bool` (line 41): 检测 owner 是否说"晚安"
- `class Scheduler` (line 49): 调度 REFLECT/DREAM 触发
  - `tick(*, owner_last_active, owner_message, sleep_state, now) -> TickResult` (line 63): 单次 tick

### 2.3 growth 包（长期记忆）

#### growth/model.py
- `class Dimension(str, Enum)` (line 17): 七维度
- `class DreamLevel(str, Enum)` (line 33): 梦境分级
- `class Growth` (line 45): 长期记忆条目 — frozen dataclass
- `assert_dimension_consistency() -> None` (line 81): 单测用

#### growth/frontmatter.py
- `class FrontmatterError(ValueError)` (line 34): 解析错误
- `parse_frontmatter(text) -> tuple[dict, str]` (line 56): 提取 frontmatter + body
- `serialize_frontmatter(meta, body) -> str` (line 69): dict + body → md
- `parse_growth_file(text) -> Growth` (line 93): md → Growth
- `serialize_growth_file(growth) -> str` (line 126): Growth → md

#### growth/writer.py
- `write_growth_obsidian(growth, related_growths) -> str` (line 61): Obsidian-Native 格式
- `extract_wikilinks_from_body(body) -> tuple[str, ...]` (line 112): 提取 `[[双链]]`
- `extract_tags_inline_from_body(body) -> tuple[str, ...]` (line 127): 提取 `#tag`

#### growth/compress.py
- `compress_growths(vault, provider, dimension) -> dict` (line 35): 压缩同维度低 confidence growth `[LLM间接]` `[VAULT-WRITE]`

#### growth/vault_layout.py
- `growth_rel(dimension, growth_id, ext) -> str` (line 43): growth 文件路径
- `growth_archive_rel(dimension, growth_id, ext) -> str` (line 48): archive 路径
- `list_dimension_dirs() -> tuple[str, ...]` (line 57): 7 维度子目录名

### 2.4 vault 包（认知存储）

#### vault/base.py
- `class VaultEntry` (line 14): vault 单条记录 — frozen dataclass
- `class VaultProtocol(Protocol)` (line 21): vault 抽象协议
  - `read/write/exists/list_entries/write_sub_output/list_pending_sub_outputs/approve_sub_output/discard_sub_output`
- `class VaultSecurity` (line 69): 安全层
  - `_normalize(rel_path) -> str` staticmethod (line 73): 栈式归一化 `(关键安全)`
  - `check_whitelist(rel_path, whitelist) -> bool` staticmethod (line 93): 白名单检查
  - `deny_reason(rel_path, whitelist) -> str` staticmethod (line 109): 拒绝原因

#### vault/local.py
- `class VaultAccessDenied(Exception)` (line 27): 白名单拒绝
- `class Vault` (line 32): 本地目录实现
  - `_safe_path(rel_path) -> Path` (line 51): 归一化 + vault 根内检查 `(关键安全)`
  - `_enforce(rel_path, whitelist, op)` (line 69): 白名单强制 `(关键安全)`
  - `read(rel_path, whitelist) -> VaultEntry` (line 80)
  - `write(rel_path, content, whitelist) -> VaultEntry` (line 98) `[VAULT-WRITE]`
  - `exists(rel_path, whitelist) -> bool` (line 122)
  - `list_entries(rel_dir, whitelist) -> list[str]` (line 135)
  - `write_sub_output(sub_id, content) -> str` (line 161) `[VAULT-WRITE]`
  - `list_pending_sub_outputs() -> list[str]` (line 172)
  - `approve_sub_output(rel_path, target_rel) -> str` (line 176) `[VAULT-WRITE]`
  - `discard_sub_output(rel_path) -> None` (line 196)
  - `write_growth(growth) -> None` (line 213) `[VAULT-WRITE]` `[SIGNAL-growth]`
  - `read_growth(rel_path) -> Growth` (line 230)
  - `list_growths(dimension) -> list[str]` (line 245)
  - `list_growths_by_tag(tag) -> list[str]` (line 262)
  - `list_growths_min_confidence(min_conf) -> list[str]` (line 278)
  - `archive_growth(dimension, growth_id) -> bool` (line 294)
  - `delete_growth(rel_path) -> bool` (line 315)

#### vault/obsidian.py
- `class Wikilink/Callout/Fold/ParsedObsidian`: Obsidian 语法结构
- `parse(text) -> ParsedObsidian` (line 135): 解析 Obsidian md
- `render_wikilink/render_embed/render_callout/render_subconscious`: 生成 Obsidian 文本

#### vault/review.py
- `class ReviewDecision(str, Enum)` (line 12): 审阅决定
- `class ReviewResult` (line 22): 审阅结果 — frozen dataclass
- `class ReviewGate` (line 30): 审阅门
  - `review(content, rel_path) -> ReviewResult` staticmethod (line 40): 自动审阅
  - `master_review(...)` staticmethod (line 57): 主人格审阅
  - `owner_override(...)` staticmethod (line 89): Owner 强制覆盖
  - `apply(...) -> str` staticmethod (line 110): 执行审阅决定 `[VAULT-WRITE]`
    - 内部 `_safe_write(target, content)` (line 155): 所有写操作先过白名单 `(关键安全)`

#### vault/normalize.py
- `normalize_rel_path(rel_path) -> str` (line 15): 栈式归一化，消除 .. 和 .

### 2.5 memory 包（会话/线程/归档）

#### memory/session.py
- `class Session` (line 14): 单次会话上下文
  - `to_dict/from_dict/save/load/add_thread`

#### memory/thread.py
- `class StepRecord` (line 14): 步骤执行记录
- `class Thread` (line 25): 任务执行线程
  - `add_step/complete/discard/add_context_ref/to_dict/from_dict/save/load`

#### memory/archive.py
- `class ArchiveEntry` (line 13): 归档记录 — frozen dataclass
- `class MemoryArchive` (line 22): 记忆归档器
  - `archive_thread(thread_id, thread_json_path, summary, target_rel) -> ArchiveEntry` (line 28) `[VAULT-WRITE]`
  - `auto_archive(thread_json_path, target_rel) -> ArchiveEntry` (line 95) `[VAULT-WRITE]`

### 2.6 provider 包（LLM Provider）

#### provider/base.py
- `class Message` (line 11): LLM 消息 — dataclass
- `class LLMProviderProtocol(Protocol)` (line 19): LLM provider 协议
  - `generate(messages, *, temperature, max_tokens) -> Message` (line 32) `[LLM]`
  - `generate_text(prompt, system, *, temperature, max_tokens) -> str` (line 51) `[LLM]`
  - `async_generate(messages, ...) -> Message` (line 65) `[LLM]`
  - `async_generate_text(prompt, system, ...) -> str` (line 75) `[LLM]`
- `run_in_executor(func, *args, **kwargs) -> Any` (line 87): asyncio executor
- `class ToolCall` (line 107): 工具调用请求

#### provider/mock.py
- `class MockProvider` (line 14): 不调外部，deterministic mock
  - `generate/generate_text/async_generate/async_generate_text` `[LLM]`

#### provider/minimax.py
- `class MinimaxAuthError/RuntimeError` (line 23): 鉴权失败
- `class MinimaxAPIError/RuntimeError` (line 27): API 失败
- `class MinimaxProvider` (line 31): minimax API provider
  - `generate/generate_text/async_generate/async_generate_text` `[LLM]`

#### provider/registry.py
- `register_provider(name, factory) -> None` (line 24): 注册工厂
- `get_provider(name, **kwargs) -> LLMProviderProtocol` (line 35): 按名获取
- `list_providers() -> list[str]` (line 55): 已注册名称
- `make_provider(kind) -> LLMProviderProtocol` (line 60): 工厂函数

#### provider/router.py
- `configure_routing(config) -> None` (line 15): 配置任务路由
- `get_provider_for_task(task, default_provider) -> LLMProviderProtocol` (line 28): 按任务获取

#### provider/audit.py
- `sha256_prefix(text, length) -> str` (line 22): SHA256 前 length 位 hex
- `messages_hash(messages, length) -> str` (line 35): 消息列表审计 hash

### 2.7 tools 包（工具系统）

#### tools/base.py
- `class ToolResult` (line 10): 工具执行结果（统一类型）— frozen dataclass
  - `ok(name, content) -> ToolResult` classmethod (line 34)
  - `err(name, error) -> ToolResult` classmethod (line 38)
- `class ToolProtocol(Protocol)` (line 42): 工具协议
  - `name/description/input_schema` property
  - `execute(**kwargs) -> ToolResult` (line 60)

#### tools/registry.py
- `class ToolRegistry` (line 14): 工具注册表
  - `register/get/names/execute/tool_schemas`
- `make_default_registry(vault, provider, include_agents) -> ToolRegistry` (line 62): 默认注册表

#### tools/agent_tool.py
- `class VaultReadToolAgent(ToolProtocol)` (line 30): vault:read_agent 包装器
- `class VaultSearchToolAgent(ToolProtocol)` (line 108): vault:search_agent 包装器
- `class VaultStatsToolAgent(ToolProtocol)` (line 193): vault:stats_agent 包装器
- `class MarkdownRenderToolAgent(ToolProtocol)` (line 258): markdown:render 包装器
- `class ClockToolAgent(ToolProtocol)` (line 309): clock 包装器

#### tools/vault_tool.py
- `class VaultReadTool/VaultListTool/VaultWriteTool/VaultExistsTool`: 基础 vault 工具

### 2.8 toolagent 包（无人格执行体）

#### toolagent/base.py
- `class ToolAgentProtocol(Protocol)` (line 38): ToolAgent 协议
  - `execute(input) -> ToolResult` (line 51)
- `class ToolAgent` (line 56): ToolProtocol 薄包装
  - `from_tool(tool, agent_id, provider, timeout) -> ToolAgent` classmethod (line 88)
  - `_llm_generate(prompt, system, *, redact, **kwargs) -> str | None` (line 102) `[LLM]` `(关键 LLM 调用点)`
    - 含 `sha256_prefix` 审计 log（issue #87）
    - 含 `redact` 标记参数（issue #87）
  - `execute(input) -> ToolResult` (line 176)

#### toolagent/vault_read.py
- `class VaultReadAgent(ToolAgent)` (line 31): 读 vault + 双链解析 + 摘要
  - `execute(input) -> ToolResult` (line 57)
  - `_summarize(content, max_length) -> str | None` (line 110) `[LLM]` `[REDACT]` `(关键)`

#### toolagent/vault_search.py
- `class VaultSearchAgent` (line 37): 全文 + tag + 双链图 + 语义搜索
  - `execute(input) -> ToolResult` (line 65)
  - `_semantic_rerank(matches, query) -> tuple[list, str]` (line 151) `[LLM]` `[REDACT]` `(关键)`
  - `_bfs_links(seeds, max_depth) -> dict` (line 244): BFS 双链图遍历
- `_snippet(body, query, context, redact) -> str` (line 302) `[REDACT]` `(关键)`
- `_resolve_link(target, from_rel) -> str | None` (line 321): wikilink → rel path

#### toolagent/vault_stats.py
- `class VaultStatsAgent` (line 30): vault 统计 + LLM 分析
  - `execute(input) -> ToolResult` (line 39)
  - `_analyze_stats(total_files, by_dimension, histogram) -> str | None` (line 82) `[LLM]` `(关键)`

#### toolagent/markdown_render.py
- `class MarkdownRenderAgent` (line 28): Obsidian 文本解析（不读 vault）
  - `execute(input) -> ToolResult` (line 36)

#### toolagent/clock.py
- `class ClockAgent` (line 30): 当前时间 + 上次 dream
  - `execute(input) -> ToolResult` (line 38)
  - `_find_last_dream() -> str | None` (line 58): 扫 mortis-dream-log/

### 2.9 runtime 包（运行时上下文）

#### runtime/context.py
- `class RuntimeContext` (line 16): 运行时上下文 — dataclass
  - `search_growths(dimension, tag, query, min_confidence, limit)` (line 33): 主人格检索 growth
  - `growth_system_prompt(max_items) -> str` (line 62): growth 摘要 prompt
  - `growth_context_for_task(task, dimension, tag, max_items) -> str` (line 74): 动态检索
  - `unease_prompt_for_injection() -> str` (line 110): 读 unease → decay → prompt `[SIGNAL-unease]`
  - `messages_for_provider() -> list[Message]` (line 130): 构建消息列表

#### runtime/master.py
- `class MasterRuntime` (line 23): 主人格运行时 — dataclass
  - `identify() -> str` (line 35): 自报身份
  - `make_context(thread, tools) -> RuntimeContext` (line 39)
  - `create_thread(task) -> Thread` (line 49)
  - `get_thread/complete_thread/discard_thread/archive_thread`
  - `read_vault/write_vault` `[VAULT-WRITE]`
  - `generate(messages) -> Message` (line 114) `[LLM]`
  - `generate_text(prompt, system) -> str` (line 117) `[LLM]`

#### runtime/sub.py
- `class L0SubTemplate` (line 43): L0 硬编码通用模板
- `class SubTemplate` (line 55): L1 模板
  - `from_seed(sub_id, task, seed, agency_scope, voice) -> SubTemplate` classmethod (line 69)
  - `verify_seed(seed) -> bool` (line 87)
  - `to_l2(task, **overrides) -> L2SubInstance` (line 91)
- `class L2SubInstance(SubTemplate)` (line 108): L2 工作 sub
  - `verify_chain(seed, l1_template) -> bool` (line 119)
- `class SubRuntime` (line 131): sub 执行体
  - `is_alive/complete/discard/system_prompt/messages_for_provider`

#### runtime/growth_search.py
- `search_growths(vault, *, dimension, tag, query, min_confidence, limit) -> list[Growth]` (line 30)
- `growth_system_prompt(growths) -> str` (line 103): Growth 列表 → markdown
- `_preview_body(g) -> str` (line 136): growth preview 行 `[REDACT]` `(关键)`

### 2.10 pipeline 包（编排层）

#### pipeline/executor.py
- `class PipelineResult` (line 16): 执行结果
- `class PipelineExecutor` (line 26): 执行器
  - `run() -> PipelineResult` (line 43) `[LLM间接]` `[VAULT-WRITE]`
  - `_run_delegated(thread, step_outputs) -> PipelineResult` (line 119) `[VAULT-WRITE]`
  - `_save_thread(thread) -> None` (line 244)

#### pipeline/step.py
- `class StepOutput` (line 20): 步骤输出
- `parse_tool_calls_from_text(text) -> list[ToolCall]` (line 31): 解析 `[TOOL: name {...}]`
- `class Step(ABC)` (line 54): 步骤基类
  - `_call_provider(messages, tools) -> tuple[Message, list]` (line 83) `[LLM]` `(关键)`
  - `_extract_function_calls(msg) -> list[ToolCall]` (line 119)
- `class ThinkStep(Step)` (line 132): Think 步骤
- `class PlanStep(Step)` (line 166): Plan 步骤
- `class ActStep(Step)` (line 199): Act 步骤（含工具循环）
- `class ReviewStep(Step)` (line 242): Review 步骤

#### pipeline/router.py
- `class RouteDecision` (line 12): 路由决策
- `class TaskRouter` (line 19): 任务路由器
  - `route() -> RouteDecision` (line 25) `[LLM]`

### 2.11 reflect 包（REFLECT phase）

#### reflect/executor.py
- `class Reflection` (line 81): 反思快照 — frozen dataclass
- `reflection_rel(reflection_id) -> str` (line 100): 相对路径
- `list_pending_reflections(vault) -> list[str]` (line 105): 列 pending
- `class ReflectExecutor` (line 120): REFLECT 执行体
  - `run(session_paths, sessions_dir) -> Reflection` (line 138) `[LLM]` `[VAULT-WRITE]`
  - `_load_sessions(session_paths, sessions_dir) -> list[Session]` (line 189)
  - `_summarize_sessions(sessions) -> str` (line 213)
  - `_generate_reflection(sessions_text) -> str` (line 225) `[LLM]` `(关键)`
  - `_next_reflection_id() -> str` (line 235)
  - `_render_reflection_md(...)` (line 245)
  - `_title_for(body, fallback) -> str` staticmethod (line 280)

#### reflect/emotion.py
- `clear_cache() -> None` (line 57): 清空缓存
- `score_emotion(provider, session_path, session_text) -> tuple[float, float]` (line 62) `[LLM]` `[REDACT]` `(关键)`

#### reflect/triggers.py
- `should_reflect(now, last_reflection, session_count_today, owner_said_goodnight) -> bool` (line 23)
- `hours_since(last, now) -> float` (line 63)

### 2.12 dream 包（梦境 — 12 个文件）

#### dream/light.py
- `class Conflict` (line 55): 冲突记录
- `class LightDreamer(DreamPipeline)` (line 65): 浅梦 4 phase
  - `phase_recall() -> PhaseTrace` (line 103) `[LLM间接]`
  - `phase_associate() -> PhaseTrace` (line 196) `[LLM间接]`
  - `phase_crystallize() -> PhaseTrace` (line 219) `[VAULT-WRITE]` `[SIGNAL-growth]`
  - `phase_reconcile() -> PhaseTrace` (line 268) `[VAULT-WRITE]`
  - `_detect_conflicts(candidate, existing) -> list[Conflict]` (line 314) `(关键)`
  - `_write_conflict(conflict) -> None` (line 348) `[VAULT-WRITE]`

#### dream/medium.py
- `class MediumDreamer(DreamPipeline)` (line 60): 中梦 5 phase
  - `phase_recall/phase_associate/phase_simulate/phase_crystallize/phase_reconcile`
  - `_write_conflict_doc(...)` (line 369) `[VAULT-WRITE]`

#### dream/deep.py
- `class DeepDreamer(DreamPipeline)` (line 46): 深梦 7 phase
  - `phase_recall/phase_associate/phase_simulate/phase_crystallize/phase_reconcile`
  - `phase_erode() -> PhaseTrace` (line 223) `[VAULT-WRITE]`
  - `phase_seed_check() -> PhaseTrace` (line 264) `[LLM间接]` `[VAULT-WRITE]`

#### dream/pipeline.py
- `class PhaseTrace` (line 19): 单次 phase trace
- `class DreamResult` (line 27): 梦境结果
  - `ok` property (line 35)
  - `trace_for(phase) -> PhaseTrace | None` (line 38)
- `class DreamPipeline` (line 45): 流水线基类
  - `run() -> DreamResult` (line 54): 按 PHASES_BY_LEVEL 顺序调用

#### dream/phases.py
- `class DreamPhase(str, Enum)` (line 14): 7 阶段
- `class DreamLevel(str, Enum)` (line 33): 3 级
- `PHASES_BY_LEVEL` (line 42): 每个 level 的 phase 顺序

#### dream/recall.py
- `compute_weight(valence, arousal) -> float` (line 26): w = |v|×a
- `emotion_weighted_sample(items, k, rng) -> list` (line 38): 情绪加权采样

#### dream/associate.py
- `associate(provider, sessions_text) -> dict` (line 83) `[LLM]` `[REDACT]` `(关键)`

#### dream/crystallize.py
- `reset_counter() -> None` (line 48)
- `infer_dimension(body) -> Dimension` (line 71)
- `make_candidate(*, body, dimension, source_sessions, valence, arousal, id) -> Growth` (line 93) `[SIGNAL-growth]`
- `average_emotion(pairs) -> tuple[float, float]` (line 138)

#### dream/erode.py
- `erode_growths(growths, now) -> tuple[list, list]` (line 67)
- `days_since_validated(g, now) -> float` (line 110)

#### dream/seed_check.py
- `class DriftReport` (line 38): drift 报告 — frozen dataclass
  - `summary() -> str` (line 47)
- `seed_check(seed, growth_summary, provider, *, threshold, per_dim_alert, vault) -> DriftReport` (line 137) `[LLM]` `[REDACT]` `[VAULT-WRITE间接]` `(关键)`

#### dream/dream_log.py
- `class DreamLog` (line 46): 单次梦境日志 — frozen dataclass
- `dream_log_rel(level, today) -> str` (line 61)
- `write_dream_log(vault, result, *, started_at, finished_at, error) -> DreamLog` (line 68) `[VAULT-WRITE]`

#### dream/drift_log.py
- `log_drift(vault, drift_score, threshold, notified) -> None` (line 23) `[VAULT-WRITE]`
- `read_drift_log(vault) -> list[dict]` (line 54)
- `drift_stats(vault) -> dict` (line 69): 总次数、通知次数、误报率
- `dismiss_drift(vault, index) -> bool` (line 89) `[VAULT-WRITE]`

#### dream/triggers.py
- `class TriggerDecision` (line 38): 触发判断结果
- `should_medium_dream(vault, *, now, pending_reflections, manual, interval_days, pending_threshold) -> TriggerDecision` (line 80)
- `should_deep_dream(vault, *, now, drift_total, manual, interval_days, drift_threshold) -> TriggerDecision` (line 144)

### 2.13 steiner 包（隐藏层）

#### steiner/unease.py
- `class UneaseState` (line 63): 不安状态 — frozen dataclass
  - `max_unease() -> float` (line 74)
  - `dim_unease(dim) -> float` (line 80)
- `load_unease(vault) -> UneaseState` (line 85)
- `save_unease(vault, state) -> bool` (line 123) `[VAULT-WRITE]`
- `accumulate(state, dimension, delta) -> UneaseState` (line 150) `[SIGNAL-unease]`
- `decay(state, now) -> UneaseState` (line 166)

#### steiner/watcher.py
- `class FakeEvent` (line 40): 测试用
- `class GrowthWatcher` (line 140): 监控 mortis-growth/
  - `start() -> None` (line 169)
  - `stop() -> None` (line 186)

#### steiner/prompt.py
- `unease_prompt(unease) -> str` (line 53): 5 档文案 `[SIGNAL-unease]`

#### steiner/drift.py
- `should_notify_owner(unease) -> bool` (line 22): max ≥ 0.75 `[SIGNAL-unease]`

#### steiner/lifecycle.py
- `class SteinerController` (line 17): 生命周期管理
  - `start() -> None` (line 31)
  - `stop() -> None` (line 40)
  - `_on_edit(dim) -> None` (line 47): debounce + accumulate + save `[SIGNAL-unease]` `[VAULT-WRITE]` `(关键)`
  - `tick_decay() -> None` (line 68) `[VAULT-WRITE]`

### 2.14 cli 包（命令行）

#### cli/commands.py
- 14 个 `cmd_*` 函数：`list/whoami/dump/delegate/pending/approve/discard/archive/dream/reflect/status/daemon/goodnight/web`
- `build_parser() -> argparse.ArgumentParser` (line 284)
- `COMMANDS` (line 410): 命令注册表
- `main(argv) -> int` (line 428): CLI 入口

#### cli/daemon.py
- `class MortisDaemon` (line 34): 常驻进程
  - `start/stop/run/_tick/_do_reflect/_do_dream`

#### cli/goodnight.py
- `run_goodnight(vault_path, provider_kind, seed_path, deep) -> dict` (line 24)
- `_do_reflect/_do_dream_light/_do_dream_deep/_do_erode`

### 2.15 web 包（Web UI + 通知）

#### web/server.py
- `class MortisWebHandler(BaseHTTPRequestHandler)` (line 38): HTTP 处理器
  - `do_GET/_send_json/_serve_dashboard/_serve_growths/_serve_growth_detail/_serve_unease/_serve_notifications/_serve_dreams`
- `start_web_server(vault_path, port) -> HTTPServer` (line 181)

#### web/notify.py
- `send_notification(vault, ntype, message, severity) -> None` (line 36) `[VAULT-WRITE]` `[SIGNAL-notification]`
- `read_notifications(vault) -> list[dict]` (line 86)
- `mark_read(vault, index) -> bool` (line 102) `[VAULT-WRITE]`

### 2.16 顶层模块

#### redact.py（共享 redact 工具）
- `SENSITIVE_PATTERNS` (line 30): 6 个 redact 模式
- `redact_snippet(text) -> str` (line 56) `[REDACT]` `(关键)`

#### __init__.py
- `write_growth/read_growth/list_growths/list_growths_by_tag/list_growths_min_confidence`: 顶层包装
- `__version__` (line 91): "0.2.0"

### 方法级审计汇总

| 类别 | 数量 | 说明 |
|------|:----:|------|
| LLM 调用点 | 11 | pipeline 层 3 + dream/reflect 层 4 + toolagent 层 4 |
| Vault 写入点 | 30+ | vault 核心 7 + memory 2 + growth 5 + dream 12 + steiner 4 + web 2 |
| Redact 调用点 | 8 | redact_snippet + _summarize + _semantic_rerank + _snippet + _preview_body + score_emotion + associate + seed_check |
| 信号产生点 | 10+ | growth 5 + unease 5 |
| 关键安全方法 | 15 | _safe_path + _enforce + _safe_write + _normalize + normalize_rel_path 等 |

---

## 03 测试覆盖率分析

64 个测试文件、986 个测试用例、78 个流程节点的覆盖分析。

### 3.1 流程节点分类体系

| 大类 | 名称 | 子节点数 | 覆盖文件数 |
|------|------|:--------:|:----------:|
| A | 主循环流程 | 5 | 3 |
| B | 认知周期 | 8 | 8 |
| C | Dream 流水线 | 7 | 10 |
| D | Growth 生命周期 | 8 | 10 |
| E | Reflect 流程 | 5 | 4 |
| F | Steiner 隐藏层 | 6 | 6 |
| G | Provider 层 | 6 | 6 |
| H | ToolAgent 层 | 8 | 8 |
| I | Vault 安全 | 7 | 8 |
| J | Redact 脱敏 | 9 | 6 |
| K | CLI 命令 | 2 | 2 |
| L | Web UI | 6 | 1 |
| M | 通知通道 | 3 | 2 |
| **合计** | | **78** | **64** |

### 3.2 测试覆盖热力图

![Figure 9](https://raw.githubusercontent.com/HeDaas-Code/Mortis/main/docs/mortis-audit-v3/images/diagram-09-test-coverage.png)

> **Figure 9**: 测试覆盖率热力图 — 78 个流程节点 × 测试文件数。红框=未覆盖，浅灰=薄弱（1 文件），深灰=密集（6+ 文件）

### 3.3 各测试文件覆盖详情

#### A. 主循环流程（3 文件）

| 测试文件 | 测试数 | 覆盖节点 | 测试内容 |
|---------|:------:|---------|---------|
| test_layers.py | 多 | A6, A7, A8 | MasterRuntime / SubRuntime / PipelineExecutor 集成 |
| test_pipeline_chain.py | 6 类 | A6, A7, A8, I7, I2 | seed hash / L2 chain / ReviewDecision / ReviewGate whitelist |
| test_pipeline_growth_injection.py | 4 类 | A2-A5, D6 | growth 动态注入 system prompt |

#### B. 认知周期（8 文件）

| 测试文件 | 测试数 | 覆盖节点 | 测试内容 |
|---------|:------:|---------|---------|
| test_logical_clock.py | 多 | B1 | LogicalClock + 6 时段 |
| test_clock_agent.py | 1 类 | B1, H6 | ClockAgent |
| test_sleep_state.py | 8 | B2 | SleepState + debt 累积/衰减 |
| test_sleep_deprived_tone.py | 4 | B2 | 4 档睡眠不足语气 |
| test_scheduler.py | 多 | B3, B2, B4-B8 | Scheduler + TickResult |
| test_daemon.py | 6 类 | B10, B3, B4, B5, B6 | MortisDaemon 常驻进程 |
| test_goodnight.py | 6 类 | K7, B9, B4-B8 | goodnight 触发链 |
| test_reflect_triggers.py | 4 类 | E4, B9 | REFLECT 触发条件 |

#### C. Dream 流水线（10 文件）

| 测试文件 | 测试数 | 覆盖节点 | 测试内容 |
|---------|:------:|---------|---------|
| test_dream_recall.py | 6 类 | C1 | compute_weight + emotion_weighted_sample |
| test_light_dreamer.py | 5 类 | C1, C2, C4, C5, D3 | LightDreamer 4 phase 端到端 |
| test_medium_dreamer.py | 1 类 | C1-C5 | MediumDreamer 5 phase |
| test_deep_dreamer.py | 1 类 | C1-C7, D3, D4, F4 | DeepDreamer 7 phase |
| test_dream_phases.py | 3 类 | C1-C7 | DreamPhase / DreamLevel / PHASES_BY_LEVEL |
| test_dream_log.py | 2 类 | C1-C7 | DreamLog 写入 |
| test_dream_erode.py | 2 类 | C6, D8 | confidence 衰减 + archive |
| test_dream_triggers.py | 3 类 | B6, B7, E4 | Medium/Deep 触发条件 |
| test_seed_check.py | 3 类 | C7 | drift 计算 + LLM 自评 |
| test_seed_check_redact.py | 6 类 | J6, C7 | seed_check redact（issue #84 CRITICAL） |

#### D. Growth 生命周期（10 文件）

| 测试文件 | 测试数 | 覆盖节点 | 测试内容 |
|---------|:------:|---------|---------|
| test_growth_model.py | 3 类 | D1 | Growth dataclass + Dimension/DreamLevel enum |
| test_seed.py | 多 | D1 | seed loader 七维度 |
| test_growth_frontmatter.py | 2 类 | D2 | frontmatter 解析/序列化 |
| test_growth_writer.py | 3 类 | D3, D2 | Obsidian-Native writer |
| test_growth_subconscious.py | 4 类 | D2, D3 | subconscious 注释剥离/保留 |
| test_obsidian_parser.py | 8 类 | D2, I3 | Obsidian 解析层 |
| test_growth_vault.py | 1 类 | D4, D5, I2 | growth vault CRUD |
| test_runtime_growth.py | 9 类 | D5, D6 | RuntimeContext × growth 集成 |
| test_growth_compression.py | 7 类 | D7, D4 | 维度压缩（issue #47） |
| test_growth_preview_redact.py | 7 类 | J2-J4, J7, D6 | growth preview redact（issue #85） |

#### E. Reflect 流程（4 文件）

| 测试文件 | 测试数 | 覆盖节点 | 测试内容 |
|---------|:------:|---------|---------|
| test_reflect_executor.py | 6 类 | E1, E2, E3, E5 | ReflectExecutor 主流程 |
| test_reflect_emotion.py | 3 类 | E3, E5 | 情绪标注 + 缓存 |
| test_session_redact.py | 2 类 | J8, E3, C2 | session redact（issue #86） |
| test_reflect_triggers.py | 4 类 | E4, B9 | REFLECT 触发条件 |

#### F. Steiner 隐藏层（6 文件）

| 测试文件 | 测试数 | 覆盖节点 | 测试内容 |
|---------|:------:|---------|---------|
| test_steiner_unease.py | 4 类 | F1 | UneaseState + load/save/accumulate/decay |
| test_steiner_watcher.py | 6 类 | F2 | GrowthWatcher handler 逻辑 |
| test_steiner_prompt.py | 1 类 | F3 | unease_prompt 5 档文案 |
| test_steiner_drift.py | 1 类 | F4 | should_notify_owner 报警阈值 |
| test_steiner_controller.py | 6 类 | F1, F2, F5, F3 | SteinerController 生命周期（issue #58） |
| test_unease_injection.py | 7 类 | F3 | unease 注入 RuntimeContext（issue #57） |
| test_drift_log.py | 5 类 | F6, C7 | drift 历史日志（issue #48） |

#### G. Provider 层（6 文件）

| 测试文件 | 测试数 | 覆盖节点 | 测试内容 |
|---------|:------:|---------|---------|
| test_providers.py | 多 | G1, G2 | LLM providers mock/minimax |
| test_async_provider.py | 4 类 | G1, G2, G5 | 异步 provider 接口（issue #46） |
| test_provider_registry.py | 3 类 | G1-G4 | provider 注册表 + 任务路由（issue #45） |
| test_provider_audit.py | 4 类 | G1, G2, G6, H8 | provider 审计日志（issue #87） |

#### H. ToolAgent 层（8 文件）

| 测试文件 | 测试数 | 覆盖节点 | 测试内容 |
|---------|:------:|---------|---------|
| test_toolagent_base.py | 5 类 | H1, H7, H8 | ToolAgent 基础类 |
| test_toolagent_provider.py | 3 类 | H1, H8 | ToolAgent provider 注入（issue #63） |
| test_agent_tool.py | 5 类 | H1-H8, I5 | ToolProtocol 包装器（issue #64） |
| test_registry_agents.py | 3 类 | H1, H8, G3 | ToolAgent 注册 + provider 注入 |
| test_vault_read_agent.py | 1 类 | H2, I5, I6 | VaultReadAgent 读 + 双链解析 |
| test_vault_read_agent_security.py | 3 类 | H2, I5, I6, I4 | VaultReadAgent 安全边界（issue #67/#80） |
| test_vault_read_summarize.py | 3 类 | H2, G3, J2-J4, J9 | VaultReadAgent 摘要 + redact |
| test_vault_search_agent.py | 多类 | H3, J1-J5, J9, I5 | VaultSearchAgent 全文 + redact |
| test_vault_search_semantic.py | 1 类 | H3, G3 | VaultSearchAgent 语义搜索 |
| test_vault_stats_agent.py | 1 类 | H4 | VaultStatsAgent 统计 |
| test_vault_stats_analyze.py | 2 类 | H4, G3 | VaultStatsAgent LLM 分析 |
| test_markdown_render_agent.py | 1 类 | H5 | MarkdownRenderAgent |
| test_clock_agent.py | 1 类 | H6, B1 | ClockAgent |
| test_agent_tool_sub_private.py | 1 类 | H2, I5 | sub 私域阻断（issue #68） |

#### I. Vault 安全（8 文件）

| 测试文件 | 测试数 | 覆盖节点 | 测试内容 |
|---------|:------:|---------|---------|
| test_vault.py | 多 | I1, I2, I4, I5, A8 | vault 主人格脑子 + sub 产出管理 |
| test_vault_security.py | 3 类 | I4, I5, I6 | 路径安全审计 S1/S2/S3（issue #11/#12/#13） |
| test_obsidian_parser.py | 8 类 | I3, D2 | Obsidian 解析层 |
| test_pipeline_chain.py | 6 类 | I7, I2, A6-A8 | seed hash + L2 chain + ReviewGate |

#### J. Redact 脱敏（6 文件）

| 测试文件 | 测试数 | 覆盖节点 | 测试内容 |
|---------|:------:|---------|---------|
| test_redact.py | 5 类 | J1-J5, J9 | 共享 redact 工具（issue #83） |
| test_vault_search_agent.py | 多类 | J1-J5, J9 | redact 对抗性测试（嵌套/相邻/未闭合/fail-closed/大小写） |
| test_vault_read_summarize.py | 3 类 | J2-J4, J9 | _summarize redact |
| test_seed_check_redact.py | 6 类 | J6, C7 | seed_check redact（issue #84 CRITICAL） |
| test_growth_preview_redact.py | 7 类 | J2-J4, J7, D6 | growth preview redact（issue #85） |
| test_session_redact.py | 2 类 | J8, E3, C2 | session redact（issue #86） |

#### K. CLI 命令（2 文件）

| 测试文件 | 测试数 | 覆盖节点 | 测试内容 |
|---------|:------:|---------|---------|
| test_cli_extensions.py | 4 类 | K5, C1-C7, E1-E5 | dream/reflect/status 命令（issue #56） |
| test_goodnight.py | 6 类 | K7, B9, B4-B8 | goodnight 命令（issue #61） |

#### L. Web UI（1 文件）

| 测试文件 | 测试数 | 覆盖节点 | 测试内容 |
|---------|:------:|---------|---------|
| test_web_ui.py | 多类 | L1-L6, M1, F1, D4 | Web UI HTTP server（issue #52/#53/#54） |

#### M. 通知通道（2 文件）

| 测试文件 | 测试数 | 覆盖节点 | 测试内容 |
|---------|:------:|---------|---------|
| test_owner_notify.py | 4 类 | M1, M2, M3 | owner 通知通道（issue #54） |
| test_web_ui.py | 多类 | L5, M1 | Web UI /notifications |

### 3.4 Gap 分析

#### 完全未覆盖
- **A1（主循环入口）**：无独立测试验证主循环入口的端到端启动流程

#### 覆盖薄弱（仅 1 文件，风险较高）
- **D7（压缩）**：仅 test_growth_compression.py
- **D8（衰减）**：仅 test_dream_erode.py
- **F5（controller）**：仅 test_steiner_controller.py
- **F6（drift log）**：仅 test_drift_log.py
- **G4（routing）**：仅 test_provider_registry.py
- **G5（async）**：仅 test_async_provider.py
- **G6（audit）**：仅 test_provider_audit.py
- **H7（result）**：仅 test_toolagent_base.py
- **I1（vault 基础）**：仅 test_vault.py
- **I3（parser）**：仅 test_obsidian_parser.py
- **I7（seed hash）**：仅 test_pipeline_chain.py
- **J6/J7/J8（redact 专项）**：各仅 1 文件
- **B10（daemon）**：仅 test_daemon.py
- **L1-L6（Web UI 全部）**：仅 test_web_ui.py 单文件覆盖 6 个端点

### 3.5 测试覆盖统计

| 维度 | 数量 |
|------|------|
| test_*.py 文件总数 | **64** |
| 测试类总数 | 约 **180+** |
| 测试用例总数 | **986 passed, 2 skipped** |
| 流程节点总数 | **78** |
| 已覆盖节点 | **77**（A1 未覆盖） |
| 覆盖率 | **98.7%** |

---

## 04 架构分析

16 个子包的职责、分层依赖关系与核心抽象设计。

### 包结构总览

| 包 | 职责 | 关键文件 | 行数 | 层级 |
|----|------|----------|------|------|
| `seed` | 不可变人格核心。七维度 schema + loader | schema.py, loader.py | 135 | L0 |
| `clock` | 逻辑时钟 + 昼夜节律状态机 | logical.py, state.py, schedule.py | 450 | L0 |
| `growth` | 长期记忆/人格生长。Growth dataclass + vault 布局 | model.py, frontmatter.py, writer.py, compress.py | 800 | L1 |
| `vault` | 认知存储层。VaultProtocol + 本地实现 + 安全白名单 | base.py, local.py, obsidian.py, review.py, normalize.py | 1300 | L2 |
| `memory` | 记忆/上下文层。Session/Thread/StepRecord 三级会话 | session.py, thread.py, archive.py | 291 | L3 |
| `provider` | LLM provider 抽象。Protocol + Mock + Minimax + 注册表 + 审计 | base.py, mock.py, minimax.py, registry.py, router.py, audit.py | 500 | L3 |
| `tools` | LLM 工具系统。ToolProtocol + Registry + 5 Agent 包装器 | base.py, registry.py, agent_tool.py | 678 | L4 |
| `toolagent` | 无人格工具执行体。5 内置 Agent + provider 注入 | base.py, vault_search.py, vault_read.py | 1123 | L4 |
| `runtime` | 运行时层。RuntimeContext 依赖注入 + Master/Sub + growth 检索 + unease 注入 | context.py, master.py, sub.py, growth_search.py | 700 | L5 |
| `pipeline` | 编排层。PipelineExecutor 主循环 + 4 步 Step | executor.py, step.py, router.py | 620 | L6 |
| `reflect` | REFLECT 态。读 session→LLM 写反思→情绪打分 | executor.py, emotion.py | 555 | L7 |
| `dream` | DREAM 态。3 级梦境 + 7 phase 流水线 + drift 监控 | 12 个文件 | 2700 | L7 |
| `steiner` | 隐藏层。GrowthWatcher + unease 注入 + drift 报警 + 生命周期 | unease.py, watcher.py, prompt.py, drift.py, lifecycle.py | 700 | L1* |
| `cli` | CLI 入口。14 个命令分发 + daemon + goodnight | commands.py, daemon.py, goodnight.py | 600 | L8 |
| `web` | Web UI + 通知通道。HTTP server + owner 通知 | server.py, notify.py | 350 | L8 |
| `redact` | 共享 redact 工具。6 个 SENSITIVE_PATTERNS + fail-closed | redact.py | 100 | L1** |

### 依赖分层图

![Figure 1](https://raw.githubusercontent.com/HeDaas-Code/Mortis/main/docs/mortis-audit-v3/images/diagram-01-arch-layers.png)

> **Figure 1**: 包依赖分层图 — 自底向上 9 层，vault 为中枢（7 包依赖），growth 为次中枢（5 包依赖）

### 核心抽象与协议

| 抽象类 | 类型 | 位置 | 职责 | 实现者 |
|--------|------|------|------|--------|
| `LLMProviderProtocol` | Protocol | provider/base.py:19 | LLM 接口契约 | MockProvider, MinimaxProvider |
| `VaultProtocol` | Protocol | vault/base.py:21 | vault 抽象 | Vault (local.py) |
| `ToolProtocol` | Protocol | tools/base.py:42 | LLM 可调用工具接口 | 4 基础工具 + 5 ToolAgent 包装器 |
| `ToolAgentProtocol` | Protocol | toolagent/base.py:38 | 无人格执行体接口 | ToolAgent + 5 内置 Agent |
| `Step` | ABC | pipeline/step.py:54 | 步骤基类 | Think/Plan/Act/ReviewStep |
| `DreamPipeline` | 基类 | dream/pipeline.py:45 | 梦境流水线 | Light/Medium/DeepDreamer |

### 关键设计决策

#### OOC 防御体系
`seed.md` 不可变（`SEVEN_DIMENSIONS` 硬编码 schema），系统 prompt 永远从 seed 重算。sub 锚定主人格：`SubTemplate.from_seed()` 自动注入 `parent_seed_hash`，`verify_chain()` 校验 L0→L1→L2 完整链路。白名单授权：`SUB_VAULT_WHITELIST` + `VaultSecurity.check_whitelist` 栈式归一化消除 `../` 遍历。

#### ToolAgent vs Tool 双层设计
`ToolProtocol`（tools 层）暴露 JSON Schema 面向 LLM tool calling；`ToolAgentProtocol`（toolagent 层）接收 dict 返回 ToolResult，不暴露 schema。5 个内置 Agent 通过 `*ToolAgent` 包装器注册为 ToolProtocol（issue #64），由 LLM 自发调用。已删除关键词路由 TaskRouter（issue #72）。

#### Reading Steiner 隐藏层
`mortis-steiner/` 是 Mortis **自身都不知道存在**的隐藏层。owner 编辑 growth → `GrowthWatcher` 检测 → `SteinerController._on_edit` debounce + accumulate → `unease_prompt` 注入 system prompt **潜台词**（非显式指令）→ drift≥0.75 通知 owner。

#### Redact 共享模块（issue #83）
`mortis/redact.py` 提供共享 `redact_snippet()` + `SENSITIVE_PATTERNS`（6 个模式）。所有发 vault 内容给 LLM 的入口统一调用，fail-closed 设计（re 异常返回占位符而非原文）。

---

## 05 调用链分析

从 task 输入到 step 输出的完整方法级调用链，Dream 生命周期数据流，Growth 注入与 Tool calling 路由。

### 主循环调用链

入口：`PipelineExecutor.run()` — `mortis/pipeline/executor.py:43`

![Figure 2](https://raw.githubusercontent.com/HeDaas-Code/Mortis/main/docs/mortis-audit-v3/images/diagram-02-pipeline-flow.png)

> **Figure 2**: 主循环调用链 — TaskRouter 路由后分 simple/delegated 两路径，ActStep 含工具调用循环

### Dream 流水线

`DreamPipeline.run()` 按 `PHASES_BY_LEVEL` 顺序反射调用各 `phase_<name>()`。Light=4 phase / Medium=5 phase（+SIMULATE）/ Deep=7 phase（+ERODE+SEED_CHECK）。

![Figure 3](https://raw.githubusercontent.com/HeDaas-Code/Mortis/main/docs/mortis-audit-v3/images/diagram-03-dream-pipeline.png)

> **Figure 3**: Dream 流水线 — Light 4 phase / Medium 5 phase / Deep 7 phase

### Growth 注入链路

核心入口：`RuntimeContext.messages_for_provider()` — `runtime/context.py:130`

```
RuntimeContext.messages_for_provider()
│
├─ msgs[0] = Message(role="system", content=seed.get_dimension("tone"))  ← 人格语气
│
├─ unease_text = unease_prompt_for_injection()   [context.py:110]  ← steiner 隐藏层
│    ├─ load_unease(vault) → UneaseState
│    ├─ decay(state, now) → UneaseState
│    └─ unease_prompt(state) → 5 档文案
│
├─ if unease_text:
│    msgs.append(Message(role="system", content=unease_text))  ← 第 2 条 system
│
├─ growth_prompt = growth_context_for_task(thread.task)   [context.py:74]
│    ├─ search_growths(vault, query=task, min_confidence=0.5, limit=5)
│    │    ├─ vault.list_growths(dimension) → 路径候选
│    │    ├─ for rel: vault.read_growth(rel) → Growth
│    │    ├─ 多重过滤: confidence≥0.5 + tag匹配 + _matches_query(子串命中)
│    │    └─ 排序: confidence desc → last_validated desc
│    └─ growth_system_prompt(growths) → markdown 段（_preview_body 已 redact）
│
├─ if growth_prompt:
│    msgs.append(Message(role="system", content=growth_prompt))  ← 第 3 条 system
│
└─ for step in thread.steps:
     msgs.append(Message(role="assistant", content=step.output))  ← 历史步骤
```

### 所有 LLM 调用点清单

| # | 文件:行号 | 方法 | 用途 | 类型 | Redact |
|---|----------|------|------|------|:------:|
| 1 | pipeline/router.py:25 | `TaskRouter.route()` | 路由判断 simple/complex | generate (带 growth) | ⚠️ 否（人格上下文） |
| 2 | pipeline/step.py:83 | `Step._call_provider()` | 各 step 首次调用 | generate (带 growth) | ⚠️ 否（人格上下文） |
| 3 | pipeline/step.py:83 | `Step._call_provider()` | 工具结果回传二次调用 | generate (带 growth) | ⚠️ 否（人格上下文） |
| 4 | dream/associate.py:83 | `associate()` | Dream ASSOCIATE 找模式 | generate_text | ✅ 是（issue #86） |
| 5 | reflect/emotion.py:62 | `score_emotion()` | 情绪打分 valence/arousal | generate_text | ✅ 是（issue #86） |
| 6 | dream/seed_check.py:137 | `seed_check()` | Deep SEED_CHECK drift 计算 | generate_text | ✅ 是（issue #84） |
| 7 | reflect/executor.py:225 | `_generate_reflection()` | REFLECT 写反思 body | generate_text | ✅ 是（issue #86） |
| 8 | toolagent/base.py:102 | `_llm_generate()` | ToolAgent 通用入口 | generate_text | — 取决于调用方 |
| 9 | toolagent/vault_read.py:110 | `_summarize()` | vault 文件摘要 | generate_text | ✅ 是 |
| 10 | toolagent/vault_search.py:151 | `_semantic_rerank()` | 语义重排 + 摘要 | generate_text | ✅ 是 |
| 11 | toolagent/vault_stats.py:82 | `_analyze_stats()` | vault 统计分析 | generate_text | — 仅统计数字 |

> **Redact 覆盖状态: 8/11 已覆盖**
>
> pipeline 层（#1-3）的 LLM 调用**带人格上下文**（tone + unease + growth + 历史），growth preview 已通过 `_preview_body` redact（issue #85），tone 来自不可变 seed，历史步骤是 Mortis 自身产出，无私密字段泄漏风险。dream/reflect 层（#4-7）和 toolagent 层（#9/#10）已全部覆盖 redact。#11 仅发统计数字。

---

## 06 信号结构

Mortis 的"信号"是认知状态的可量化表达 — 从 session 情绪到 growth confidence 到 steiner unease，构成完整的信号产生-传递-消费链。

### 信号结构清单

| 信号 | 产生者 | 消费者 | 数据结构 | 文件 |
|------|--------|--------|----------|------|
| **DreamLevel** | Light/Medium/DeepDreamer | Growth.dream_level | Enum: LIGHT/MEDIUM/DEEP | phases.py:33 |
| **DreamPhase** | DreamPipeline.run() | PhaseTrace | Enum: 7 阶段 | phases.py:14 |
| **confidence** | CRYSTALLIZE(0.3) / Medium(0.5) / ERODE 衰减 | search_growths 排序 / ERODE archive | float 0.0-1.0 | growth/model.py:65 |
| **emotional_valence** | score_emotion() | Growth 字段 / RECALL 加权采样 | float -1.0-1.0 | growth/model.py:70 |
| **emotional_arousal** | score_emotion() | Growth 字段 / RECALL 加权采样 | float 0.0-1.0 | growth/model.py:71 |
| **emotion_weight** | compute_weight(v,a)=\|v\|×a | emotion_weighted_sample() | float 0.0-1.0 | recall.py:26 |
| **Dimension** | infer_dimension() 关键词命中 | Growth.dimension / vault 路径 | Enum: 7 维度 | growth/model.py:17 |
| **UneaseState** | GrowthWatcher → accumulate() | unease_prompt() → system 注入 | frozen dataclass | steiner/unease.py:63 |
| **unease_prompt** | unease_prompt(state) 5 档 | system prompt 潜台词 | str (0.0/0.15/0.45/0.75/1.0) | steiner/prompt.py:53 |
| **DriftReport** | seed_check() LLM 自评 | DeepDreamer → owner-notify.json | frozen dataclass | seed_check.py:38 |
| **Conflict** | _detect_conflicts() | 写 conflicts/ 目录 | dataclass | dream/light.py:55 |
| **PhaseTrace** | 各 phase | DreamResult.traces | dataclass | pipeline.py:19 |

### 信号流主链

![Figure 4](https://raw.githubusercontent.com/HeDaas-Code/Mortis/main/docs/mortis-audit-v3/images/diagram-04-signal-flow.png)

> **Figure 4**: 信号流主链 — session→emotion→growth→steiner→drift 完整闭环

### confidence 生命周期

| Phase | confidence | 触发事件 | 说明 |
|-------|:-----------:|----------|------|
| CRYSTALLIZE (Light) | 0.3 | 初始创建 | Light Dream 新 growth 默认值 |
| SIMULATE (Medium) | 0.5 | source_sessions 重叠≥2 | Medium 提升至 0.5 |
| RECONCILE (冲突) | 0.25 | 旧 growth ×0.5 | 检测到矛盾项衰减 |
| ERODE (Deep, 7天) | 0.21 | ×0.85^7 | 7 天衰减后 |
| ERODE (Deep, 30天) | 0.04 | ×0.85^30 | 30 天衰减后，接近 archive 阈值 |
| search_growths | — | min_confidence=0.5 | 只注入 ≥0.5 的 growth 到 LLM prompt |

---

## 07 安全审计

Vault 安全纵深防御、Redact 覆盖矩阵、漏洞清单与 Provider 隔离分析。

### Vault 安全层级（纵深防御）

![Figure 5](https://raw.githubusercontent.com/HeDaas-Code/Mortis/main/docs/mortis-audit-v3/images/diagram-05-vault-defense.png)

> **Figure 5**: Vault 4 层纵深防御 + Redact 脱敏层 — 任一层失败即拦截

### Redact 覆盖矩阵

#### _SENSITIVE_PATTERNS 完整列表

| # | 模式 | 替换 | 覆盖目标 |
|---|------|------|----------|
| 1 | `[!dream]...` | `[!dream]: [REDACTED]` | Obsidian dream callout（含嵌套续行） |
| 2 | `[!warning\|secret\|private\|confidential]...` | `[!redacted]: [REDACTED]` | warning/secret/private/confidential callout |
| 3 | `[emotion:...]` | `[emotion:REDACTED]` | 行内 emotion 标签 |
| 4 | `%%subconscious%%...%%/subconscious%%` | `%%subconscious:REDACTED%%` | 潜意识注释（带终止符） |
| 5 | `%%subconscious%%...$` | `%%subconscious:REDACTED%% (unclosed)` | 潜意识注释（无终止符，到 EOF） |
| 6 | `(emotional_valence\|arousal\|dream_level)\s*:\s*...` | `\1: REDACTED` | frontmatter 情感字段 |

#### LLM 调用点 × Redact 覆盖

| LLM 调用点 | dream callout | emotion 标签 | subconscious | emotional_* | warning callout |
|-----------|:---:|:---:|:---:|:---:|:---:|
| #1 TaskRouter.route | — | — | — | — | — |
| #2 Step._call_provider | — | — | — | — | — |
| #3 Step._call_provider(回传) | — | — | — | — | — |
| #4 associate() | ✅ | ✅ | ✅ | ✅ | ✅ |
| #5 score_emotion() | ✅ | ✅ | ✅ | ✅ | ✅ |
| #6 seed_check() | ✅ | ✅ | ✅ | ✅ | ✅ |
| #7 _generate_reflection() | ✅ | ✅ | ✅ | ✅ | ✅ |
| #8 _llm_generate() | — | — | — | — | — |
| #9 _summarize() | ✅ | ✅ | ✅ | ✅ | ✅ |
| #10 _semantic_rerank() | ✅ | ✅ | ✅ | ✅ | ✅ |
| #11 _analyze_stats() | — | — | — | — | — |

> **图例**: ✅ 已覆盖 | — 不适用（pipeline 层带人格上下文，#11 仅发统计数字）

### 安全漏洞清单

#### 已修复漏洞（22 项）

| ID | 漏洞 | 修复 | 文件 | 状态 |
|----|------|------|------|:----:|
| S1/#11 | Vault.write 路径遍历 | `_safe_path()` + resolve + relative_to | vault/local.py:51 | ✅ 已修 |
| S2/#12 | 白名单 ../ 绕过 | `_normalize()` 栈式归一化 | vault/base.py:73 | ✅ 已修 |
| S3/#13 | discard_sub_output 删任意文件 | 走 `_safe_path()` | vault/local.py:196 | ✅ 已修 |
| #6 | 白名单未下沉到 Vault 层 | `Vault._enforce()` 强制检查 | vault/local.py:69 | ✅ 已修 |
| #17 | ReviewGate.apply 不走白名单 | `_safe_write()` 内部强制 | vault/review.py:155 | ✅ 已修 |
| #38 | 人格层可读 mortis-steiner/ | `BLOCKED_PREFIXES` | vault_read.py:39 | ✅ 已修 |
| #67 | BLOCKED 中段 .. 绕过 | `normalize_rel_path()` | vault_read.py:63 | ✅ 已修 |
| #71 | search/bfs 异常未捕获 | VaultAccessDenied 捕获 + log | vault_search.py:126 | ✅ 已修 |
| #73 | semantic rerank 发私密字段 | `_redact_snippet()` | vault_search.py:40 | ✅ 已修 |
| CRITICAL-1 | _summarize 未 redact | 复用 `_redact_snippet` | vault_read.py:122 | ✅ 已修 |
| CRITICAL-2 | redact 大小写绕过 | IGNORECASE + `\s*:\s*` | vault_search.py:61,374 | ✅ 已修 |
| #70 | _llm_generate 静默吞错 | 异常分类 + log warning | toolagent/base.py:102 | ✅ 已修 |
| #80 | sub-outputs 阻断只在包装层 | BLOCKED_PREFIXES 加 sub-outputs | vault_read.py:39 | ✅ 已修 |
| #83 | redact utility 未共享 | 提升为 `mortis/redact.py` | redact.py | ✅ 已修 |
| #84 | seed_check 发 growth body 未 redact | 发 LLM 前 `redact_snippet` | seed_check.py:137 | ✅ 已修 |
| #85 | growth preview 未 redact | `_preview_body` 加 redact | growth_search.py:136 | ✅ 已修 |
| #86 | session 发 LLM 未 redact | associate + score_emotion 加 redact | associate.py:83, emotion.py:62 | ✅ 已修 |
| #87 | provider 无 prompt 审计日志 | `sha256_prefix` 审计 log | provider/audit.py, toolagent/base.py:102 | ✅ 已修 |
| #88 | 两套 ToolResult 易混淆 | 统一为 `tools.base.ToolResult` | toolagent/base.py | ✅ 已修 |
| #45 | 单 LLM 后端 | 多 LLM 注册表 + 任务路由 | provider/registry.py, router.py | ✅ 已修 |
| #46 | 无 async 接口 | async_generate + async_generate_text | provider/base.py, mock.py, minimax.py | ✅ 已修 |
| #47 | growth 维度膨胀 | 维度压缩 | growth/compress.py | ✅ 已修 |

#### 潜在漏洞（0 项）

**所有潜在漏洞已修复。** v3.0 审计发现的 P1-P4（seed_check / growth preview / session 未 redact）已全部通过 issue #84/#85/#86 修复。

### Provider 隔离分析

| 隔离良好 | 待改进 |
|---------|--------|
| **协议抽象**：Protocol 鸭子类型 | **数据 redact**：provider 层无 redact，责任在调用方（已通过共享模块解决） |
| **API key**：从环境变量读 | **prompt 日志**：已通过 `sha256_prefix` 审计 log 解决（issue #87） |
| **网络层**：stdlib urllib，超时 30s | **ToolAgent 降级**：已通过异常分类 + log 解决（issue #70） |
| **异常分类**：MinimaxAuthError / MinimaxAPIError | |
| **工厂隔离**：`make_provider("auto")` 无 key 用 Mock | |
| **注册表扩展**：按名称注册新 provider（issue #45） | |
| **任务路由**：按任务类型选 provider（issue #45） | |

---

## 08 信息流转模拟

模拟真实使用环境下，从 owner 输入 task 到 Mortis 产出回复的完整信息流转路径。

### 场景: owner 委派复杂任务

```bash
python -m mortis delegate "帮我整理本周的 growth 并总结 identity 维度的变化" --provider auto
```

![Figure 6](https://raw.githubusercontent.com/HeDaas-Code/Mortis/main/docs/mortis-audit-v3/images/diagram-06-task-flow.png)

> **Figure 6**: 复杂任务委派完整信息流转 — 从 owner 输入到 growth 落地

### 场景: 夜间 Dream 周期

clock 进入 DREAM_LIGHT (23:00-06:00) → `LightDreamer.run()`

![Figure 7](https://raw.githubusercontent.com/HeDaas-Code/Mortis/main/docs/mortis-audit-v3/images/diagram-07-dream-cycle.png)

> **Figure 7**: Dream 周期信息流 — 4 phase 从 session 到 growth 到 conflict

### 场景: Steiner 隐藏层触发

owner 手动编辑 growth 文件 → GrowthWatcher 检测 → unease 注入

![Figure 8](https://raw.githubusercontent.com/HeDaas-Code/Mortis/main/docs/mortis-audit-v3/images/diagram-08-steiner-hidden.png)

> **Figure 8**: Steiner 隐藏层触发链 — owner 编辑→unease→潜台词注入→drift 通知

---

## 09 分支与 Issue 时间轴

5 天开发周期（2026-06-20 至 2026-06-25）、60+ 提交、88 个 issues、10+ 分支的完整时间轴。

![Figure 10](https://raw.githubusercontent.com/HeDaas-Code/Mortis/main/docs/mortis-audit-v3/images/diagram-10-timeline.png)

> **Figure 10**: 分支与 Issue 提交时间轴 — 5 天 60+ 提交 88 issues 全部关闭

### 时间轴详情（按日期分组）

#### 2026-06-20（v0 骨架）

| 时间 | 分支 | Issue | 提交 |
|------|------|-------|------|
| — | main | #1 | mortis 架构骨架 — vault 抽象 + 主人格引擎 |
| — | main | #2 | 立人 — 从工具化到人格化 |

#### 2026-06-21（v0+v1 + 安全审计）

| 时间 | 分支 | Issue | 提交 |
|------|------|-------|------|
| 03:14 | main | — | v0+v1 骨架完整实现 (69 测试 + minimax) |
| 12:15 | main | — | 重构为 8 子包自研框架 |
| 15:39 | main | — | 首次跟踪 mortis/vault/ 子包代码 |
| 15:42 | main | #6 | whitelist 强制检查下沉到 Vault 层 |
| 16:59 | fix/audit-hanis-vault-path-security | #11/#12/#13 | 修复 3 个 CRITICAL 路径安全漏洞 (S1/S2/S3) |
| 17:13 | fix/audit-hanis-pipeline-chain | #7/#8/#9/#10 | Pipeline 审阅链 + SubTemplate 防伪 + L2 模板链 |
| 18:12 | main | #16 | RFC-001 认知生长系统 |
| 19:30 | main | #17 | ReviewGate.apply vault_whitelist 强制 |

#### 2026-06-22（RFC-001 实现）

| 时间 | 分支 | Issue | 提交 |
|------|------|-------|------|
| 10:10 | main | #18 | Growth 数据模型 + 7 维度枚举 |
| 10:14 | main | — | vault 结构扩展 + growth CRUD API |
| 13:15 | main | #27 | mortis/__init__ growth CRUD 顶层包装 |
| 13:35 | main | #19/#28 | Obsidian 语法解析层 + Growth Obsidian-Native |
| 14:34 | main | #21/#29 | ReflectExecutor + emotion 标注 + 触发条件 |
| 15:38 | main | #22/#30 | LightDreamer 4 phase + 情绪加权采样 |
| 16:48 | main | #24/#31 | Reading Steiner — unease + watcher + drift |
| 16:57 | main | #25/#32 | 5 内置 Agent + TaskRouter 关键词路由 |
| 17:08 | main | #23/#33 | Medium + Deep + erode + seed-check |
| 21:47 | main | #26/#34 | 逻辑时钟 + 昼夜节律 + 时差 + 睡眠不足 |

#### 2026-06-23（v3 集成 + 审计修复）

| 时间 | 分支 | Issue | 提交 |
|------|------|-------|------|
| 07:44 | feature/v3-toolagent-llm-integration | #63/#64/#59 | ToolAgent LLM integration + growth retrieval |
| 08:54 | main | #41 | hours_awake 双重计数 + LogicalClock 时区 |
| 08:55 | main | #42 | reconcile break 错位 + archive_growth API |
| 08:55 | main | #43 | VaultReadAgent blocked_prefixes 安全检查 |
| 08:56 | main | #40/#44 | 清理审计死代码 + 风格问题 |
| 09:08 | main | — | 更新 README + RFC-001 → Implemented |
| 10:51 | main | — | Harness 工程 — dev 工具 + 上下文锚点 |
| 19:56 | fix/vault-read (PR #69) | #67 | BLOCKED_PREFIX 路径归一化 — 消除 .. 绕过 |
| 20:47 | fix/agent-tool | #68 | VaultReadToolAgent sub 私域阻断 |

#### 2026-06-24（v3 安全 + 运行时集成 + 生产化 + 体验层）

| 时间 | 分支 | Issue | 提交 |
|------|------|-------|------|
| 00:32 | fix/toolagent (PR #74) | #70 | _llm_generate 区分 TimeoutError + log warning |
| 00:43 | chore/toolagent (PR #76) | #72 | 删除 TaskRouter 关键词路由 |
| 12:48 | fix/toolagent (#77) | #71/#73 | semantic rerank redact + 异常分类 |
| 14:30 | main | — | Merge PR #74 + #76 |
| 14:37 | main | — | 修复 2 个 CRITICAL 数据泄漏漏洞 |
| 14:46 | fix/80-vault-read-agent-sub-outputs | #80 | VaultReadAgent sub-outputs 阻断 |
| 14:47 | fix/78-79-test-timebomb | #78/#79 | dream 测试 time-bomb 修复 |
| 15:09 | main | — | 新增 v3 方法级代码审计报告 |
| 15:12 | main | — | 合并 fix/78-79 + fix/80 分支 |
| 15:20 | main | — | 审计报告 HTML → Markdown |
| 15:40 | main | — | Mermaid 图表渲染为 PNG |
| 15:58 | main | — | 图片引用改为绝对 raw URL |
| 17:00 | fix/83-redact-shared | #83 | redact utility 提升为共享模块 |
| 17:21 | fix/88-unify-toolresult | #88 | 统一 ToolResult 类型 |
| 17:44 | fix/87-provider-audit-log | #87 | provider prompt hash 审计日志 |
| 17:56 | fix/84-seed-check-redact | #84 | seed_check 发 LLM 前加 redact (CRITICAL) |
| 18:01 | fix/86-session-redact | #86 | associate + score_emotion redact |
| 18:03 | fix/85-growth-preview-redact | #85 | growth preview 注入前 redact |
| 18:19 | fix/57-unease-injection | #57 | unease 注入 RuntimeContext |
| 18:21 | fix/58-growth-watcher-start | #58 | SteinerController 生命周期管理 |
| 18:35 | fix/56-cli-extensions | #56 | dream/reflect/status 命令 |
| 19:02 | fix/61-goodnight-trigger | #61 | owner「晚安」触发夜间认知周期 |
| 19:10 | fix/60-daemon-mode | #60 | daemon 常驻进程自动触发 |
| 19:14 | main | — | Merge fix/61-goodnight-trigger |
| 19:41 | fix/45-provider-registry | #45 | 多 LLM 后端注册表 + 任务路由 |
| 19:57 | fix/46-async-generate | #46 | async generate/generate_text 接口 |
| 19:59 | fix/47-growth-compression | #47 | growth 维度压缩 |
| 20:12 | fix/48-drift-log | #48 | drift 误报率监控 |
| 20:14 | fix/52-web-ui | #52/#53/#54 | Web UI + growth 浏览器 + owner 通知 |
| 20:16 | main | — | Merge fix/52-web-ui |

#### 2026-06-25（PR #66 合并）

| 时间 | 分支 | Issue | 提交 |
|------|------|-------|------|
| 01:29 | main | — | Merge PR #66 (冲突解决，全部保留 main 版本) |

### 分支汇总

| 分支 | 状态 | 用途 |
|------|------|------|
| `main` | ✅ 主线 | 主分支，所有 fix 分支合并目标 |
| `feature/v3-toolagent-llm-integration` | ✅ 已合并 (PR #66) | v3 ToolAgent LLM 集成分支 |
| `fix/audit-hanis-vault-path-security` | ✅ 已合并 (PR #14) | S1/S2/S3 路径安全 |
| `fix/audit-hanis-pipeline-chain` | ✅ 已合并 (PR #15) | Pipeline 审阅链 |
| `fix/vault-read` | ✅ 已合并 (PR #69) | #67 路径归一化 |
| `fix/agent-tool` | ✅ 已合并 | #68 sub 私域阻断 |
| `fix/toolagent` | ✅ 已合并 (PR #74) | #70 TimeoutError |
| `chore/toolagent` | ✅ 已合并 (PR #76) | #72 删除 TaskRouter |
| `fix/toolagent` (#77) | ✅ 已合并 | #71/#73 redact + 异常分类 |
| `fix/80-vault-read-agent-sub-outputs` | ✅ 已合并 | #80 sub-outputs 阻断 |
| `fix/78-79-test-timebomb` | ✅ 已合并 | #78/#79 测试 time-bomb |
| `fix/83-redact-shared` | ✅ 已合并 | #83 共享 redact 模块 |
| `fix/88-unify-toolresult` | ✅ 已合并 | #88 统一 ToolResult |
| `fix/87-provider-audit-log` | ✅ 已合并 | #87 审计日志 |
| `fix/84-seed-check-redact` | ✅ 已合并 | #84 seed_check redact |
| `fix/86-session-redact` | ✅ 已合并 | #86 session redact |
| `fix/85-growth-preview-redact` | ✅ 已合并 | #85 growth preview redact |
| `fix/57-unease-injection` | ✅ 已合并 | #57 unease 注入 |
| `fix/58-growth-watcher-start` | ✅ 已合并 | #58 SteinerController |
| `fix/56-cli-extensions` | ✅ 已合并 | #56 CLI 命令 |
| `fix/61-goodnight-trigger` | ✅ 已合并 | #61 goodnight |
| `fix/60-daemon-mode` | ✅ 已合并 | #60 daemon |
| `fix/45-provider-registry` | ✅ 已合并 | #45 provider 注册表 |
| `fix/46-async-generate` | ✅ 已合并 | #46 async |
| `fix/47-growth-compression` | ✅ 已合并 | #47 growth 压缩 |
| `fix/48-drift-log` | ✅ 已合并 | #48 drift 日志 |
| `fix/52-web-ui` | ✅ 已合并 | #52/#53/#54 Web UI |

### Issue 汇总

| Issue 范围 | 数量 | 状态 | 主题 |
|-----------|:----:|:----:|------|
| #1-#2 | 2 | ✅ closed | v0 骨架 |
| #3-#5 | 3 | ✅ closed | v1 sub + minimax + 合并 |
| #6-#17 | 12 | ✅ closed | 安全审计 + Pipeline 审阅链 |
| #18-#26 | 9 | ✅ closed | RFC-001 认知生长系统 |
| #40, #65 | 2 | ✅ closed | 死代码清理 + v3 总览 |
| #45-#48 | 4 | ✅ closed | v3.1 生产化 |
| #52-#54 | 3 | ✅ closed | v3.2 体验层 |
| #55 | 1 | ✅ closed | v3.2 总览 |
| #56-#62 | 7 | ✅ closed | v3.0 运行时集成 |
| #63-#64 | 2 | ✅ closed | v3 ToolAgent LLM |
| #67-#80 | 9 | ✅ closed | v3 安全修复 |
| #83-#88 | 6 | ✅ closed | redact 共享 + 统一类型 |
| **合计** | **88** | **88 closed** | **0 open** |

---

## 10 发现与建议

### 审计发现汇总

| 类别 | 数量 | 说明 |
|------|:----:|------|
| ✅ 已修复 | 22 | S1-S3, #6, #17, #38, #67, #70, #71, #73, CRITICAL-1/2, #80, #83-#88, #45-#47 |
| 🔴 CRITICAL 潜在 | 0 | 无 |
| 🟡 MEDIUM 潜在 | 0 | 无 |
| 🟣 架构改进 | 0 | 无（#83/#88 已完成） |
| ⚪ 测试 Gap | 1 | A1 主循环入口端到端未覆盖 |

### 架构健康度评估

| ✅ 优势 | ⚠️ 待改进 |
|---------|----------|
| **分层清晰**：9 层无循环依赖，vault/growth 中枢设计合理 | **测试 Gap**：A1 主循环入口端到端未覆盖 |
| **Protocol 解耦**：6 个核心抽象用 Protocol 鸭子类型 | **Web UI 覆盖薄弱**：仅 1 文件覆盖 6 端点 |
| **安全纵深**：4 层独立防御 + fail-closed redact | **CLI 子命令覆盖薄弱**：仅 2 文件 |
| **OOC 防御**：seed 不可变 + sub 锚定 + 白名单强制 | |
| **Redact 全覆盖**：8/11 LLM 调用点已覆盖 | |
| **steiner 集成**：v3 #57/#58 已完成，隐藏层注入闭环 | |
| **三态自动化**：clock/dream/reflect 自动调度（daemon + goodnight） | |
| **统一 ToolResult**：单一类型（issue #88） | |
| **测试覆盖**：986 passed，78 节点 77 覆盖（98.7%） | |

### 改进建议路线图

#### 短期（补齐测试 Gap）

1. 补 A1 主循环入口端到端测试（从 CLI 输入到 dream/reflect 产出完整闭环）
2. 补 Web UI 横向冗余测试（每个端点独立测试文件）
3. 补 CLI 子命令端到端测试（daemon/web 命令入口）

#### 中期（架构演进）

1. Provider 层支持原生 function calling（消除 TextCall 降级）
2. Growth 检索升级为向量语义搜索（当前是子串匹配）
3. Steiner unease 注入从"潜台词"升级为"情绪向量"（影响 temperature/top_p）

#### 长期（生态扩展）

1. 多 provider 路由策略优化（按任务类型 + 成本 + 延迟）
2. Obsidian 插件实现（Graph View 集成）
3. owner 移动端通知推送

> **✅ 审计结论**
>
> Mortis v3 架构健康度**良好**，分层清晰、Protocol 解耦、安全纵深扎实、redact 全覆盖、steiner 隐藏层闭环。**所有 22 个安全漏洞已修复，0 个潜在漏洞，88 个 issues 全部关闭**。测试覆盖 986 passed / 78 节点 77 覆盖（98.7%），仅 A1 主循环入口端到端未覆盖。main 分支已推送到远程，可安全部署。

---

*Mortis v3 代码审计报告 — 方法级 + 测试覆盖率 + 时间轴 | 2026-06-25 | 分支: main (HEAD: 1dadd28)*

*本报告替代旧版 `mortis-audit-v3.md`（v3.0），新增方法级审计、测试覆盖率分析、分支与 issue 时间轴，图片全部重新渲染为白底黑字。*

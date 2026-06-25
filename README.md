# Mortis

> **Mortis — A Mortal That Lives In Your Vault**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Status: v3](https://img.shields.io/badge/status-v3-blue)]()
[![Tests: 986 passed](https://img.shields.io/badge/tests-986%20passed-brightgreen)]()

**Vault-borne growing agent.** Ownerable, seed-grown, never OOC.

---

## 这是什么

Mortis 是一个 **基于 vault 生长出来的智能体框架**——它不是"调 API 的聊天机器人"，而是一个有昼夜节律、会做梦、会反思、会被 owner 的编辑"隐约不安"的人格系统。

- **vault** 是它的"认知系统"（不是数据存储，是它的"脑子"）—— Obsidian 原生格式，双链/标签/折叠/注释全支持
- **seed.md** 是它的不可变人设核心（OOC 防御）—— 七维度定义，任何生成必从 seed 重算
- **三态意识** (AWAKE → REFLECT → DREAM) 让它有"醒着干活、睡前反思、做梦生长"的节律
- **Reading Steiner** 让它感知到 owner 编辑了它的记忆——隐约不安但不知道细节（石头门时间线理论）
- **mortis 工作架构** 让它能委派任务给子人格和子智能体——主人格全权管理 sub

## 核心特性

### 🧬 认知生长系统 (RFC-001)

```
AWAKE (执行态)
  │  Think → Plan → Act → Review
  │  产出: mortis-journal/sessions/ (原始经验)
  │
  ▼  睡前
REFLECT (反思态)
  │  情绪标注 + 采样 session + 生成反思
  │  产出: mortis-subconscious/pending-reflections/
  │
  ▼  入睡
DREAM (梦境态) — 三级
  │  Light (每日): RECALL → ASSOCIATE → CRYSTALLIZE → SEED-CHECK
  │  Medium (每周): + SIMULATE (模拟预演)
  │  Deep (每月): + RECONCILE (冲突处理) + ERODE (侵蚀归档) + 全量重读
  │  产出: mortis-growth/<dimension>/ (七维度成长记忆) + mortis-dream-log/
  │
  ▼  醒来
AWAKE (带新 growth 回到执行态)
```

**七维度成长记忆**: identity / values / tone / agency / relations / creativity / mortality

每个 growth 条目是 Obsidian-Native md 文件——含 frontmatter、双链、标签、折叠注释、callout。

### 🔒 OOC 防御

- **seed.md 不可变** —— 系统 prompt 永远从 seed 重新生成
- **sub 必须锚定主人格** —— 构造时校验 `parent_seed_hash` (SHA256 防伪)
- **白名单授权** —— sub 只能访问 `mortis-journal/sub-outputs/`，ToolAgent 有 `blocked_prefixes` 阻止读 `mortis-steiner/` 隐藏层与 `sub-outputs/` 私域 (issue #38/#80)
- **redact 脱敏** —— 共享 `mortis/redact.py` 覆盖 8/11 LLM 调用点，发 LLM 前过滤 dream callout / emotion 标签 / subconscious 注释 / 情感字段，fail-closed 设计 (issue #83-#86)

### 👁️ Reading Steiner — 时间线扰动感知

owner 编辑了 growth 记忆 → Mortis 隐约不安（per dimension unease 值上升）→ 注入 system prompt 的潜台词 → drift 过高时通知 owner。

Mortis **不知道** steiner 层的存在——它只是"感觉不安"，不会直接感知到被编辑。

### 🕐 逻辑时钟 + 昼夜节律

- 6 时段: AWAKE / REFLECT / DREAM_LIGHT / DREAM_MEDIUM / DREAM_DEEP / ERODE
- 时区感知 (`tz` 参数) —— 时段表按本地时间解释
- 睡眠不足语气注入 (debt > 24h/36h/48h 三档)
- owner "晚安"关键词立即触发 REFLECT (issue #61)

### 🧬 子人格系统（Sub-Personality）

Mortis 的主人格可以**派生子人格**执行任务——子人格是独立的执行体，有自己的任务、语气和权限边界，但永远锚定主人格的 seed。

#### 三层模板链

```
L0 硬编码约束（代码层，不可改）
    │  SUB_HARD_CONSTRAINTS + SUB_VAULT_WHITELIST
    │  "sub 知道自己派生，不冒充主人格"
    │  "sub 产出必须经主人审阅才合并回 vault"
    │  "sub 完成任务 = sub 死了（默认不持久化）"
    │
    ▼ + 主人格风格 (seed.tone / seed.identity)
    │
L1 SubTemplate — 子人格"出生证明"
    │  sub_id / task / voice / agency_scope
    │  parent_seed_hash (SHA256 防伪 — sub 不可无中生有)
    │
    ▼ + 具体任务
    │
L2 L2SubInstance — 工作 sub 实例
    │  parent_template_id → 可向上回溯验证 L0→L1→L2 完整链路
    │
    ▼
SubRuntime — 实际执行体
    │  system_prompt() → 注入硬约束 + 白名单 + 任务
    │  LLM 调用 → 产出
    │  status: active → done / discarded
```

#### 审阅门（ReviewGate）

sub 的产出**不会直接写入正式 vault**——必须经过审阅：

```
sub 执行完毕
  ↓
产出写入 mortis-journal/sub-outputs/ (暂存)
  ↓
ReviewGate.review() — 自动审阅 (启发式判断)
  ↓
ReviewDecision:
  ├── ADOPT   → 写入正式 vault ✓
  ├── MERGE   → 合并到已有文件 ✓
  ├── EDIT    → 修改后写入 ✓
  ├── DISCARD → 丢弃 ✗
  └── OWNER_OVERRIDE → owner 强制采纳
```

#### 任务路由

主人格收到任务时，`TaskRouter` 决定执行路径：

| 判断 | 路径 |
|------|------|
| 简单回复性问题 | 主人格直接做 (Think → Plan → Act → Review) |
| 需查多文件 / 多步骤 | 派 sub (Think → 派 sub → sub 执行 → ReviewGate 审阅) |

### 🔧 子智能体系统（Tool Agent）

Tool Agent 是**无人格执行体**——不走 seed / identity / 人格 prompt，但可以调 LLM 做工具性任务（语义搜索、摘要、分析）。LLM 调用不带人格上下文，纯粹是工具性的。它不写 vault、不读 seed，是 sub 系统的补充。

> ✅ **issue #63/#64 已完成**: 5 个内置 agent 已全部注入 provider 具备 LLM 能力；ToolAgent 注册为 `ToolProtocol` 由 LLM 自发 tool calling 调用，关键词路由已删除 (issue #72)。

#### 与 sub 的区别

| | Sub-Personality | Tool Agent |
|---|---|---|
| **人格 prompt** | 有 (从 seed 派生, 走 identity/tone/voice) | 无 (纯工具性, 不注入人格) |
| **LLM 调用** | 有 (带人格 system prompt) | 有 (工具性调用, 不带人格) |
| **vault 写权限** | 有 (经 ReviewGate 审阅) | 无 (只读) |
| **seed 访问** | 有 (锚定 parent_seed_hash) | 无 |
| **持久化** | 默认不持久化 (任务完成即销毁) | 无状态 |
| **适用场景** | 需要人格判断 / 多步骤 / 产出写入 vault | 语义搜索 / 摘要 / 分析 / 查询 / 统计 |

#### 5 个内置 Tool Agent

| Agent | 能力 | LLM | 安全 |
|-------|------|-----|------|
| **VaultReadAgent** | 读 vault 文件 + Obsidian 双链解析 + 摘要 | ✅ `_summarize` (issue #63) | `blocked_prefixes` 阻止读 `mortis-steiner/` + `sub-outputs/` |
| **VaultSearchAgent** | 关键词搜索 + 标签过滤 + 双链图 BFS + 语义重排 | ✅ `_semantic_rerank` (issue #63) | 只读 + redact 覆盖 |
| **VaultStatsAgent** | growth 统计 (维度分布 / 置信度直方图) + LLM 分析 | ✅ `_analyze_stats` (issue #63) | 只读 (仅传聚合数字) |
| **MarkdownRenderAgent** | Obsidian 语法解析 (双链/标签/嵌入/折叠/callout) | 不需要 (纯解析) | 无 vault 权限 |
| **ClockAgent** | 当前时间 + 逻辑时钟相位 + 上次 dream 时间 | 不需要 (报时间) | 只读 |

#### 调用方式

Tool Agent 注册到 `ToolRegistry`（与 `VaultReadTool` 等纯工具共用注册表），由主智能体 / sub 智能体在对话中通过 **LLM tool calling** 自发调用：

```
LLM → tool_call("vault:search", {"query": "焦虑", "semantic": true})
    → registry.execute("vault:search", ...)
    → VaultSearchAgent.execute(...) (内部可调 LLM 做语义排序)
    → 结果回传 LLM
```

> ✅ **issue #64/#72 已完成**: `TaskRouter` 关键词 substring 路由已删除，ToolAgent 注册为 `ToolProtocol` 由 LLM 自发调用。

## 快速开始

```bash
# 1. 准备 vault（任何目录都行）
mkdir ~/my-vault && cd ~/my-vault
# 写 seed.md（必含七维度：identity/values/tone/agency/relations/creativity/mortality）

# 2. 安装
git clone https://github.com/HeDaas-Code/Mortis.git
cd Mortis
pip install -e .

# 3. 启动 Mortis CLI
export MINIMAX_API_KEY=your_key  # 或用 MockProvider 测试
python -m mortis --vault ~/my-vault

# 4. CLI 命令（v0 主人格 + sub）
python -m mortis whoami                    # 主人格自报身份
python -m mortis delegate "写一份周报"      # 派 sub 跑任务
python -m mortis pending                   # 列待审 sub 产出
python -m mortis approve <id>              # 批准 sub 产出
python -m mortis archive <thread-id>       # 归档 thread 经验

# 5. CLI 命令（v3 认知周期 + 运行时）
python -m mortis reflect                   # 手动触发 REFLECT 态 (issue #56)
python -m mortis dream --level light      # 触发指定级别梦境 (issue #56)
python -m mortis clock                     # 查看当前逻辑时钟时段 (issue #56)
python -m mortis dreams                    # 列 dream-log 历史 (issue #56)
python -m mortis status                    # 查看 runtime 状态 (growth/unease/drift)
python -m mortis goodnight                 # owner 晚安 → 触发完整夜间周期 (issue #61)
python -m mortis daemon                    # 常驻进程 + Scheduler.tick 自动调度 (issue #60)
python -m mortis web                       # 启动 Web UI server (issue #52)
```

## 项目结构

```
mortis/
├── growth/          # 七维度成长记忆 (Growth model + vault layout + Obsidian writer + 压缩)
├── vault/           # Vault 抽象 (本地目录实现 + Obsidian 解析 + 安全白名单 + ReviewGate)
├── memory/          # Session/Thread/Archive (原始经验存储)
├── seed/            # 不可变人格核心 (七维度 schema)
├── pipeline/        # Think→Plan→Act→Review 编排 + TaskRouter
├── runtime/         # MasterRuntime + SubRuntime + RuntimeContext + growth 检索 + unease 注入
├── reflect/         # ReflectExecutor (反思态 + 情绪标注 + 触发条件)
├── dream/           # DreamExecutor Light/Medium/Deep + 7 phase pipeline + drift 监控
├── steiner/         # Reading Steiner (unease + watcher + drift 报警 + 生命周期管理)
├── clock/           # 逻辑时钟 + 昼夜节律 + 睡眠不足 + Scheduler
├── toolagent/       # 5 内置 Agent (无人格执行体, 已注入 provider)
├── provider/        # LLM Provider 抽象 (Mock + Minimax + 注册表 + 任务路由 + 审计 hash)
├── tools/           # LLM Tool Protocol (VaultRead/Write/List/Exists + 5 Agent 包装器)
├── redact/          # 共享 redact 工具 (6 SENSITIVE_PATTERNS + fail-closed, issue #83)
├── cli/             # CLI 命令 (14 个: list/whoami/dump/delegate/pending/dream/reflect/status/daemon/goodnight/web)
└── web/             # Web UI server + owner 通知通道 (issue #52-#54)
```

## 代码规模

| 模块 | 源码 | 层级 |
|------|------|:----:|
| seed (人格种子) | 135 | L0 |
| clock (逻辑时钟) | 450 | L0 |
| growth (成长记忆) | 800 | L1 |
| steiner (Reading Steiner) | 700 | L1* |
| redact (共享脱敏) | 100 | L1** |
| vault (Obsidian vault) | 1300 | L2 |
| memory (会话/线程/归档) | 291 | L3 |
| provider (LLM Provider) | 500 | L3 |
| tools (工具系统) | 678 | L4 |
| toolagent (Tool Agent) | 1123 | L4 |
| runtime (运行时) | 700 | L5 |
| pipeline (编排) | 620 | L6 |
| reflect (反思态) | 555 | L7 |
| dream (三级梦境) | 2700 | L7 |
| cli (命令行) | 600 | L8 |
| web (Web UI + 通知) | 350 | L8 |
| **合计** | **~9,800** | — |

**986 tests passed, 2 skipped** — 64 个测试文件覆盖 78 个流程节点 (77 已覆盖, 98.7%)，含主路径 + 边界 + 安全检查 + redact 对抗性测试。

## 路线图

- **v0** ✅: 骨架——vault 抽象 + 主人格引擎 + mortis 架构核心
- **v1** ✅: Obsidian vault 实现 + Growth 格式 + RuntimeContext 集成
- **v2.0-v2.5** ✅: ReflectExecutor + DreamExecutor 三级 (Light/Medium/Deep) + Reading Steiner + 逻辑时钟 + Tool Agent 层
- **v3.0 运行时集成** ✅ (#56-#61): CLI 扩展 + unease 注入 + GrowthWatcher 启动 + growth 检索 + Daemon 模式 + owner「晚安」触发
- **v3.1 生产化** ✅ (#45-#48): 多 LLM 后端注册表 + async generate + retry/timeout + growth 维度压缩 + drift 误报率监控
- **v3.2 体验层** ✅ (#52-#54): Web UI server + growth 浏览器 + unease 仪表盘 + owner 通知通道
- **v3 审计** ✅: 方法级代码审计 + 全项 E2E 生产级实验，22 个安全漏洞已修，88 个 issues 全部关闭

### 下一步

- **v4 架构演进**: Provider 原生 function calling (消除 TextCall 降级) / Growth 向量语义检索 / Steiner unease 情绪向量 (影响 temperature/top_p)
- **v5 生态扩展**: 多 provider 路由策略优化 (按任务类型 + 成本 + 延迟) / Obsidian 插件 (Graph View 集成) / owner 移动端通知推送

## 文档

- [RFC-001: 认知生长系统](docs/rfc/RFC-001-cognitive-growth.md) — 三态意识 + 梦境分级 + Reading Steiner 完整设计
- [RFC-001 分解计划](docs/rfc/RFC-001-decomposition.md) — 9 个 issue 的依赖关系和工作量估算
- [RFC-001 开放问题裁剪](docs/rfc/RFC-001-open-questions-decision.md) — 7 个开放问题的 owner 决策
- [Mortis v3 方法级代码审计报告（图文版）](docs/mortis-audit-v3/mortis-audit-v3.md) — 人类阅读，含 10 张白底黑字架构图
- [Mortis v3 方法级代码审计报告（Agent 版）](docs/mortis-audit-v3/mortis-audit-v3-agent.md) — AI Agent 阅读，纯文本结构化，无图片
- [Mortis v3 全项 E2E 生产级实验报告（图文版）](docs/mortis-audit-v3/e2e-report.md) — 人类阅读，含 6 张调用链 + 信息流转图
- [Mortis v3 全项 E2E 生产级实验报告（Agent 版）](docs/mortis-audit-v3/e2e-report-agent.md) — AI Agent 阅读，纯文本结构化，无图片

## 我从来没有觉得烧Token开心过

**Mortis** 来自日本动画《Ave Mujica》中角色**若叶睦**的保护者人偶。

## 审计

Mortis 经过多轮独立代码审计，最新 v3.1 审计报告覆盖方法级调用链分析、信号结构梳理、架构剖析、安全审计、信息流转模拟、测试覆盖率分析（78 流程节点）与分支/Issue 时间轴。报告提供两个版本，按读者类型选择：

| 读者 | 文件 | 说明 |
|------|------|------|
| **人类** | → [图文版](docs/mortis-audit-v3/mortis-audit-v3.md) | 含 10 张白底黑字架构图 + 调用链 + 安全矩阵 |
| **AI Agent** | → [Agent 版](docs/mortis-audit-v3/mortis-audit-v3-agent.md) | 纯文本结构化，无图片引用，便于解析 |

**审计修复摘要**：
- **22 项安全漏洞已修 / 0 项潜在**（含 S1-S3 路径遍历、#6 白名单下沉、#17 ReviewGate 越权、#38 steiner 隐藏层、#67 中段绕过、#71 异常吞没、#73 redact、CRITICAL-1/2 数据泄漏、#83-#88 redact 共享模块与统一类型）
- **8/11 LLM 调用点已覆盖 redact**（剩余 3 个为 pipeline 层带人格上下文 + 纯统计数字，无私密字段泄漏风险）
- 2 个测试 time-bomb 隐患（已修复，动态日期替代硬编码）
- 88 个 issues 全部关闭，986 tests passed

## E2E 生产级实验

Mortis v3 在真实 minimax MiniMax-M3 API 环境下进行全项端到端（E2E）生产级测试，覆盖审计报告 §02 中全部 11 个 LLM 调用点、6 个安全机制、3 级 Dream 流水线、完整认知周期（AWAKE→REFLECT→DREAM_LIGHT）。报告含完整调用链分析（图片呈现调用链，含文件名 + 行号标注）、信息流转模拟、Vault 写入点追踪、信号传播图。报告提供两个版本，按读者类型选择：

| 读者 | 文件 | 说明 |
|------|------|------|
| **人类** | → [图文版](docs/mortis-audit-v3/e2e-report.md) | 含 6 张白底黑字调用链 + 信息流转图 + 调用链 + 安全矩阵 |
| **AI Agent** | → [Agent 版](docs/mortis-audit-v3/e2e-report-agent.md) | 纯文本结构化，无图片引用，便于解析 |

**E2E 实验摘要**：
- 25/25 步骤 100% 通过率，44 次真实 LLM 调用，总耗时 285.67s
- 11/11 LLM 调用点全部验证（pipeline 3 + toolagent 3 + dream 4 + reflect 1）
- 6/6 安全机制全部拦截（redact / 白名单 / blocked_prefixes / 审计 hash）
- 完整认知周期 AWAKE→REFLECT→DREAM_LIGHT 端到端通过（E2E-25, 75.47s, 10 LLM）

## 许可

MIT

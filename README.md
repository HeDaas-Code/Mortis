# Mortis

> **Mortis — A Mortal That Lives In Your Vault**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Status: v2.5](https://img.shields.io/badge/status-v2.5-blue)]()
[![Tests: 482 passed](https://img.shields.io/badge/tests-482%20passed-brightgreen)]()

**Vault-borne growing agent.** Ownerable, seed-grown, never OOC.

---

## 这是什么

Mortis 是一个 **基于 vault 生长出来的智能体框架**——它不是"调 API 的聊天机器人"，而是一个有昼夜节律、会做梦、会反思、会被 owner 的编辑"隐约不安"的人格系统。

- **vault** 是它的"认知系统"（不是数据存储，是它的"脑子"）—— Obsidian 原生格式，双链/标签/折叠/注释全支持
- **seed.md** 是它的不可变人设核心（OOC 防御）—— 七维度定义，任何生成必从 seed 重算
- **三态意识** (AWAKE → REFLECT → DREAM) 让它有"醒着干活、睡前反思、做梦生长"的节律
- **Reading Steiner** 让它感知到 owner 编辑了它的记忆——隐约不安但不知道细节（石头门时间线理论）
- **mortis 工作架构** 让它能委派任务给 sub 智能体——主人格全权管理 sub

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
- **sub 必须锚定主人格** —— 构造时校验 `parent_seed_hash`
- **白名单授权** —— sub 不能越权访问 vault，ToolAgent 有 `blocked_prefixes` 阻止读 steiner 层

### 👁️ Reading Steiner — 时间线扰动感知

owner 编辑了 growth 记忆 → Mortis 隐约不安（per dimension unease 值上升）→ 注入 system prompt 的潜台词 → drift 过高时通知 owner。

Mortis **不知道** steiner 层的存在——它只是"感觉不安"，不会直接感知到被编辑。

### 🕐 逻辑时钟 + 昼夜节律

- 6 时段: AWAKE / REFLECT / DREAM_LIGHT / DREAM_DEEP / ERODE
- 时区感知 (`tz` 参数) —— 时段表按本地时间解释
- 睡眠不足语气注入 (debt > 24h/36h/48h 三档)
- owner "晚安"关键词立即触发 REFLECT

### 🛠️ Tool Agent 层 — 无人格执行体

比 sub 更轻量——不调 LLM、不写 vault、不读 seed，直接执行工具调用：

| Agent | 能力 |
|-------|------|
| VaultReadAgent | 读 vault 文件 + Obsidian 双链解析 (blocked: steiner/) |
| VaultSearchAgent | 关键词搜索 vault |
| VaultStatsAgent | growth 统计 (维度/置信度/标签) |
| ClockAgent | 当前时间 + 逻辑时钟相位 + 上次 dream |
| TaskRouter | 关键词路由 → 分发到对应 Agent |

### 🧬 三层模板链（mortis 工作架构）

```
L0 硬编码通用 sub 模板（代码层）
    │
    ▼ + 主人格风格
    │
L1 子人格设计通用模板（按主人格生成）
    │
    ▼ + 当前任务
    │
L2 工作 sub 人格 + sub 智能体
```

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

# 4. CLI 命令
python -m mortis whoami                    # 主人格自报身份
python -m mortis delegate "写一份周报"      # 派 sub 跑任务
python -m mortis pending                   # 列待审 sub 产出
python -m mortis approve <id>              # 批准 sub 产出
python -m mortis archive <thread-id>       # 归档 thread 经验
```

## 项目结构

```
mortis/
├── growth/          # 七维度成长记忆 (Growth model + vault layout + Obsidian writer)
├── vault/           # Vault 抽象 (本地目录实现 + Obsidian 解析 + 安全白名单)
├── memory/          # Session/Thread/Archive (原始经验存储)
├── seed/            # 不可变人格核心 (七维度 schema)
├── pipeline/        # Think→Plan→Act→Review 编排 + TaskRouter
├── runtime/         # MasterRuntime + SubRuntime + RuntimeContext
├── reflect/         # ReflectExecutor (反思态 + 情绪标注 + 触发条件)
├── dream/           # DreamExecutor Light/Medium/Deep + 7 phase pipeline
├── steiner/         # Reading Steiner (unease + watcher + drift 报警)
├── clock/           # 逻辑时钟 + 昼夜节律 + 睡眠不足 + Scheduler
├── toolagent/       # 5 内置 Agent + TaskRouter (无人格执行体)
├── provider/        # LLM Provider 抽象 (Mock + Minimax)
├── tools/           # LLM Tool Protocol (VaultRead/Write/List/Exists)
└── cli/             # CLI 命令 (list/whoami/dump/delegate/pending/approve/archive)
```

## 代码规模

| 模块 | 源码 | 测试 |
|------|------|------|
| growth (成长记忆) | 663 | — |
| vault (Obsidian vault) | 1085 | — |
| dream (三级梦境) | 2473 | — |
| reflect (反思态) | 555 | — |
| steiner (Reading Steiner) | 545 | — |
| clock (逻辑时钟) | 362 | — |
| toolagent (Tool Agent) | 796 | — |
| pipeline (编排) | 620 | — |
| runtime (运行时) | 567 | — |
| 其他 (seed/memory/provider/tools/cli) | 1442 | — |
| **合计** | **~9100** | **~6400** |

**482 tests passed** — 覆盖所有模块的主路径 + 边界 + 安全检查。

## 路线图

- **v0** ✅: 骨架——vault 抽象 + 主人格引擎 + mortis 架构核心
- **v1** ✅: Obsidian vault 实现 + Growth 格式 + RuntimeContext 集成
- **v2.0-v2.2** ✅: ReflectExecutor + DreamExecutor Light
- **v2.3-v2.5** ✅: Dream Medium/Deep + Reading Steiner + 逻辑时钟 + Tool Agent 层
- **v3** (下一步): 运行时集成——把 clock/scheduler/dream/reflect/steiner 接入 CLI 和 runtime
- **v4**: Obsidian 插件 + Web UI + 多 LLM 后端

### v3 下一步具体工作

RFC-001 的 9 个模块都已实现并通过测试，但它们 **还没有接入运行时**。当前 CLI 只暴露 v0 的 `delegate/pending/approve/archive` 命令，clock/dream/reflect/steiner 需要 owner 手动调 Python API。

v3 的核心任务：

1. **Daemon 模式** —— `python -m mortis --vault ~/my-vault --daemon` 启动后台进程，LogicalClock 自动 tick
2. **Scheduler 集成** —— Scheduler.tick() 触发 ReflectExecutor / DreamExecutor，不需要手动调
3. **Steiner watcher 启动** —— GrowthWatcher 监听 `mortis-growth/` 变更，自动 accumulate unease
4. **CLI 扩展** —— `mortis reflect`、`mortis dream --level light|medium|deep`、`mortis clock` 命令
5. **unease 注入 RuntimeContext** —— AWAKE 时读 unease，注入 system prompt 潜台词
6. **dream-log 查询** —— `mortis dreams` 列历史 dream 记录

## 文档

- [RFC-001: 认知生长系统](docs/rfc/RFC-001-cognitive-growth.md) — 三态意识 + 梦境分级 + Reading Steiner 完整设计
- [RFC-001 分解计划](docs/rfc/RFC-001-decomposition.md) — 9 个 issue 的依赖关系和工作量估算
- [RFC-001 开放问题裁剪](docs/rfc/RFC-001-open-questions-decision.md) — 7 个开放问题的 owner 决策

## 命名文化背景

**Mortis** 来自日本动画《Ave Mujica》中角色**若叶睦**的精神分裂子人格：

| 动画设定 | 项目映射 |
|---|---|
| 若叶睦 = 本体 | owner / 主体 |
| Mortis = 睦派生的子人格 | sub 人格 / sub 智能体 |
| Mortis 知道自己从睦派生 | sub 知道自己从主人格派生 |
| 睦对 Mortis 有完全控制 | 主人格对 sub 全权管理 |
| Mortis 不冒充睦 | sub 严格不冒充主人格 |

参考：《BanG Dream! Ave Mujica》动画系列。

## 审计

Mortis 经过独立第三方智能体（哈尼斯）的全量代码审计，发现并修复了 6 个 bug + 死代码。审计报告见 PR #32-#34 的 review comments。

## 许可

MIT

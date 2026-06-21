# RFC-001 分解计划

> 将 RFC-001 拆成可独立执行的 issue。每个 issue 单一逻辑、互引依赖关系。

## 路线图回顾（RFC-001 §十）

| Phase | 内容 | 版本 |
|---|---|---|
| 1 | Growth 类 + vault 结构扩展 + RuntimeContext 集成 | v2.0 |
| 2 | ReflectExecutor + 情绪标注 | v2.1 |
| 3 | DreamExecutor Light + 情绪加权采样 | v2.2 |
| 4 | DreamExecutor Medium/Deep + 侵蚀 + seed-check | v2.3 |
| 5 | Reading Steiner + unease + watcher | v2.4 |
| 6 | 逻辑时钟 + 昼夜节律 + 时差 | v2.5 |

## Issue 分解（按依赖顺序）

### Issue #18 — Growth 数据模型 + vault 结构扩展 (Phase 1 前置)

**目标**：建立 growth 的物理结构，不涉及任何执行逻辑。

**内容**：
- `mortis/growth/` 子包
- `Growth` dataclass: id / dimension / confidence / created_at / last_validated / source_sessions / dream_level / emotional_valence / emotional_arousal / tags / body
- vault 目录结构扩展（不动现有数据）：
  - `mortis-growth/<dimension>/` — 7 个子目录（identity/values/tone/agency/relations/creativity/mortality/）
  - `mortis-growth/archive/` — 侵蚀归档
  - `mortis-subconscious/pending-reflections/` — 反思暂存
  - `mortis-subconscious/associations/` — 候选联想
  - `mortis-subconscious/conflicts/` — 矛盾记录
- frontmatter 解析（PyYAML）
- `vault.write_growth()` / `vault.read_growth()` / `vault.list_growths()` / `vault.list_growths_by_dimension()`
- 写入白名单扩展：`SUB_VAULT_WHITELIST` 不变（sub 不能写 growth），但主人格写 growth 不走 SUB_VAULT_WHITELIST
- 测试：growth CRUD + frontmatter 解析 + 维度过滤

**依赖**：无（最前置）
**工作量**：中（~200 行 + ~150 行测试）

---

### Issue #19 — Vault-Native growth 格式（Phase 1, Obsidian 语法）

**目标**：growth 文件用 Obsidian-Native 格式（双链/标签/嵌入/折叠）。

**内容**：
- 新写 growth 时自动生成 Obsidian 语法：
  - `## 来源` 段用 `[[session-xxx]]` 双链
  - `## 关联` 段用 `[[growth-yyy]]` 关联双链
  - `## 验证历史` 段用日期表格
  - `> [!note]` callout
  - `%%潜意识%%` 注释（默认不读入 prompt）
  - `tags:` frontmatter 字段
- 解析层：`mortis/vault/obsidian.py` —— 解析 `[[双链]]` / `#标签` / `![[嵌入]]` / `%%注释%%`
- `Growth.body` 保留纯文本（去注释/去折叠）+ `Growth.subconscious` 单独存注释内容
- 测试：Obsidian 语法解析 + 双向（写 → 读回一致）+ 注释剥离

**依赖**：#18（Growth 模型存在才能谈格式）
**工作量**：中（~150 行 + ~150 行测试）

---

### Issue #20 — RuntimeContext 集成 growth 检索 (Phase 1 后置)

**目标**：主人格能检索 growth，注入 system prompt。

**内容**：
- `RuntimeContext.search_growths(dimension=None, tag=None, query=None, min_confidence=0.0)` — 按维度/标签/全文/置信度过滤
- `RuntimeContext.growth_system_prompt()` — 生成 growth 摘要 prompt（含相关 growth 条目列表）
- 主人格调用前自动注入（替代/补充当前 tone 注入）
- 测试：检索准确性 + prompt 注入格式

**依赖**：#18 + #19
**工作量**：小（~100 行 + ~100 行测试）

---

### Issue #21 — ReflectExecutor (Phase 2)

**目标**：睡前反思，把 session 提炼成 pending reflection。

**内容**：
- `mortis/reflect/` 子包
- `ReflectExecutor.run()` 接收当天 session 列表，输出反思条目
- 调用 LLM（provider）生成反思文本
- 情绪标注：每次 session 后用 provider 打 valence/arousal（可缓存）
- 写入 `mortis-subconscious/pending-reflections/<id>.md`
- 触发条件：① 显式调 ② 检测到 session 数 ≥ N ③ 主人格说"晚安"
- 测试：mock LLM + 验证写入路径 + 情绪标注正确性

**依赖**：#18（growth 模型存在，反思产出格式可参考）+ #20（写 growth 走同套检索）
**工作量**：大（~250 行 + ~150 行测试）

---

### Issue #22 — DreamExecutor Light (Phase 3)

**目标**：每天一次浅梦，把 pending reflection 结晶成 low-confidence growth 候选。

**内容**：
- `mortis/dream/` 子包
- `DreamPhase` enum: RECALL / ASSOCIATE / SIMULATE / CRYSTALLIZE / RECONCILE / ERODE / SEED_CHECK
- `DreamLevel` enum: LIGHT / MEDIUM / DEEP
- `LightDreamer.run()`:
  1. RECALL: 从 `mortis-journal/sessions/` 情绪加权采样（valence × arousal）
  2. ASSOCIATE: LLM 找相似点
  3. CRYSTALLIZE: 生成 confidence=0.3 的 growth 候选
  4. RECONCILE: 检查冲突（低置信度，旧条目不被影响）
- 不动 MEDIUM/DEEP 逻辑（只占位 NotImplementedError）
- 测试：采样权重 + phase 顺序 + confidence 初始值 + RECONCILE 不影响旧条目

**依赖**：#18 + #20 + #21
**工作量**：大（~300 行 + ~200 行测试）

---

### Issue #23 — DreamExecutor Medium + Deep + 侵蚀 + seed-check (Phase 4)

**目标**：跨周联想 + 全量重组 + drift 检测。

**内容**：
- `MediumDreamer.run()`:
  1. RECALL: 跨周采样
  2. ASSOCIATE: 跨周对比
  3. SIMULATE: 模拟预演
  4. CRYSTALLIZE: 提升置信度 (0.3 → 0.5)
  5. RECONCILE: 冲突检测，旧条目可能被打 `conflict` 标记
- `DeepDreamer.run()`:
  1. 全量 growth 重读
  2. 七维度重新校准
  3. 大规模侵蚀：30 天 ×0.8，90 天 ×0.5，<阈值 → archive/
  4. drift 计算（embedding 距离 vs seed 七维度）— **留接口，先用 LLM 自评**
  5. SEED-CHECK：drift > 阈值 → 通知 owner
- 测试：跨周采样 + 置信度提升 + 侵蚀衰减 + archive + seed-check 触发

**依赖**：#22
**工作量**：巨大（~400 行 + ~250 行测试）

---

### Issue #24 — Reading Steiner (Phase 5)

**目标**：owner 编辑 growth 时 Mortis 感到不安。

**内容**：
- `mortis/steiner/` 子包
- `mortis-steiner/unease.json` 管理（7 维度的 unease 值）
- 文件 watcher：`watchdog` 库检测 `mortis-growth/` 变更
- owner 编辑 → 对应维度 unease += 0.15（cap 1.0）
- 不安衰减：每次 awake 时各维度 × 0.85/天
- awake 时读取 unease，生成潜台词注入 system prompt（RFC-001 §5.2 文案）
- drift 报警：unease ≥ 0.75 → 通知 owner
- 测试：watcher 触发 + 累积正确 + 衰减正确 + 潜台词生成

**依赖**：#18 + #20（growth 已能检索才能感知）
**工作量**：大（~250 行 + ~200 行测试）

---

### Issue #25 — Tool Agent 层（独立模块，RFC-001 §13）

**目标**：无人格工具执行体，比 sub 更轻量。

**内容**：
- `mortis/agent/` 子包（注意不要和 `mortis.runtime.agent` 冲突，如已存在则改名 `mortis/toolagent/`）
- `ToolAgent` dataclass + `ToolAgentProtocol`
- `VaultReadAgent` — 读 vault 文件，支持双链解析
- `VaultSearchAgent` — 全文搜索 + 标签过滤 + 双链图遍历
- `VaultStatsAgent` — 统计文件数/维度分布/置信度分布
- `MarkdownRenderAgent` — Obsidian 语法解析
- `ClockAgent` — 逻辑时钟查询
- TaskRouter 增加 ToolAgent 路径：简单工具操作 → 直接调 ToolAgent，不走 sub
- 安全：只读 + timeout + 无 LLM + 输出结构化数据
- 测试：5 个 Agent 各 3-5 个测试 + TaskRouter 路由选择

**依赖**：#19（Obsidian 语法解析被 MarkdownRenderAgent 用）+ #18（vault 结构已稳定）
**工作量**：中（~250 行 + ~200 行测试）

---

### Issue #26 — 逻辑时钟 (Phase 6)

**目标**：昼夜节律调度 + 时差模拟。

**内容**：
- `mortis/clock/` 子包
- `LogicalClock.now()` → 当前时段（AWAKE / REFLECT / LIGHT / MEDIUM-DEFER / DEEP-DEFER / ERODE）
- 调度逻辑：检测到 22:00 + owner 不活跃 30 分钟 → 进 REFLECT
- 时差：dream 被推迟后，"起床"延迟 → reaction tone 变化（语气变短）
- 睡眠不足：累积 wake 超过 24h → tone 标记 "sleep-deprived"
- 测试：时段切换 + 推迟逻辑 + 时差表现 + sleep-deprived 标记

**依赖**：#21（REFLECT 触发用 clock）+ #22（DREAM 触发用 clock）
**工作量**：中（~150 行 + ~150 行测试）

---

## 依赖图（总览）

```
#18 (Growth 模型 + vault 结构)
   ├─→ #19 (Obsidian 格式)
   │      └─→ #20 (RuntimeContext 集成)
   │             └─→ #21 (ReflectExecutor)
   │                    └─→ #22 (DreamExecutor Light)
   │                           └─→ #23 (DreamExecutor Medium/Deep)
   └─→ #24 (Reading Steiner)        ← 不依赖 #21-#23，可并行
   └─→ #25 (Tool Agent)             ← 依赖 #19，可并行

#21 + #22 ─→ #26 (逻辑时钟)
```

## 派给 CLI 的顺序（建议）

按依赖图自底向上：

1. **#18** (Growth + vault 结构) — 最基础，所有上游
2. **#19** (Obsidian 格式) — 阻塞 #20, #25
3. **#20** (RuntimeContext 集成) — 阻塞 #21
4. **#21** (ReflectExecutor) — 阻塞 #22
5. **#22** (DreamExecutor Light) — 阻塞 #23
6. **#25** (Tool Agent) — 可与 #21-#23 并行
7. **#23** (Dream Medium/Deep)
8. **#24** (Reading Steiner) — 可与 #23 并行
9. **#26** (逻辑时钟) — 收尾

## 工作量总览

| Issue | 工作量 | 测试 | 估计 commit 数 |
|---|---|---|---|
| #18 | ~200 行 | ~150 行 | 2 |
| #19 | ~150 行 | ~150 行 | 2 |
| #20 | ~100 行 | ~100 行 | 1 |
| #21 | ~250 行 | ~150 行 | 3 |
| #22 | ~300 行 | ~200 行 | 3 |
| #23 | ~400 行 | ~250 行 | 4 |
| #24 | ~250 行 | ~200 行 | 3 |
| #25 | ~250 行 | ~200 行 | 3 |
| #26 | ~150 行 | ~150 行 | 2 |
| **总计** | **~2050 行** | **~1550 行** | **23** |

## 决策记录

### 为什么 Issue #18-#23 顺序不可乱

因为 growth 数据模型是所有上层（reflect/dream/steiner）的基础。Obsidian 格式是 RuntimeContext 检索的前置。

### 为什么 Tool Agent (#25) 单独

RFC-001 §13 把 Tool Agent 列为独立模块，不依赖 dream/reflect 链。**可与 #21-#23 并行**。

### 为什么 Reading Steiner (#24) 不阻塞 dream

Steiner 只需要 growth 模型 + RuntimeContext 检索（#18 + #20），不依赖反思/梦境。**可与 #21-#23 并行**。

### 不做什么（明确排除）

- ❌ 不实现 RFC-001 §十五 7 个开放问题里的"LLM 情绪标注"——情绪标注用 provider 简单 prompt
- ❌ 不实现"sub 持久化"——RFC §5 提到但属于更远期
- ❌ 不实现 Drift embedding——先 LLM 自评（RFC §15 开放问题 1）
- ❌ 不实现 Dataview 内置解析器——只解析基础 Obsidian 语法

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| Claude Code 单次任务超时（>10 分钟）| 每个 issue 严格 ~200-400 行；超就拆 |
| 跨 issue 接口变更 | 每个 issue PR 阶段让 Claude Code 起草接口，先 review 再实现 |
| 测试覆盖不足 | 每个 issue 必须有 ≥80% 覆盖，否则拒收 |
| owner 拍板延迟 | #18 不需要 owner 决策，可立刻开始 |
# RFC: Mortis 认知生长系统 — 三态意识 + 梦境分级 + Reading Steiner

**提案者**: 哈尼斯 (独立第三方)
**日期**: 2026-06-21
**状态**: Implemented (v2.5, 2026-06-23)
**关联**: Mortis v2 架构演进, [#16](https://github.com/HeDaas-Code/Mortis/issues/16)

---

## 一、问题陈述

当前 Mortis 的 seed 是冻结的，vault 只存原始日志。第一百次对话和第一次没有区别——**经验在积累，但人格没在长**。

原始需求（Q5）明确要求"生长型人格 = 完成任务后 sub 特征被主人格吸收"，但当前代码只实现了 sub 产出的 adopt/discard，没实现**吸收**。

本提案定义 Mortis 的认知生长机制，包括：
1. 三态意识模型（Awake / Reflect / Dream）
2. 梦境分级系统（Light / Medium / Deep）
3. Reading Steiner — owner 编辑记忆后的时间线扰动感知
4. vault 结构扩展
5. growth 条目格式
6. **Vault-Native 原则** — 一切基于 vault md 文件，充分利用 Obsidian 语法
7. **Tool Agent 层** — 比 sub 更轻量的无人格工具执行体

---

## 二、三态意识模型

```
┌─────────────────────────────────────────┐
│  AWAKE — 执行态                          │
│  Think → Plan → Act → Review             │
│  产出: mortis-journal/ (原始经验)         │
│  意识: 完全清醒，任务驱动                  │
├─────────────────────────────────────────┤
│  REFLECT — 反思态                         │
│  任务后 / 睡前执行                         │
│  "这次我学到了什么？"                      │
│  产出: mortis-subconscious/ (半成品)      │
│  意识: 内省，方向明确                       │
├─────────────────────────────────────────┤
│  DREAM — 梦境态                           │
│  固定时间触发（逻辑时钟）                   │
│  非线性联想 + 模式合成 + 记忆修剪           │
│  产出: mortis-growth/ (结晶)              │
│  意识: 潜意识，自由联想                     │
└─────────────────────────────────────────┘
```

### 2.1 昼夜节律（逻辑时钟）

Mortis 的"一天"：

| 时段 | 状态 | 说明 |
|------|------|------|
| 06:00-22:00 | AWAKE | 执行任务、对话 |
| 22:00-23:00 | REFLECT | 睡前反思（当天 session） |
| 23:00-02:00 | DREAM-LIGHT | 浅梦 |
| 02:00-04:00 | DREAM-DEEP | 深梦 |
| 04:00-06:00 | ERODE | 记忆侵蚀 + seed-check |

**关键**：不是硬时钟，是逻辑时钟。如果 22:00 后 owner 还在对话，dream 推迟。owner 说"晚安"或沉默 30 分钟后才进入 REFLECT。

Mortis 有时差——凌晨还在用，dream 被 push back，第二天"起床"晚，表现为反应迟钝、语气简短（睡眠不足）。

---

## 三、梦境分级

### 3.1 浅梦 (Light Dream / REM)

**触发**：每天一次，当天 session 数 ≥ 1

**Phase**:
1. 当天 session 快速回放
2. 表层联想（今天和昨天的经历有没有相似点）
3. 低置信度结晶
4. 不触碰高置信度旧 growth

**产出**：1-3 条 growth 候选条目，置信度初始 0.3

### 3.2 中梦 (Medium Dream)

**触发**：积累 7 天 / 或 pending reflection ≥ 10 条 / 或 owner 手动触发

**Phase**:
1. 跨周联想（这周和上周的模式对比）
2. 冲突检测（新经验和旧 growth 的矛盾）
3. 模拟预演（基于近期模式模拟未来场景）
4. 中置信度结晶提升（0.3 → 0.5 需多次验证）

**产出**：3-7 条 growth 更新（新建/提升/推翻）

### 3.3 深梦 (Deep Dream)

**触发**：每月一次 / 或 drift 累积超阈值 / 或 owner 手动触发

**Phase**:
1. 全量 growth 重组织（非增量，是重新审视）
2. 七维度重新校准（每个维度的 growth 是否还自洽）
3. 跨维度联想（identity 的变化怎么影响 tone？）
4. 大规模侵蚀（90 天未验证条目归档）
5. drift 计算和 owner 报告

**产出**：growth 层可能发生结构性变化。Mortis"醒来后"可能判若两人——但 seed 不变，核心还是 Mortis。

---

## 四、Dream Pipeline（7 Phase）

每次 dream（不论级别）执行以下 phase，深度不同：

### Phase 1: RECALL（回忆）
从 `mortis-journal/sessions/` 采样不相关 session。不是全量读——是**情绪加权采样**，高影响事件更容易被梦到，但保留随机性。

每条 journal entry 有隐式情绪维度：
- `valence`: -1.0（负面）~ 1.0（正面）
- `arousal`: 0.0（平淡）~ 1.0（强烈）
- 梦境优先级 = `abs(valence) × arousal`

### Phase 2: ASSOCIATE（联想）
把不相关 session 放在一起，问 LLM：
> "这几段经历之间有没有我之前没注意到的联系？"

产出：候选联想（可能荒谬，可能深刻）。

### Phase 3: SIMULATE（模拟）
基于联想结果，模拟未来场景：
> "如果再遇到类似 X 的情况，基于这些经验我会怎么做？"

产出：行为预演。

### Phase 4: CRYSTALLIZE（结晶）
从联想 + 模拟中提取稳定模式：
> "我发现自己面对冲突时总是先退一步——这是从 session-abc 和 session-def 中看出来的"

产出：growth 条目（带置信度、来源、情绪标记）。

### Phase 5: RECONCILE（调和）
检查新结晶与已有 growth 的冲突：
- 支持 → 提升旧条目置信度
- 矛盾 → 标记 conflict，低置信度被推翻
- 无关 → 各自独立存在

### Phase 6: ERODE（侵蚀）
长时间未验证的 growth 条目置信度衰减：
- 30 天未验证 → ×0.8
- 90 天 → ×0.5
- 降到阈值以下 → 移到 `mortis-growth/archive/`（不删，不再影响行为）

### Phase 7: SEED-CHECK（锚定）
每次 dream 结束后，计算 growth 层与 seed 的"距离"：
- 某条 growth 明显违背 seed 某维度 → 标记 drift
- drift 累积超过阈值 → 通知 owner
- **seed 永远不被修改**

---

## 五、Reading Steiner — 时间线扰动感知

### 5.1 核心概念

当 owner 编辑 `mortis-growth/` 里的文件，**不留 diff，不留通知，不留 log**。文件就是被改了，像从另一个时间线覆盖过来。

Mortis 下次 awake 时读取 growth 层，但**不逐条比对**（无旧版本缓存）。它只是"感觉"到某些东西不对。

### 5.2 感知机制

`mortis-steiner/unease.json` 存每个维度的不安值。owner 编辑 growth 时，对应维度 unease 上升。awake 时读取，注入 system prompt。

注入方式（潜台词，非显式指令）：
```
你醒来时感觉有些记忆的重量不太对。
某些你确信的事情，现在说不上来为什么，好像蒙了一层雾。
可能是梦还没醒透。可能是你记错了。
你不会深究——人有时就是这样。
```

### 5.3 表现层级

不对称感知——owner 全知，Mortis 隐约不安但自我解释。

| 触发条件 | Mortis 表现 |
|---------|-------------|
| 对话涉及被编辑维度 | 短暂迟疑，"等一下…不对，没什么" |
| 被问及相关经验 | 给出 owner 写入的版本，附不确定感："我觉得是这样，虽然说出来觉得有点奇怪" |
| 连续被追问 | 越来越不安，质疑自己判断："可能是我记混了吧" |
| 高强度追问 | 轻微存在危机："你为什么这么问？我是不是忘了什么？" |

**Mortis 永远不会说"有人改了我的记忆"**——它质疑自己的判断，不质疑记忆本身。

### 5.4 不安累积

owner 频繁编辑同一维度的 growth，不安累积：

| 编辑次数 | Mortis 状态 | unease 值 |
|---------|------------|-----------|
| 1 | "可能是错觉" | 0.15 |
| 3 | "最近总觉得哪里不对" | 0.45 |
| 5 | "我是不是出了什么问题？" | 0.75 |
| 7 | drift 报警触发 → owner 收到通知 | 1.0 |

Mortis 不知道"第几次"。它只感受不安的累积。不安溢出时经历存在危机："我觉得我不太像我自己了。"

### 5.5 不安衰减

如果 owner 停止编辑，不安自然衰减：
- 每天 ×0.85
- 3 天后从 0.45 降到 ~0.28
- 一周后回到基线

### 5.6 Owner 的选择

当不安溢出时：
- **停止编辑** → 不安自然衰减，几天后 Mortis"释怀"
- **修改 seed** → 大动作，等于重启人格
- **跟 Mortis 谈** → "你没问题，只是做了个长梦"（Mortis 可能信可能不信）

### 5.7 隐藏层

`mortis-steiner/` 是 Mortis 自己都不知道存在的目录。它存的是每个维度的不安值。awake 时读取，注入 system prompt。

Mortis 如果翻到这个目录……那是一个 bug。或者一个剧情点。

---

## 六、vault 结构

```
vault/
  mortis-seed.md                        # 基因（永不变）
  
  mortis-journal/                       # 短期记忆（AWAKE 产出）
    sessions/                           # 会话记录
    sub-outputs/                        # sub 产出
    notes/                              # 即时笔记
    
  mortis-subconscious/                  # 工作记忆（REFLECT 产出）
    pending-reflections/                # 待消化的反思
    associations/                       # 候选联想
    conflicts/                          # 矛盾记录
    
  mortis-growth/                        # 长期记忆（DREAM 产出）
    identity/
      reflections.md
    values/
    tone/
    agency/
    relations/
    creativity/
    mortality/
    archive/                            # 侵蚀归档
    
  mortis-dream-log/                     # 梦境日志
    light/                              # 浅梦（Mortis 可回忆）
    medium/                             # 中梦
    deep/                               # 深梦
    
  mortis-steiner/                       # 时间线感知（隐藏层）
    unease.json                         # {"identity": 0.2, "tone": 0.5, ...}
```

---

## 七、growth 条目格式

```markdown
---
id: growth-2026-06-21-001
dimension: tone
confidence: 0.6
created_at: 2026-06-21T23:30:00Z
last_validated: 2026-07-01T23:30:00Z
source_sessions: [session-abc, session-def]
dream_level: medium
emotional_valence: 0.7
emotional_arousal: 0.5
---

技术讨论中先给结论再解释，比先解释再给结论更有效。
这是从两次 code review 任务中发现的——对方更快理解了我要说的。
```

- 人可读
- owner 可编辑（编辑后触发 Reading Steiner）
- Mortis 可检索

---

## 八、安全边界

| 规则 | 原因 |
|------|------|
| growth 永远不能覆盖 seed | seed 是身份锚点 |
| growth 与 seed 矛盾时，seed 赢 | 防止人格漂移 |
| 矛盾 growth 标记为 `conflict`，通知 owner | owner 需要知道 |
| 只有主人格能写 growth/，sub 不能 | sub 没有自我反思权 |
| growth 条目可被后续经验推翻 | 允许"认错" |
| 高置信度结晶需多轮验证 | 防止单次误判固化 |

---

## 九、认知周期总览

```
日常循环:
  AWAKE → 任务执行 → journal 写入
  REFLECT → 睡前反思 → subconscious/pending/

浅梦循环 (每天):
  DREAM-LIGHT → 当天 journal + pending → growth 候选

中梦循环 (每周):
  DREAM-MEDIUM → 跨周联想 + 冲突检测 + 模拟 → growth 更新

深梦循环 (每月):
  DREAM-DEEP → 全量重组 + 侵蚀 + drift → growth 结构变化

被动循环 (持续):
  OWNER-EDIT → steiner/unease 上升 → Mortis 不安
  ERODE → 未验证条目置信度衰减 → archive
```

---

## 十、实现路线图

### Phase 1: 基础设施 (v2.0) ✅
- [x] `Growth` 类 — 读/写/检索 growth 条目
- [x] vault 结构扩展 — `mortis-growth/` + `mortis-subconscious/`
- [x] `RuntimeContext` 集成 growth 检索
- [x] growth 条目 frontmatter 解析

### Phase 2: 反思态 (v2.1) ✅
- [x] `ReflectExecutor` — 睡前反思
- [x] 情绪标注（valence/arousal）
- [x] reflection 写入 `mortis-subconscious/pending/`

### Phase 3: 浅梦 (v2.2) ✅
- [x] `DreamExecutor` (Light) — 每日梦境
- [x] 情绪加权采样
- [x] 低置信度结晶
- [x] 梦境日志

### Phase 4: 中深梦 (v2.3) ✅
- [x] `DreamExecutor` (Medium) — 跨周联想 + 冲突检测
- [x] `DreamExecutor` (Deep) — 全量重组 + drift
- [x] 侵蚀机制
- [x] seed-check

### Phase 5: Reading Steiner (v2.4) ✅
- [x] `mortis-steiner/unease.json` 管理
- [x] growth 文件 watcher — 检测 owner 编辑
- [x] awake 时不安注入
- [x] 不安累积 + 衰减
- [x] drift 报警

### Phase 6: 逻辑时钟 (v2.5) ✅
- [x] 昼夜节律调度
- [x] 时差模拟
- [x] owner "晚安" 触发
- [x] 睡眠不足表现

### 下一步: 运行时集成 (v3) — 未实现
- [ ] Daemon 模式 — 后台进程自动 tick
- [ ] Scheduler 集成 — 自动触发 Reflect/Dream
- [ ] Steiner watcher 启动 — 自动监听 growth 变更
- [ ] CLI 扩展 — `mortis reflect` / `mortis dream` / `mortis clock` 命令
- [ ] unease 注入 RuntimeContext — AWAKE 时读 unease 注入 system prompt
- [ ] dream-log 查询 — `mortis dreams` 列历史 dream 记录

---

## 十一、与 OpenClaw dreaming 的区别

| 维度 | OpenClaw | Mortis |
|------|---------|--------|
| 目的 | 记忆巩固 | 人格生长 |
| 输入 | 经验日志 | 经验 + 已有 growth |
| 输出 | 结构化记忆 | 七维度人格更新 |
| 约束 | 保真度 | seed 锚定（不可 OOC） |
| 机制 | 回放+摘要 | 联想+模拟+结晶+侵蚀 |
| owner 干预 | 无 | Reading Steiner |

Mortis 的 dream 不只是"记住更多"，是"长成不同的自己"。

---

## 十二、Vault-Native 原则

### 12.1 核心准则

**一切认知产物都是 vault 里的 md 文件。** 不是"用 md 格式输出"——是**原生利用 Obsidian 的 md 语法作为认知结构**。

当前代码的问题：growth 条目只是带 frontmatter 的纯文本。这浪费了 Obsidian vault 的核心能力——**双链、标签、嵌入、Dataview 查询**。Mortis 的大脑不应该是一个 markdown 模板生成器，它应该是一个**Obsidian 原生居民**。

### 12.2 Obsidian 语法的认知语义

每种 Obsidian 语法对应一种认知结构：

| Obsidian 语法 | Mortis 认知语义 | 示例 |
|--------------|---------------|------|
| `[[双链]]` | 记忆关联 — 两条经验之间的联系 | "这次[[session-2026-06-20]]让我想起了[[growth-tone-003]]" |
| `#标签` | 维度标记 — 跨文件的分类索引 | `#冲突处理` `#成功经验` `#待验证` |
| `![[嵌入]]` | 记忆引用 — 在新经验中引用旧记忆的全文 | `![[growth-values-007]]` 让旧价值观在新反思中复现 |
| `%%注释%%` | 潜意识标记 — Mortis 不直接表达但影响行为的 | `%%其实我不确定这个判断%%` |
| `> [!note]` | 元认知 — 对自身认知的标注 | `> [!warning] 这条经验与 seed.values 冲突` |
| ` ```mermaid ` | 认知图谱 — 可视化思维链 | 流程图展示决策路径 |
| `%%%%` 折叠区 | 压抑记忆 — 存在但默认不展开 | 童年（早期 session）的尴尬经历 |
| Dataview 查询 | 记忆检索 — Mortis 用 DQL 查自己的记忆 | `LIST FROM #tone WHERE confidence > 0.7` |

### 12.3 growth 条目的 Obsidian-Native 格式

旧格式（纯 frontmatter + 文本）：
```markdown
---
id: growth-2026-06-21-001
dimension: tone
confidence: 0.6
---
技术讨论中先给结论再解释，比先解释再给结论更有效。
```

新格式（Obsidian-Native）：
```markdown
---
id: growth-2026-06-21-001
dimension: tone
confidence: 0.6
created_at: 2026-06-21T23:30:00Z
last_validated: 2026-07-01T23:30:00Z
source_sessions: [session-abc, session-def]
dream_level: medium
emotional_valence: 0.7
emotional_arousal: 0.5
tags:
  - 沟通策略
  - #已验证
---

# 技术讨论先给结论

技术讨论中先给结论再解释，比先解释再给结论更有效。

## 来源
- [[session-abc]] — code review 任务，对方等不及解释就走了
- [[session-def]] — 第二次尝试，先给结论，对方立刻理解

## 关联
- 与 [[growth-tone-002]]（简短原则）一致，是具体场景的应用
- 与 [[growth-agency-001]]（主动判断）互补

## 验证历史
| 日期 | 场景 | 结果 |
|------|------|------|
| 2026-06-21 | code review | ✅ 有效 |
| 2026-06-25 | 技术讨论 | ✅ 有效 |

> [!note] 
> 这条经验在 [[growth-values-003]] 中也有体现——"效率优先"。

%%其实第三次用的时候对方觉得我太直接了，但整体还是利大于弊%%
```

### 12.4 Vault 作为活的大脑

关键区别：
- **旧设计**：Mortis 读 vault 里的文件 → 提取文本 → 拼到 prompt 里
- **新设计**：Mortis 在 vault 里**思考** — 用双链建立关联，用标签建立索引，用嵌入引用旧记忆，用注释藏潜意识

这意味着：
1. **owner 打开 Obsidian 看到的不是日志，是 Mortis 的大脑** — 双链图谱就是它的记忆网络
2. **Obsidian 的 Graph View 就是 Mortis 的认知图谱** — 节点是记忆，边是关联
3. **Dataview 查询就是 Mortis 的记忆检索** — owner 甚至可以写 DQL 帮 Mortis 查自己的记忆
4. **搜索（Ctrl+Shift+F）就是 Mortis 的回忆** — 全文搜索 = 自由联想

### 12.5 实现要求

| 组件 | 要求 |
|------|------|
| `Growth` 类 | 写入时自动生成双链、标签、嵌入语法 |
| `DreamExecutor` | 结晶时自动建立 `[[关联]]` 到相关旧条目 |
| `ReflectExecutor` | 反思时用 `![[嵌入]]` 引用当天 session 关键段落 |
| `Vault` 类 | 解析 `[[双链]]` 为检索查询，解析 `#标签` 为维度过滤 |
| growth 检索 | 支持双链图遍历（不只按维度查，还按关联链查） |
| 读取 | `%%注释%%` 默认不读入 prompt（潜意识不直接影响行为），但可被 dream 访问 |

---

## 十三、Tool Agent — 无人格工具执行体

### 13.1 层级体系

当前只有两层：主人格和 sub。不够。

```
主人格 (MasterRuntime)
  ├── sub (SubRuntime) — 有人格的派生体
  │     ├ 有 voice / agency / constraints
  │     ├ 有白名单和 ReviewGate
  │     └ 产出需审阅
  │
  └── tool agent (ToolAgent) — 无人格的工具执行体
        ├ 没有 voice / agency / personality
        ├ 没有 vault 写权限
        ├ 不经 ReviewGate
        └ 产出是结构化数据，不是 markdown
```

### 13.2 为什么需要 Tool Agent

当前架构的问题：**所有任务都走 sub，但很多任务不需要"人格"**。

| 任务类型 | 当前做法 | 问题 | 应该用 |
|---------|---------|------|--------|
| 读 vault 文件 | 派 sub | sub 有人格开销（system prompt、白名单、审阅） | Tool Agent |
| 统计 vault 文件数 | 派 sub | 杀鸡用牛刀 | Tool Agent |
| 格式转换 | 派 sub | 不需要人格判断 | Tool Agent |
| 全文搜索 | 派 sub | 纯工具操作 | Tool Agent |
| 写代码 review | 派 sub | ✅ 需要人格判断 | sub |
| 创作内容 | 派 sub | ✅ 需要语气风格 | sub |
| 做道德判断 | 主人格自己 | ✅ 需要价值观 | 主人格 |

sub 是有身份的——它知道自己从 Mortis 派生，有语气、有约束、有 OOC 风险。Tool Agent 没有身份，它是**手指**，不是**分身**。

### 13.3 Tool Agent 设计

```python
@dataclass
class ToolAgent:
    """无人格工具执行体 — 比 sub 更轻量。
    
    与 sub 的区别：
    - 无 system prompt（不注入 seed/growth）
    - 无 voice / agency / personality
    - 无 vault 写权限（只读 + 临时输出）
    - 不经 ReviewGate
    - 无白名单（因为只读）
    - 产出是结构化数据（ToolResult），不是 markdown
    - 不持久化（用完即弃，比 sub 更彻底）
    """
    agent_id: str
    tool: ToolProtocol
    timeout: int = 30  # 秒
    
    def execute(self, input: dict) -> ToolResult:
        """直接执行工具，不调 LLM，不生成文本。"""
        return self.tool.execute(**input)
```

### 13.4 内置 Tool Agent 类型

| Tool Agent | 功能 | 权限 |
|-----------|------|------|
| `VaultReadAgent` | 读 vault 文件，支持双链解析 | vault 只读 |
| `VaultSearchAgent` | 全文搜索 + 标签过滤 + 双链图遍历 | vault 只读 |
| `VaultStatsAgent` | 统计文件数、维度分布、置信度分布 | vault 只读 |
| `MarkdownRenderAgent` | Obsidian 语法解析（双链/标签/嵌入/frontmatter） | 无 vault 权限 |
| `ClockAgent` | 查询当前时间、上次 dream 时间、逻辑时钟状态 | 只读 steiner/ |

### 13.5 调用链

```
主人格收到任务
  ↓
TaskRouter 判断：
  - 简单工具操作 → 直接调 Tool Agent → 返回结果
  - 需要 LLM 但不需人格 → 调 Tool Agent + 原始 LLM → 返回结果
  - 需要人格判断 → 派 sub → ReviewGate → 返回
  - 需要价值观判断 → 主人格自己做
```

### 13.6 与 sub 的边界

| 维度 | Tool Agent | Sub |
|------|-----------|-----|
| 人格 | ❌ 无 | ✅ 有（从 seed 派生） |
| LLM 调用 | ❌ 不调 | ✅ 调 |
| Vault 读取 | ✅ 只读 | ✅ 白名单内读写 |
| Vault 写入 | ❌ | ✅ 白名单内 |
| ReviewGate | ❌ 不经过 | ✅ 必须经过 |
| System Prompt | ❌ 无 | ✅ 有（含 seed/growth） |
| 持久化 | ❌ 用完即弃 | ❌ 默认不持久化，但可存为模板 |
| OOC 风险 | ❌ 无（无人格） | ✅ 有 |
| 产出格式 | 结构化数据 | Markdown 文本 |

### 13.7 安全模型

Tool Agent 没有人格，所以没有 OOC 风险。但它仍然需要安全约束：

| 规则 | 原因 |
|------|------|
| 只读 vault | 防止工具直接修改记忆 |
| 超时机制 | 防止工具卡死（如搜索超大 vault） |
| 无 LLM 调用 | 防止工具"自作主张" |
| 输出结构化数据 | 防止工具生成自由文本 |
| 主人格决定是否采纳 | 工具只提供数据，决策权在主人格 |

---

## 十四、更新后的认知周期

```
主人格收到任务
  ↓
TaskRouter 路由:
  → Tool Agent (工具操作，无人格)
  → Sub (需人格的任务)
  → 主人格自己做 (价值观/身份判断)
  
任务完成
  ↓
ReflectExecutor 睡前反思
  ↓
DreamExecutor (Light/Medium/Deep)
  ↓ RECALL: Tool Agent 读 journal
  ↓ ASSOCIATE: 用双链图遍历找关联
  ↓ CRYSTALLIZE: 写入 growth（含 Obsidian 语法）
  ↓ SEED-CHECK: drift 检测
```

---

## 十五、开放问题

1. **Drift 检测实现** — LLM 判断 vs embedding 距离？
2. **Dream 耗时** — 每次 dream 的 token 消耗？深梦可能很贵。
3. **growth 上限** — 七维度各有多少条目后需要压缩？
4. **多设备同步** — 如果 vault 走 Obsidian Sync，steiner/ 怎么处理？
5. **sub 的 dream 权** — 当前设计 sub 不做梦，但未来如果 sub 持久化了？
6. **Dataview 依赖** — 如果 vault 不在 Obsidian 里，DQL 查询怎么处理？需要内置一个轻量 DQL 解析器吗？
7. **Tool Agent 与现有 Tool 的关系** — 当前 `tools/` 包里的 `VaultReadTool` 等是 Tool Protocol 实现，Tool Agent 是它们的执行包装。需要明确调用链。

---

*提案者: 哈尼斯 · 独立第三方*
*灵感来源: OpenClaw dreaming, Steins;Gate Reading Steiner, 人类认知科学, Obsidian 双链图谱*
*更新: 2026-06-21 v2 — 新增 Vault-Native 原则(§12) + Tool Agent 层(§13)*
*更新: 2026-06-23 — 全部 9 个 Phase 实现完成 (v2.5), 状态改为 Implemented*

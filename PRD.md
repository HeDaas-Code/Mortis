---
title: Mortis PRD
type: prd
version: v0
status: draft
created: 2026-06-20
last_updated: 2026-06-20
---

# Mortis PRD — Vault-borne Growing Agent

## Problem Statement

用户（owner）需要一个 **长期存在、可成长、但永不偏离人设的智能体**——

- 它应该**随时间积累经验**（不是僵化的纯 prompt）
- 它应该有**独立人格**（不是用户的复制品 / 不是越来越像用户）
- 它应该**严格不 OOC**——seed 一旦确定，经验不能腐蚀人设
- 它应该能**委派任务给临时 sub 智能体**——sub 由主人格生成、由主人格审阅、由主人格管理生死

现有方案（如 LangChain agent、AutoGPT、CrewAI）的不足：

| 现有方案 | 不足 |
|---|---|
| LangChain Agent | 没有"人设不可变"概念——prompt 改了，agent 就变了 |
| AutoGPT | 没有"主人格/sub"分层——所有决策都是单一 agent |
| CrewAI | 多 agent 但每个独立——没有"派生/继承"关系 |
| Character.AI / SillyTavern | 单一角色扮演——无"任务委派/经验积累" |
| 通用 Agent 框架 | 无"vault 作为认知系统"概念——把 vault 当数据库 |

Mortis 的差异化：

1. **vault = 主体认知系统**——不是数据存储，是主体的"脑子"
2. **seed md = 不可变人设**——OOC 防御核心
3. **mortis 工作架构**——主人格→sub 人格→sub 智能体三层委派
4. **sub 全权管理**——主人格决定 sub 的存档/丢弃/合并/编辑
5. **白名单授权**——sub 只能动主人格授权的范围

## Solution

构建一个 Python 智能体框架——**Mortis**——提供：

1. **vault 抽象层**——任何目录都能成为 vault（首版支持 Obsidian vault、本地目录）
2. **主人格引擎**——读 seed md，生成系统 prompt
3. **mortis 工作架构**——L0/L1/L2 模板链委派 sub 智能体
4. **sub 智能体执行器**——隔离工作区 + 白名单授权
5. **vault 写入审核**——sub 产出草稿，主人格审过才入正式 vault
6. **CLI 入口**——`python -m mortis --vault ~/vault` 启动

## User Stories

### 主人格创建与维护

1. 作为 owner，我想写一份 seed md（主人格人设），让 Mortis 知道我是谁
2. 作为 owner，我想验证 seed md 的完整性（必含字段检查），让 setup 不漏关键信息
3. 作为 owner，我想修改 seed md，让主人格人设升级，但旧经验不被误删
4. 作为 owner，我想看到 seed md 与经验/关系的清晰分层，让 vault 不混乱
5. 作为 owner，我想给主人格起名字，让它有"自我"
6. 作为 owner，我想配置 LLM 后端（OpenAI/Anthropic/国内），让主人格用合适的模型

### Vault 管理

7. 作为主人格，我想扫描 vault 找到 seed md，让主人格知道自己从哪里定义
8. 作为主人格，我想读 vault 内的笔记作为"经验"输入，让 sub 能调用相关上下文
9. 作为 vault 主权，我想拒绝非法访问（sub 越界），让 vault 安全
10. 作为 owner，我想看 vault 的权限矩阵（哪些 sub 授权了什么），让权限清晰

### Mortis 工作架构

11. 作为主人格，看到任务 X 时，我想分类决定是否需要 sub，让简单任务自己处理
12. 作为主人格，需要 sub 时，我想从 L0 模板生成 L1 通用模板，让 sub 设计风格匹配我
13. 作为主人格，需要工作 sub 时，我想从 L1 模板生成 L2 具体实例，让 sub 针对当前任务
14. 作为主人格，我想签发白名单给 sub，让 sub 只动授权范围
15. 作为主人格，我想在 sub 工作时监督，让 sub 不会走偏
16. 作为主人格，sub 完成后，我想审阅产出，决定采纳/丢弃/合并/编辑，让 sub 不污染 vault
17. 作为主人格，我想把优秀 sub 存为模板，让下次复用

### Sub 智能体生命周期

18. 作为 sub，我知道自己从哪个主人格派生，让我不冒充主人格
19. 作为 sub，我在隔离工作区执行，让我不污染正式 vault
20. 作为 sub，我只能访问主人格白名单授权的范围，让我不越权
21. 作为 sub，我完成任务后产出草稿，等待主人格审阅，让主人格保持最终决定权
22. 作为 sub，我的"生死"由主人格决定，让我服从主人格

### CLI 与可观测性

23. 作为 owner，我想用 CLI 启动 Mortis 并指定 vault 路径，让我能跑自己的 vault
24. 作为 owner，我想看到主人格当前状态（哪些 sub 在跑 / 历史任务 / 经验统计），让我能观察
25. 作为 owner，我想看主人格的 LLM 调用日志，让我能调试和优化
26. 作为 owner，我想把主人格的产出导出为 markdown，让我能二次编辑

### 多模型与扩展

27. 作为 owner，我想给不同任务配不同模型（如主人格用 GPT-4，sub 用 GPT-3.5），让我平衡成本/性能
28. 作为 owner，我想未来加 LangChain/LlamaIndex 中间层（v2+），让我换模型不重写
29. 作为 owner，我想未来加 Obsidian 插件（v3+），让我在 Obsidian 里直接用

## Implementation Decisions

### 模块结构（v0 骨架）

```
src/
├── mortis/
│   ├── __init__.py
│   ├── vault/              # vault 抽象层
│   │   ├── __init__.py
│   │   ├── base.py         # Vault 抽象基类
│   │   ├── local.py        # 本地目录实现
│   │   └── obsidian.py     # Obsidian vault 实现（v1+）
│   ├── persona/            # 主人格引擎
│   │   ├── __init__.py
│   │   ├── master.py       # MasterPersona 类
│   │   ├── seed.py         # seed md 加载/校验
│   │   └── prompt.py       # 系统 prompt 生成
│   ├── mortis_arch/        # mortis 工作架构
│   │   ├── __init__.py
│   │   ├── templates.py    # L0/L1/L2 模板链
│   │   ├── delegator.py    # 委派逻辑
│   │   └── sub_persona.py  # SubPersona 类
│   ├── agent/              # sub 智能体执行器
│   │   ├── __init__.py
│   │   ├── sub_agent.py    # SubAgent 类
│   │   ├── workspace.py    # 隔离工作区
│   │   └── permission.py   # 白名单授权
│   ├── review/             # 主人格审核
│   │   ├── __init__.py
│   │   └── gate.py         # ReviewGate
│   ├── llm/                # LLM 后端（v0 简版，v1+ 抽 langchain）
│   │   ├── __init__.py
│   │   ├── backend.py      # LLMBackend 接口
│   │   └── openai.py       # OpenAI 实现
│   ├── cli.py              # CLI 入口
│   └── config.py           # 配置加载
└── tests/
    ├── unit/
    └── integration/
```

### 关键接口（v0）

```python
# Vault 抽象
class Vault(Protocol):
    def read(self, path: str) -> str: ...
    def write(self, path: str, content: str, review: bool = True) -> bool: ...
    def list(self, pattern: str) -> List[str]: ...
    def exists(self, path: str) -> bool: ...

# 主人格
class MasterPersona:
    def __init__(self, vault: Vault, seed_path: str = "seed.md"): ...
    def system_prompt(self) -> str: ...  # 永远从 seed 生成
    def classify_task(self, task: str) -> TaskType: ...  # 自己处理 vs 委派 sub
    def delegate(self, task: str) -> SubAgent: ...

# Mortis 架构
@dataclass
class SubPersona:
    parent_seed_hash: str  # 锚定主人格（OOC 检测）
    template_layer: Literal["L0", "L1", "L2"]
    persona_md: str
    created_at: datetime

# Sub 智能体
class SubAgent:
    def __init__(self, persona: SubPersona, vault: Vault, permission: Permission): ...
    def run(self, task: str) -> SubOutput: ...  # 在隔离工作区
    def submit(self) -> DraftOutput: ...  # 产出草稿，等主人格审

# 主人格审核
class ReviewGate:
    def review(self, draft: DraftOutput) -> ReviewDecision: ...
    # ReviewDecision: Adopt | Discard | Merge(sub_ids=[...]) | Edit(new_md=...)
```

### 关键不变量（代码层强制）

1. **seed md 永远只读**——`MasterPersona` 构造时加载一次，运行期不改
2. **sub 不能直接 write vault**——必须走 `ReviewGate`
3. **sub 必须有 `parent_seed_hash`**——构造时强制，hash 不匹配 = OOC
4. **白名单是 vault 操作前的强制检查**——`Permission.check(vault_op)`

### LLM 后端（v0）

- **v0 简版**：直连 OpenAI API（HTTP 调用）
- **v1+**：抽象 `LLMBackend` 接口，可插 OpenAI/Anthropic/国内
- **不引 LangChain**——v0 避免依赖污染

### Owner 优先级

```python
# ReviewDecision 优先级
OWNER_OVERRIDE = "owner_override"  # owner 永远可 override 主人格决策
```

## Testing Decisions

### 单元测试范围

- `vault/local.py`：读写、列表、权限
- `persona/seed.py`：必含字段校验、hash 计算
- `persona/master.py`：系统 prompt 生成、任务分类
- `mortis_arch/templates.py`：L0/L1/L2 模板链正确性
- `agent/permission.py`：白名单强制检查
- `review/gate.py`：4 种审核决策

### 集成测试

- 端到端：seed md → 任务 → sub 委派 → 隔离执行 → 审核 → vault 写入
- OOC 防御：尝试修改 seed md → 应被拒
- 白名单越界：sub 尝试访问未授权文件 → 应被拒

### 测试原则

- **只测外部行为**，不测实现细节
- 不 mock LLM——用真实 API（小模型 + 小 prompt 控制成本）
- 不依赖网络——本地 vault 测试

## Out of Scope

v0 不做（明确划线）：

- ❌ Obsidian 插件（v3+）
- ❌ LangChain/LlamaIndex 中间层（v1+）
- ❌ 多 LLM 后端路由（v1+）
- ❌ sub 智能体跨进程并发（v0 单进程串行）
- ❌ Web UI（v0 CLI only）
- ❌ 多 vault（v0 单 vault）
- ❌ 远程 owner 同步（v0 本地）

## Further Notes

### 命名文化背景

**Mortis** 来自日本动画《Ave Mujica》中角色**若叶睦**的精神分裂子人格：

| 动画设定 | 项目映射 |
|---|---|
| 若叶睦 = 本体 | owner / 主体 |
| Mortis = 睦派生的子人格 | sub 人格 / sub 智能体 |
| Mortis 知道自己从睦派生 | sub 知道自己从主人格派生 |
| Mortis 在任务中存在 | sub 在任务生命周期内活动 |
| 睦对 Mortis 有完全控制 | 主人格对 sub 全权管理 |
| Mortis 不冒充睦 | sub 严格不冒充主人格 |

参考：《BanG Dream! It's MyGO!!!!!》+《BanG Dream! Ave Mujica》动画系列（2023-2024）。

### 路线图

- **v0（当前）**：骨架——vault 抽象 + 主人格引擎 + mortis 架构核心
- **v1**：LangChain 抽象 + Obsidian vault 实现
- **v2**：多 LLM 后端 + sub 并发调度
- **v3**： Web UI

### 后续

- 把本 PRD 转为 GitHub issue 体系（v0-issue-1 ~ v0-issue-N）
- 每个 issue 由 agent 实现 → owner 验收
- 实现完成后归档到 docs/adr/
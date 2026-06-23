# HARNESS.md — Mortis 开发 Harness

> 本文件是 Mortis 项目的**开发上下文锚点**。任何 AI agent (Cursor Claude / MiniMax / 哈尼斯) 在动手改代码前必须先读本文件。

## 项目快照

- **仓库**: HeDaas-Code/Mortis
- **状态**: v2.5 — RFC-001 全部 9 Phase 实现 + 审计修复完成
- **代码规模**: ~9100 行源码 + ~6400 行测试, 482 tests passed
- **总览 issue**: #65 (v3 全量计划)
- **当前阶段**: v3.0 运行时集成 (Milestone #4)

## 架构速查

```
mortis/
├── seed/         不可变七维度人设 (OOC 防御)
├── vault/        Obsidian-native vault (双链/标签/折叠/注释解析)
├── growth/       七维度成长记忆 (frontmatter CRUD)
├── memory/       Session / Thread / StepRecord 三级会话
├── provider/     LLM 抽象 (MiniMax + Mock)
├── runtime/      MasterRuntime / SubRuntime / RuntimeContext
├── pipeline/     Think→Plan→Act→Review 编排 + TaskRouter
├── tools/        ToolProtocol + ToolRegistry (LLM tool calling)
├── reflect/      ReflectExecutor (睡前反思 + 情绪标注)
├── dream/        Light/Medium/Deep 三级梦境 + 7 Phase pipeline
├── steiner/      Reading Steiner (unease + watcher + drift)
├── clock/        LogicalClock + Scheduler + SleepState
└── toolagent/    5 内置 Tool Agent (⚠ #63 #64 待重构)
```

## 开发约定

### 分支命名

```
feature/<功能>     — 新功能 (对应 feat issue)
fix/<问题>         — bug 修复 (对应 bug issue)
docs/<任务>        — 纯文档
```

### Commit 规范

```
feat(<模块>): <中文简述> (issue #N) (#PR)
fix(<模块>): <中文简述> (issue #N) (#PR)
docs(<模块>): <中文简述>
chore: <中文简述>
```

### 代码约定

- 代码注释 / docstring / issue / PR: **中文**
- 变量 / 函数 / 类命名: **英文** (Python 惯例)
- docstring 必须标注 issue 编号: `"""issue #NN: ..."""`
- 每个模块 `__init__.py` 必须有 `__all__`
- 测试文件: `tests/test_<模块>.py`, 一个 test file 对应一个 source module

### 测试要求

- **PR 合并前必须 482+ tests passed** (不能回归)
- 新功能必须带测试
- bug fix 必须带回归测试 (编码错误行为 → 修代码同时修测试)
- MockProvider 模式下全部可测试 (不依赖真实 API key)
- 日期相关测试用动态 `datetime.now()`, 不硬编码日期

### Issue/PR 工作流

```
1. 认领 issue → 改 label: status:needs-triage → status:in-progress
2. 建分支: git checkout -b feature/<功能>
3. 开发 + 测试: pytest --tb=short
4. 推送 + 开 PR
5. PR 合并 → 关闭 issue → 更新 tracking issue
6. 删本地分支: git branch -D <branch>
```

## 已知架构债务

| Issue | 严重度 | 描述 |
|-------|--------|------|
| #63 | P1 bug | ToolAgent 全不调 LLM, 缺 provider 注入 |
| #64 | P1 bug | TaskRouter 关键词路由是架构错误, 应注册为 ToolProtocol |

## v3 关键路径

```
#63 → #64 → #59 → (v3.0 完成) → #52 → #53
```

**#63 是全局第一个该做的 issue。**

## 多 Agent 协作

本项目同时使用多个 AI agent 开发:

| Agent | 角色 | 擅长 |
|-------|------|------|
| Cursor Claude | 主力开发 | 写代码 + 重构 |
| MiniMax-M3 (Hermes) | 辅助开发 | review + 方案讨论 |
| 哈尼斯 (本 agent) | 独立审计 | 架构分析 + bug 发现 |

**协作规则**:
- 各 agent 独立工作, 不串供
- 发现 bug 开 issue, 不直接改其他 agent 的分支
- 认领 issue 前检查没人已经在做 (看 `status:in-progress` label + open PR)
- PR review 可以互相做, 但合并由 owner 决定

## Harness 工具

```bash
# 认领 issue + 建分支
python tools/dev.py claim <issue_number>

# 运行测试 (合并前检查)
python tools/dev.py test

# 创建 PR
python tools/dev.py pr <issue_number> --title "标题"

# 查看当前 issue 全貌
python tools/dev.py issues

# 合并后清理
python tools/dev.py cleanup <pr_number>
```

## 文件索引

| 文件 | 用途 |
|------|------|
| `HARNESS.md` (本文件) | 开发上下文锚点 — agent 必读 |
| `AGENTS.md` | Agent skills 配置 (Hermes / Matt Pocock) |
| `CONTEXT.md` | 领域术语表 |
| `PRD.md` | 产品需求文档 |
| `README.md` | 项目 README (对外) |
| `docs/rfc/` | RFC 文档 |
| `docs/agents/` | Agent 配置 (issue tracker / labels / domain) |
| `tools/dev.py` | 开发自动化工具 |

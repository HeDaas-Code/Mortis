---
title: Mortis Agent Skills Configuration
type: agents-config
status: active
last_updated: 2026-06-20
---

# AGENTS.md — Mortis Agent Skills Configuration

> 本文件配置 Mortis 项目使用 Hermes / Matt Pocock engineering skills 所需的项目级上下文。

## Agent skills

### Issue tracker

项目使用 GitHub Issues。详见 [[docs/agents/issue-tracker]]。

### Triage labels

Matt Pocock 默认 5 类状态机标签。详见 [[docs/agents/triage-labels]]。

### Domain docs

单上下文布局——根 `CONTEXT.md` + `docs/adr/`。详见 [[docs/agents/domain]]。

## 沟通约定

- **本项目代码、注释、issue/PR 标题使用中文**
- **变量/函数命名使用英文**（Python 业界惯例）
- **Commit message**：`feat: <中文简述>` / `fix: <中文简述>` / `chore: <中文简述>` / `docs: <中文简述>`
- **分支命名**：`feature/<功能>` / `fix/<问题>` / `chore/<任务>`

## 项目性质

**Mortis** = 一个基于 vault 的生长型智能体——核心创新是 mortis 工作架构（主→sub 人格委派）。

**注意**：vault 是主人格的"认知系统"，不是用户的笔记库——sub 智能体在 vault 内活动，主人格全权管理。

详见 [[PRD]]。

## 快速命令

```bash
# 安装依赖
pip install -e ".[dev]"

# 测试
python tools/dev.py test          # 或直接 pytest

# 认领 issue + 建分支
python tools/dev.py claim <issue_number>

# 创建 PR
python tools/dev.py pr <issue_number>

# 查看 open issues
python tools/dev.py issues

# 当前开发状态
python tools/dev.py status
```

## 关联文件

- **[[HARNESS]]** — 开发 harness 上下文锚点 (agent 必读)
- [[README]] — 仓库根 README
- [[PRD]] — 项目 PRD（产品需求文档）
- [[CONTEXT]] — 项目领域术语
- [[docs/agents/issue-tracker]] — issue 配置
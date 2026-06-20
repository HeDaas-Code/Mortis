---
title: Mortis Domain Docs
type: agents-config
parent: AGENTS.md
---

# Domain Docs

**单上下文布局**——`CONTEXT.md`（根） + `docs/adr/`（入仓） + `工作Wiki/`（不入仓）。

## 何时开 ADR

- 引入新依赖（langchain/llamaindex 选型）
- 改变 mortis 架构核心（vault/seed/sub 关系）
- 改变 L0 硬编码模板
- 改变 sub 智能体白名单机制
- 改变 owner 优先级规则

## 何时不开

- bug fix
- 文档更新
- 工具脚本
---
title: Mortis 领域术语表
type: context
status: active
last_updated: 2026-06-20
---

# CONTEXT.md — Mortis 领域术语表

## 项目核心概念

### Mortis

vault-borne growing agent——基于 vault 生长出来的智能体。

**命名来源**：日本动画《Ave Mujica》中角色若叶睦的精神分裂子人格 "Mortis"——对应项目的 sub 人格概念。

### Vault（vault）

**主主体的认知系统**——不是用户的笔记库，是 vault 主体的"脑子"。

类比：
- 人对自己的记忆 = owner 对 vault 的访问
- vault 内的所有笔记/记忆/经验 = 主体认知的一部分

### 主人格（Master Persona / Seed）

vault 的核心意识，由 **seed md** 锚定。

**关键不变量**：
- seed md 不可变（OOC 防御核心）
- 主人格对 vault 有完全控制权
- owner 永远高优先级（可 override 主人格决策）

### Sub 人格

由主人格按任务派生的临时/永久人格。

**生命周期**（主人格全权）：
- **存档**：永久保留为模板（进 sub 人格库）
- **丢弃**：任务结束销毁
- **合并**：多个 sub 人格特征合成新 sub
- **编辑**：修改已存在的 sub 人格

### Sub 智能体

装载 sub 人格的执行体。

**关键约束**：
- 仅主人格授权的白名单（vault 隔离）
- 隔离工作区执行
- 产出是草稿，需主人格审过才入正式 vault

### Mortis 工作架构

**三层模板链**：
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

**关键特性**：sub 智能体可并发执行，主人格监督。

## 不混淆概念

- **Mortis ≠ 若叶睦（动画本体）**——前者项目，后者动画角色
- **vault ≠ Obsidian vault**——Mortis 不限于 Obsidian，vault 是抽象存储层
- **主人格 ≠ owner**——前者是被创建的，后者是创建者
- **sub 人格 ≠ sub 智能体**——前者是设定，后者是执行实体
- **L1 ≠ L2**——L1 是设计模板，L2 是具体实例

## 项目特定命名

| 术语 | 含义 |
|---|---|
| **seed md** | 主人格的不可变核心（必含：我是谁/核心身份/owner 关系/工作方式/成长规则） |
| **白名单授权** | sub 智能体可访问的 vault 范围（主人格签发） |
| **sub 人格库** | 主人格管理的累积 sub 模板集合（可存档/合并/编辑） |
| **OOC** | Out of Character——主人格/sub 偏离人设 |
| **vault 主权** | 主人格对 vault 的完全控制权 |

## 待补

- [ ] L0 硬编码模板内容（首版）
- [ ] seed md 必含字段（首版）
- [ ] vault 与 Obsidian 适配方案
- [ ] sub 并发调度策略
# Mortis

> **Mortis — A Mortal That Lives In Your Vault**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Status: v0 draft](https://img.shields.io/badge/status-v0%20draft-orange)]()

**Vault-borne growing agent.** Ownerable, seed-grown, never OOC.

---

## 这是什么

Mortis 是一个 **基于 vault 生长出来的智能体**——

- **vault** 是它的"认知系统"（不是数据存储，是它的"脑子"）
- **seed md** 是它的不可变人设核心（OOC 防御）
- **mortis 工作架构** 让它能委派任务给 sub 智能体
- **sub 全由主人格管理**——存档 / 丢弃 / 合并 / 编辑

## 核心特性

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

### 🔒 OOC 防御

- **seed md 不可变**——系统 prompt 永远从 seed 重新生成
- **sub 必须锚定主人格**——构造时校验 `parent_seed_hash`
- **白名单授权**——sub 不能越权访问 vault

### 👁️ Owner 永远优先

- vault 是 owner 创建的
- 主人格知道自己的"生死"在 owner 手上
- 主人格服从 owner 但保留自己的判断

## 快速开始

```bash
# 1. 准备 vault（任何目录都行）
mkdir ~/my-vault && cd ~/my-vault
# 写 seed.md（必含：我是谁/核心身份/owner 关系/工作方式/成长规则）

# 2. 启动 Mortis
pip install mortis
python -m mortis --vault ~/my-vault
```

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

## 路线图

- **v0**（当前）：骨架——vault 抽象 + 主人格引擎 + mortis 架构核心
- **v1**：LangChain 抽象 + Obsidian vault 实现
- **v2**：多 LLM 后端 + sub 并发调度
- **v3**：Obsidian 插件 + Web UI

## 文档

- [[PRD]] — 产品需求文档
- [[CONTEXT]] — 项目领域术语
- [[docs/agents/issue-tracker]] — issue 追踪配置
- [[工作Wiki/README]] — 工作 Wiki 入口（本地）

## 许可

MIT
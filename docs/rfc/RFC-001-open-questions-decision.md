# RFC-001 §15 开放问题裁剪记录

> 日期: 2026-06-21
> 决策人: HeDaas (owner)
> 上下文: [#16 RFC-001](https://github.com/HeDaas-Code/Mortis/issues/16) + [decomposition plan](./RFC-001-decomposition.md)

RFC-001 §十五列出 7 个开放问题。owner 拍板 **全部裁剪（暂不实现）**，理由逐条记录：

## 1. Drift 检测实现 — LLM 判断 vs embedding 距离

**决定**: 暂不实现具体方案，先用最简 LLM 自评。

**理由**:
- 项目**无 embedding 基础设施**——要从零搭 sentence-transformers / chromadb / faiss，**v2.0 范围过载**
- LLM 自评够用 v2.0 / v2.1 —— 让 provider 输出 "drift 0~1 分"，**80 分优先**
- Embedding 是 v3.0 工作 —— 第一个月看真实数据再决定

**触发重审**: 当 drift 报警误报率 > 30% 时

## 2. Dream 耗时 / token 消耗

**决定**: 不实现任何优化，在 deploy/README 里讨论。

**理由**:
- 这不是 feature 问题，是 ops 决策
- v2.0 没真实数据前，**优化 = 拍脑袋**
- 第一个月看实际 token 账单再决定（rate limit / 缓存策略 / 异步化）

**触发重审**: 当月度 dream token 成本 > $X 时（owner 决定阈值）

## 3. Growth 上限 / 七维度压缩

**决定**: 不实现上限逻辑。

**理由**:
- **这是 policy 不是 feature** —— 多少条 growth 算"太多"是 owner 审美问题
- 没有真实数据前设上限 = 拍脑袋
- 侵蚀机制（#23）已经在做"自然衰减"，**等价于软上限**

**触发重审**: 当某维度 growth > 50 条时人工 review

## 4. 多设备同步 — steiner/ 处理

**决定**: 不实现，由 owner 工具链决定。

**理由**:
- **Obsidian Sync 是 owner 选型不是 Mortis 的事**
- steiner/ 是 `mortis-steiner/unease.json` 单文件，**Obsidian Sync 处理 JSON 没问题**
- 如果将来要拆 steiner/ 到独立 storage，需要 RFC-002

**触发重审**: 当 owner 用 Obsidian Sync + 多设备出现矛盾时

## 5. Sub 的 dream 权

**决定**: 不实现，按 RFC §13 设计"sub 默认不持久化所以不做梦"。

**理由**:
- 这是独立大题 —— **应该单独 RFC-002**，混进 RFC-001 会让 #18-#26 工作量翻倍
- 当前 sub 范式（用完即弃）**没"人格延续"需求**
- 如果将来 sub 持久化，先开 RFC-002 单独讨论

**触发重审**: 当 owner 明确提出"sub 应该做梦"需求时

## 6. Dataview 内置解析器

**决定**: 不实现，只解析基础 Obsidian 语法（双链/标签/嵌入/折叠/注释）。

**理由**:
- Dataview 是 **Obsidian 插件** 不是 md 标准 —— 强加 DQL = 破坏 vault-native 原则
- Owner 在 Obsidian 里手写 DQL 查自己的记忆 —— **这是 feature 不是 bug**
- Mortis 自己查 vault 用 Python 解析，不走 DQL

**触发重审**: 当 owner 多次抱怨"Mortis 不会查 DQL"时

## 7. Tool Agent 与现有 Tool 的关系

**决定**: Tool Agent 是现有 Tool Protocol 的执行包装（RFC §13.3 设计），不改变现有 `mortis/tools/` 接口。

**理由**:
- `mortis/tools/` 是 LLM 可调用的 Tool（带 schema）
- Tool Agent 是 **无人格执行体**（不带 schema，直接 execute）
- **两者并存不冲突**—— Tool 给 LLM 看，Tool Agent 给主人格直接用
- Issue #25 会明确两者的调用链

**触发重审**: 当出现 "Tool 和 Tool Agent 重复实现" 时

---

## 总览

| 问题 | 决定 | 重审触发 |
|---|---|---|
| 1. Drift embedding | LLM 自评 | 误报 > 30% |
| 2. Dream token | README 讨论 | 月成本超阈值 |
| 3. Growth 上限 | 不实现 | 某维度 > 50 |
| 4. 多设备同步 | owner 工具链 | 出现矛盾 |
| 5. Sub dream 权 | RFC-002 单独讨论 | 需求出现 |
| 6. Dataview 解析 | 不实现 | owner 抱怨 |
| 7. Tool Agent 边界 | 走 RFC §13.3 | 重复实现 |

## 影响

**RFC-001 §15 在 issue #16 标记为 "owner-decided-deferred"**。所有 7 项均不在 #18-#26 工作量内。
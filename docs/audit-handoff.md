# Mortis 审计交接文档（2026-06-21）

> 本文件记录 v0.2.0 阶段的**两次独立审计**与一次完整盘点，供后续 owner / agent 接手时参考。
>
> **目的**：让接手的人（人或 agent）能立刻知道"为什么这些 commit 存在"、"还有哪些问题没修"、"RFC-001 是什么状态"。

---

## 时间线

| 时间 | 事件 |
|---|---|
| 2026-06-20 | 项目立项（commit `4b360b4` Mortis v0 骨架） |
| 2026-06-20 → 21 上午 | v1 闭环 + v2 重构（commit `868f543` → `9f80798`） |
| 2026-06-21 06:30 | **第一次审计**（Hermes / MiniMax-M3）—— 发现 5 条 Critical #6-#10 |
| 2026-06-21 07:31 | Hermes 关 #6 + push 5 commit |
| 2026-06-21 09:00 | **第二次审计**（第三方"哈尼斯 / hanis"）—— 发现 3 条新 Critical #11-#13 + 接管 #7-#10 |
| 2026-06-21 10:13 | RFC-001 认知生长系统（设计稿，未实现）|
| 2026-06-21 15:38 | 本次盘点（同步后）|

## 第一次审计（Hermes）

### 范围
- commit `9f80798`（v2 重构后状态）
- 8 子包架构 + 73 测试 + 2450 行代码

### 输出
- 报告：TBD（未保存到 docs；2026-06-21 chat session）
- 5 条 Critical issue（#6-#10）
- 多条 Warning（跨包 re-export、token 截断等）

### 实际改动
- 3 commit（vault 子包首次入库 + whitelist 下沉 + 12 测试）
- issue #6 闭环

### 漏掉的（被 Hanis 发现）
- **S1**: Vault.write 路径遍历（`../` 可写任意文件）
- **S2**: whitelist 可被 `../` 绕过
- **S3**: discard_sub_output 可删任意文件
- **#7-#10**: 4 条 Critical 没动手

### 教训
- 第一次审计"白名单下沉"只看了**白名单本身**，没看**路径解析**
- **白名单 + 路径遍历 = 两个独立漏洞**，必须同时防御

## 第二次审计（Hanis）

### 范围
- commit `74a2ddc`（Hermes 完成后状态）

### 输出
- PR #14（路径安全）+ PR #15（sub 治理链）
- 7 个 issue 一次性关单（#7-#13）
- 42 个新测试（23 + 19）
- RFC-001 v1（认知生长系统）

### 关键贡献

| Issue | 问题 | 修复 |
|---|---|---|
| **S1 / #11** | Vault.write 路径遍历 | `_safe_path()` + `resolve()` + `relative_to()` |
| **S2 / #12** | 白名单 `../` 绕过 | `_normalize()` 归一化路径 |
| **S3 / #13** | discard 删任意文件 | 走 `_safe_path()` |
| **#7** | PipelineExecutor 不调 ReviewGate | `_run_delegated` 末尾 review + apply |
| **#8** | SubTemplate 可任意构造 | `SubTemplate.from_seed()` 自动注入 `parent_seed_hash` |
| **#9** | OWNER_OVERRIDE 缺失 + MERGE/EDIT stub | 完整实现 + `master_review()` / `owner_override()` |
| **#10** | L2 模板链缺失 | `L2SubTemplate` + `verify_chain()` |

### 仍未修（Hanis 也没动）
- 跨包 re-export（provider → tools 反向依赖，审计 Warning #2）
- messages_for_provider 无 token 截断（审计 Warning #1）
- RFC-001 落地实施（设计稿，未实现）

## 当前仓库状态（2026-06-21 18:42 UTC）

```
HEAD:     d0d8f32 (RFC-001 v2)
分支:     main（与 origin 同步）
测试:     127/127 PASS
git tree: 线性主干（2 个 merge commit，无冲突）
```

### 仓库结构
```
mortis/
├── cli/        CLI 入口
├── memory/     Session/Thread/Archive
├── pipeline/   Think/Plan/Act/Review + Executor + Router
├── provider/   LLM 抽象（mock + minimax + registry）
├── runtime/    MasterRuntime + SubRuntime + SubTemplate + L2SubTemplate
├── seed/       七维度人格种子
├── tools/      Tool Protocol + Registry + Vault tools
└── vault/      本地存储 + 白名单 + ReviewGate
docs/
├── agents/     Matt Pocock 工程流配置
├── adr/        架构决策记录（v0+v1 时期）
└── rfc/
    └── RFC-001-cognitive-growth.md  (Hanis, 630 行)
tests/
├── test_layers.py              (20)
├── test_pipeline_chain.py      (19, Hanis)
├── test_providers.py           (20)
├── test_seed.py                (18)
├── test_vault.py               (27, 15 旧 + 12 新)
└── test_vault_security.py      (23, Hanis)
```

## Issue 状态（截至盘点）

| # | 标题 | 状态 | 解决方 |
|---|---|---|---|
| 1-5 | v0+v1 issues | CLOSED | 项目初期 |
| **6** | 白名单下沉 | CLOSED | Hermes |
| **7-10** | Critical 链 | CLOSED | Hanis PR #15 |
| **11-13** | 路径安全 | CLOSED | Hanis PR #14 |
| **16** | RFC-001 认知生长系统 | **OPEN, needs-triage** | Hanis 提的 RFC |

## 未完成工作

### P2: RFC-001 落地（issue #16, status: needs-triage）
- 630 行 RFC 文档，描述三态意识 + 梦境分级 + Reading Steiner + Tool Agent 层
- **owner 需决策**：是否进 v2.1 实施？分几期？

### P3: 仍存在的 Warning
- **跨包 re-export**：`mortis/provider/__init__.py` 反向依赖 `mortis/tools/base.py`
- **token 截断**：`RuntimeContext.messages_for_provider()` 重建全量历史，无摘要/sliding window

### P3: vault 包首次入库的连锁影响
- v2 重构时因 `.gitignore` `vault/` 误伤 `mortis/vault/`，整个子包未入库
- 已在 `d7b41f9` 修复（首次跟踪 vault 包）
- **未开 issue 跟踪**（建议补一个 docs/audit 类 issue 留档）

## commit 命名规范（沿用至今）

| type | 用途 | 例子 |
|---|---|---|
| `feat` | 新功能 | `feat(vault): whitelist 强制下沉到 Vault 层` |
| `fix` | 修 bug | `fix(vault): 修复 3 个 CRITICAL 路径安全漏洞` |
| `chore` | 杂项（.gitignore、清理）| `chore: 删除过时 decision-qa` |
| `docs` | 仅文档 | `docs(rfc): RFC-001 认知生长系统` |
| `test` | 仅测试 | `test(vault): 覆盖 whitelist 强制下沉` |

## 接手 checklist

如果你是新 agent / 新 owner，要继续推进：

1. [ ] 拉最新：`git pull origin main`
2. [ ] 跑测试：`python3 -m pytest`（应 127/127 PASS）
3. [ ] 看 RFC-001（`docs/rfc/RFC-001-cognitive-growth.md`）判断是否进 v2.1
4. [ ] 看 issue #16（needs-triage）做分类决策
5. [ ] 考虑是否补 issue："vault 包首次入库"作为独立 audit 记录
6. [ ] 评估 Warning：跨包 re-export / token 截断是否要单独立 issue

## 联系方式

- 项目 owner: Hedaas (HeDaas-Code)
- 第一次审计: Hermes / MiniMax-M3 (本 agent)
- 第二次审计: 哈尼斯 (独立第三方)
- Co-authored-by 标记已落 commit

## 写在最后

Mortis v0.2.0 经过两次独立审计（Hermes + Hanis），所有 CRITICAL 漏洞已修复，测试 127/127 PASS。

唯一 OPEN 的是 RFC-001（设计稿），等待 owner 决策是否进入 v2.1 实施。

后续如果要做 RFC-001 的实现，建议**先做一次 architectural review**，因为它涉及 vault 结构大改（新增 `growth/` `subconscious/` `dream-log/` `steiner/` 四个子目录），影响范围比 #6-#13 都大。
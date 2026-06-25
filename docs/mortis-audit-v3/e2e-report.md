# Mortis v3 全项 E2E 生产级实验报告

> **E2E EXPERIMENT REPORT** | 开始: 2026-06-25T03:46:58.829082+00:00 | 结束: 2026-06-25T03:51:44.505945+00:00 | 总耗时: 285.7s
> Provider: MinimaxProvider (MiniMax-M3, 真实 API 调用)

## 实验摘要

| 指标 | 值 |
|------|-----|
| 总步骤 | 25 |
| 通过 | 25 |
| 失败 | 0 |
| 通过率 | 100.0% |
| LLM 调用总数 | 44 |
| 步骤总耗时 | 285.67s |

### 按类别统计

| 类别 | 总数 | 通过 | 失败 |
|------|:----:|:----:|:----:|
| provider | 3 | 3 | 0 |
| pipeline | 3 | 3 | 0 |
| toolagent | 5 | 5 | 0 |
| reflect | 1 | 1 | 0 |
| dream | 5 | 5 | 0 |
| security | 5 | 5 | 0 |
| steiner | 2 | 2 | 0 |
| clock | 1 | 1 | 0 |

## 实验步骤详情

| 步骤 | 类别 | 名称 | 状态 | 耗时 | LLM | 详情/错误 |
|------|------|------|:----:|:----:|:---:|----------|
| E2E-01 | provider | Provider 连通性（minimax generate_text） | ✓ PASS | 6.25s | 1 | 响应长度 156 字符，包含 '2': True |
| E2E-02 | provider | Provider generate(messages) 多轮 | ✓ PASS | 3.87s | 1 | role=assistant, content 长度 60 |
| E2E-03 | provider | Provider async_generate_text（issue #46） | ✓ PASS | 2.12s | 1 | 异步响应包含 '4': True |
| E2E-04 | pipeline | Pipeline 简单任务（Think→Plan→Act→Review） | ✓ PASS | 9.83s | 4 | steps=3, delegated=True, output 长度 42 |
| E2E-05 | pipeline | Pipeline + 工具调用（vault:read_agent） | ✓ PASS | 17.79s | 4 | tool_calls=0, output 长度 42 |
| E2E-06 | toolagent | VaultReadAgent + 摘要（issue #63 LLM） | ✓ PASS | 6.31s | 1 | summary 长度 80 |
| E2E-07 | toolagent | VaultSearchAgent 语义搜索（issue #63 LLM + redact） | ✓ PASS | 4.07s | 1 | matches=1, summary 长度 78 |
| E2E-08 | toolagent | VaultStatsAgent + LLM 分析（issue #63 LLM） | ✓ PASS | 50.11s | 1 | total_files=3, analysis=有 |
| E2E-09 | toolagent | ClockAgent（纯工具，无 LLM） | ✓ PASS | 0.00s | 0 | current_time=2026-06-25T03:48:39.178097+00:00 |
| E2E-10 | toolagent | MarkdownRenderAgent（纯解析，无 LLM） | ✓ PASS | 0.00s | 0 | parsed keys=['wikilinks', 'embed_links', 'tags', 'callouts', 'frontmatter'] |
| E2E-11 | reflect | ReflectExecutor（REFLECT phase LLM） | ✓ PASS | 62.12s | 2 | 反思输出长度 5891, valence=0.00 |
| E2E-12 | dream | LightDreamer 4 phase（RECALL→ASSOCIATE→CRYSTALLIZE→SEED-CHECK） | ✓ PASS | 14.32s | 4 | dream 输出长度 505 |
| E2E-13 | dream | MediumDreamer 5 phase（+SIMULATE） | ✓ PASS | 12.50s | 5 | dream 输出长度 581 |
| E2E-14 | dream | DeepDreamer 7 phase（+RECONCILE+ERODE） | ✓ PASS | 8.90s | 7 | dream 输出长度 739 |
| E2E-15 | dream | seed_check + redact（issue #84 CRITICAL） | ✓ PASS | 12.01s | 1 | total_drift=0.60, needs_notify=False |
| E2E-16 | security | growth preview + redact（issue #85） | ✓ PASS | 0.00s | 0 | prompt 长度 152, redact 后无 emotional_: True |
| E2E-17 | security | redact 共享模块（issue #83 6 patterns） | ✓ PASS | 0.00s | 0 | ✓ > [!dream]
> 私密梦境内容; ✓ > [!secret]
> 私密内容; ✓ [emotion:joy@0.8] 文本; ✓ %%subconscious%%
隐藏
%%/subcons; ✓ emotional_valence: 0.8 应被脱敏; ✓ dream_level: deep 应被脱敏; ✓ normal text 正常文本不应被脱敏 |
| E2E-18 | security | Vault 白名单 + 路径遍历防护（S1/S2/S3 + #67） | ✓ PASS | 0.00s | 0 | 3/3 攻击路径被拦截 |
| E2E-19 | security | VaultReadAgent blocked_prefixes（issue #38/#68/#80） | ✓ PASS | 0.00s | 0 | 3/3 受限路径被阻断 |
| E2E-20 | security | Provider 审计日志 hash（issue #87） | ✓ PASS | 0.00s | 0 | messages_hash=66136c2cb6eeb45e, sha256_prefix=6aa8f49cc992dfd7 |
| E2E-21 | steiner | Steiner GrowthWatcher 编辑检测（issue #24/#58） | ✓ PASS | 0.00s | 0 | unease accumulate 完成，无异常 |
| E2E-22 | steiner | unease 注入 RuntimeContext（issue #57） | ✓ PASS | 0.00s | 0 | unease prompt 长度 0 |
| E2E-23 | clock | LogicalClock 时段状态机（issue #26/#34） | ✓ PASS | 0.00s | 0 | 09:00=awake, 22:00=reflect, 03:00=dream_deep |
| E2E-24 | dream | growth 维度压缩（issue #47 LLM 间接） | ✓ PASS | 0.00s | 1 | 压缩结果 keys=['compressed', 'merged'] |
| E2E-25 | pipeline | 完整认知周期 AWAKE→REFLECT→DREAM_LIGHT | ✓ PASS | 75.47s | 10 | awake_output=42, reflect=4650, dream=498 |

## 覆盖的 LLM 调用点（审计报告 §02）

| # | 调用点 | 位置 | E2E 步骤 |
|---|--------|------|:--------:|
| 1 | ThinkStep | pipeline/step.py | E2E-04/05/25 |
| 2 | PlanStep | pipeline/step.py | E2E-04/05/25 |
| 3 | ReviewStep | pipeline/step.py | E2E-04/05/25 |
| 4 | VaultReadAgent._summarize | toolagent/vault_read.py | E2E-06 |
| 5 | VaultSearchAgent._semantic_rerank | toolagent/vault_search.py | E2E-07 |
| 6 | VaultStatsAgent._analyze_stats | toolagent/vault_stats.py | E2E-08 |
| 7 | SeedChecker.check | dream/seed_check.py | E2E-15 |
| 8 | ReflectExecutor | reflect/executor.py | E2E-11/25 |
| 9 | LightDreamer | dream/light.py | E2E-12/25 |
| 10 | MediumDreamer | dream/medium.py | E2E-13 |
| 11 | DeepDreamer | dream/deep.py | E2E-14 |

## 覆盖的安全机制

| 机制 | Issue | E2E 步骤 |
|------|-------|:--------:|
| redact 共享模块 | #83 | E2E-17 |
| growth preview redact | #85 | E2E-16 |
| seed_check redact | #84 | E2E-15 |
| Vault 白名单 + 路径遍历 | S1/S2/S3/#67 | E2E-18 |
| VaultReadAgent blocked_prefixes | #38/#68/#80 | E2E-19 |
| Provider 审计日志 hash | #87 | E2E-20 |

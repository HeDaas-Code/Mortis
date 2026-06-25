# Mortis v3 全项 E2E 生产级实验报告

> **E2E EXPERIMENT REPORT** | 开始: 2026-06-25T09:20:07.336884+00:00 | 结束: 2026-06-25T09:23:12.779390+00:00 | 总耗时: 185.4s
> Provider: MinimaxProvider (MiniMax-M3, 真实 API 调用)

## 实验摘要

| 指标 | 值 |
|------|-----|
| 总步骤 | 31 |
| 通过 | 28 |
| 失败 | 3 |
| 通过率 | 90.3% |
| LLM 调用总数 | 43 |
| 步骤总耗时 | 185.44s |

### 按类别统计

| 类别 | 总数 | 通过 | 失败 |
|------|:----:|:----:|:----:|
| provider | 3 | 2 | 1 |
| pipeline | 3 | 3 | 0 |
| toolagent | 5 | 5 | 0 |
| reflect | 1 | 1 | 0 |
| dream | 5 | 5 | 0 |
| security | 5 | 5 | 0 |
| steiner | 2 | 2 | 0 |
| clock | 1 | 1 | 0 |
| web | 6 | 4 | 2 |

## 实验步骤详情

| 步骤 | 类别 | 名称 | 状态 | 耗时 | LLM | 详情/错误 |
|------|------|------|:----:|:----:|:---:|----------|
| E2E-01 | provider | Provider 连通性（minimax generate_text） | ✗ FAIL | 0.00s | 0 | **ERROR**: RuntimeError: 期望 MinimaxProvider，实际 LoggingProvider（MINIMAX_API_KEY 未设置？） |
| E2E-02 | provider | Provider generate(messages) 多轮 | ✓ PASS | 1.39s | 1 | role=assistant, content 长度 60 |
| E2E-03 | provider | Provider async_generate_text（issue #46） | ✓ PASS | 1.19s | 1 | 异步响应包含 '4': True |
| E2E-04 | pipeline | Pipeline 简单任务（Think→Plan→Act→Review） | ✓ PASS | 7.51s | 4 | steps=3, delegated=True, output 长度 42 |
| E2E-05 | pipeline | Pipeline + 工具调用（vault:read_agent） | ✓ PASS | 12.00s | 4 | tool_calls=0, output 长度 42 |
| E2E-06 | toolagent | VaultReadAgent + 摘要（issue #63 LLM） | ✓ PASS | 2.33s | 1 | summary 长度 80 |
| E2E-07 | toolagent | VaultSearchAgent 语义搜索（issue #63 LLM + redact） | ✓ PASS | 5.25s | 1 | matches=1, summary 长度 175 |
| E2E-08 | toolagent | VaultStatsAgent + LLM 分析（issue #63 LLM） | ✓ PASS | 22.59s | 1 | total_files=3, analysis=有 |
| E2E-09 | toolagent | ClockAgent（纯工具，无 LLM） | ✓ PASS | 0.00s | 0 | current_time=2026-06-25T09:20:59.613264+00:00 |
| E2E-10 | toolagent | MarkdownRenderAgent（纯解析，无 LLM） | ✓ PASS | 0.00s | 0 | parsed keys=['wikilinks', 'embed_links', 'tags', 'callouts', 'frontmatter'] |
| E2E-11 | reflect | ReflectExecutor（REFLECT phase LLM） | ✓ PASS | 27.94s | 2 | 反思输出长度 3829, valence=0.00 |
| E2E-12 | dream | LightDreamer 4 phase（RECALL→ASSOCIATE→CRYSTALLIZE→SEED-CHECK） | ✓ PASS | 8.53s | 4 | dream 输出长度 506 |
| E2E-13 | dream | MediumDreamer 5 phase（+SIMULATE） | ✓ PASS | 9.72s | 5 | dream 输出长度 582 |
| E2E-14 | dream | DeepDreamer 7 phase（+RECONCILE+ERODE） | ✓ PASS | 8.81s | 7 | dream 输出长度 727 |
| E2E-15 | dream | seed_check + redact（issue #84 CRITICAL） | ✓ PASS | 12.96s | 1 | total_drift=0.70, needs_notify=False |
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
| E2E-25 | pipeline | 完整认知周期 AWAKE→REFLECT→DREAM_LIGHT | ✓ PASS | 64.68s | 10 | awake_output=42, reflect=5036, dream=496 |
| E2E-26 | web | Web UI server 启动 + dashboard（issue #52） | ✗ FAIL | 0.01s | 0 | status=200, phase=awake, growth_count=6, endpoints=4<br>**ERROR**:  |
| E2E-27 | web | GET /growths + /growths/<rel>（growth 浏览器, issue #53） | ✗ FAIL | 0.01s | 0 | 列表 total=6, 详情 id=None, dimension=None<br>**ERROR**:  |
| E2E-28 | web | GET /unease（unease 仪表盘, issue #53） | ✓ PASS | 0.00s | 0 | max_unease=0.82, identity=0.45, 7 维度=7 |
| E2E-29 | web | GET /notifications（owner 通知通道, issue #54） | ✓ PASS | 0.00s | 0 | notifications=2, 首条 type=drift |
| E2E-30 | web | GET /dreams（dream 日历, issue #53） | ✓ PASS | 0.00s | 0 | dreams=3, levels={'medium', 'light', 'deep'} |
| E2E-31 | web | GET /unknown (404) + 数据流转校验 + server 关闭 | ✓ PASS | 0.51s | 0 | 404=True, 数据流转(vault↔HTTP)=True, server 已关闭 |

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

## 覆盖的 Web UI 交互入口（issue #52/#53/#54）

| 端点 | 方法 | 功能 | E2E 步骤 |
|------|------|------|:--------:|
| / | GET | dashboard 仪表盘 (phase+unease+growth 概览) | E2E-26 |
| /growths | GET | growth 浏览器 (列表, 50 条预览) | E2E-27 |
| /growths/<rel> | GET | growth 详情 (含 emotional_*, owner 视角) | E2E-27 |
| /unease | GET | unease 仪表盘 (7 维度 + max + last_decay) | E2E-28 |
| /notifications | GET | owner 通知通道 (drift/unease/dream) | E2E-29 |
| /dreams | GET | dream 日历 (light/medium/deep 分组) | E2E-30 |
| /unknown | GET | 404 路由兜底 | E2E-31 |
| — | — | 数据流转校验 (vault 原文 ↔ HTTP 返回一致) | E2E-31 |

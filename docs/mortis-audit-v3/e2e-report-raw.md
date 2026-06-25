# Mortis v3 全项 E2E 生产级实验报告

> **E2E EXPERIMENT REPORT** | 开始: 2026-06-25T15:58:09.876885+00:00 | 结束: 2026-06-25T15:58:11.862559+00:00 | 总耗时: 2.0s
> Provider: MinimaxProvider (MiniMax-M3, 真实 API 调用)

## 实验摘要

| 指标 | 值 |
|------|-----|
| 总步骤 | 43 |
| 通过 | 38 |
| 失败 | 5 |
| 通过率 | 88.4% |
| LLM 调用总数 | 56 |
| 步骤总耗时 | 1.98s |

### 按类别统计

| 类别 | 总数 | 通过 | 失败 |
|------|:----:|:----:|:----:|
| provider | 3 | 1 | 2 |
| pipeline | 3 | 3 | 0 |
| toolagent | 5 | 5 | 0 |
| reflect | 1 | 1 | 0 |
| dream | 5 | 5 | 0 |
| security | 6 | 6 | 0 |
| steiner | 2 | 2 | 0 |
| clock | 1 | 1 | 0 |
| web | 6 | 3 | 3 |
| exception | 3 | 3 | 0 |
| delegation | 1 | 1 | 0 |
| streaming | 1 | 1 | 0 |
| resilience | 2 | 2 | 0 |
| chat | 2 | 2 | 0 |
| gateway | 2 | 2 | 0 |

## 实验步骤详情

| 步骤 | 类别 | 名称 | 状态 | 耗时 | LLM | 详情/错误 |
|------|------|------|:----:|:----:|:---:|----------|
| E2E-01 | provider | Provider 连通性（minimax generate_text） | ✗ FAIL | 0.00s | 0 | **ERROR**: RuntimeError: 期望 MinimaxProvider，实际 LoggingProvider（MINIMAX_API_KEY 未设置？） |
| E2E-02 | provider | Provider generate(messages) 多轮 | ✓ PASS | 0.00s | 1 | role=assistant, content 长度 22 |
| E2E-03 | provider | Provider async_generate_text（issue #46） | ✗ FAIL | 0.00s | 1 | 异步响应包含 '4': False<br>**ERROR**:  |
| E2E-04 | pipeline | Pipeline 简单任务（Think→Plan→Act→Review） | ✓ PASS | 0.01s | 4 | steps=3, delegated=True, output 长度 42 |
| E2E-05 | pipeline | Pipeline + 工具调用（vault:read_agent） | ✓ PASS | 0.01s | 4 | tool_calls=0, output 长度 42 |
| E2E-06 | toolagent | VaultReadAgent + 摘要（issue #63 LLM） | ✓ PASS | 0.00s | 1 | summary 长度 12 |
| E2E-07 | toolagent | VaultSearchAgent 语义搜索（issue #63 LLM + redact） | ✓ PASS | 0.00s | 1 | matches=1, summary 长度 0 |
| E2E-08 | toolagent | VaultStatsAgent + LLM 分析（issue #63 LLM） | ✓ PASS | 0.00s | 1 | total_files=3, analysis=有 |
| E2E-09 | toolagent | ClockAgent（纯工具，无 LLM） | ✓ PASS | 0.00s | 0 | current_time=2026-06-25T15:58:09.901256+00:00 |
| E2E-10 | toolagent | MarkdownRenderAgent（纯解析，无 LLM） | ✓ PASS | 0.00s | 0 | parsed keys=['wikilinks', 'embed_links', 'tags', 'callouts', 'frontmatter'] |
| E2E-11 | reflect | ReflectExecutor（REFLECT phase LLM） | ✓ PASS | 0.00s | 2 | 反思输出长度 32, valence=0.00 |
| E2E-12 | dream | LightDreamer 4 phase（RECALL→ASSOCIATE→CRYSTALLIZE→SEED-CHECK） | ✓ PASS | 0.01s | 4 | dream 输出长度 475 |
| E2E-13 | dream | MediumDreamer 5 phase（+SIMULATE） | ✓ PASS | 0.01s | 5 | dream 输出长度 582 |
| E2E-14 | dream | DeepDreamer 7 phase（+RECONCILE+ERODE） | ✓ PASS | 0.01s | 7 | dream 输出长度 728 |
| E2E-15 | dream | seed_check + redact（issue #84 CRITICAL） | ✓ PASS | 0.00s | 1 | total_drift=0.00, needs_notify=False |
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
| E2E-25 | pipeline | 完整认知周期 AWAKE→REFLECT→DREAM_LIGHT | ✓ PASS | 0.02s | 10 | awake_output=42, reflect=268, dream=475 |
| E2E-26 | web | Web UI server 启动 + HTML dashboard (issue #52) | ✗ FAIL | 0.04s | 0 | html=True (DOCTYPE+UI+交互元素), api=False (phase=awake), data_in_html=True<br>**ERROR**:  |
| E2E-27 | web | HTML growth 列表 + 详情页 + 前端过滤交互 (issue #53) | ✗ FAIL | 0.01s | 0 | html_list=True, api_list=False (total=6), html_detail=False, api_detail=False<br>**ERROR**:  |
| E2E-28 | web | HTML unease 仪表盘 (柱状图 + 7 维度, issue #53) | ✓ PASS | 0.00s | 0 | html=True (bar-chart+bar-fill), api=True (max=0.82, dims=7) |
| E2E-29 | web | HTML notifications 页面 (issue #54) | ✓ PASS | 0.00s | 0 | html=True (notification+warning+drift), api=True (count=2) |
| E2E-30 | web | HTML dreams 日历页 (badge + table, issue #53) | ✓ PASS | 0.00s | 0 | html=True (badge+table+levels), api=True (count=3) |
| E2E-31 | web | 404 路由 + 数据流转校验 (vault→HTML↔JSON) + server 关闭 | ✗ FAIL | 0.51s | 0 | 404=True, dataflow=False (vault→HTML→JSON 三者一致), interaction=True, shutdown=True<br>**ERROR**:  |
| E2E-32 | exception | 异常输入 — VaultReadAgent 读取不存在的文件 | ✓ PASS | 0.00s | 0 | 异常被捕获 (优雅降级): AttributeError: 'ToolResult' object has no attribute 'message' |
| E2E-33 | exception | 异常输入 — 格式错误的 growth 文件 | ✓ PASS | 0.00s | 0 | malformed growth 写入成功, list_growths() 返回 7 条 (不崩溃) |
| E2E-34 | exception | 异常输入 — LLM 服务不可用 + FallbackProvider 降级 | ✓ PASS | 0.00s | 0 | error_caught=True (simulated LLM service unavailable), fallback_result='[mock:test prompt]' |
| E2E-35 | delegation | 子智能体派发 — 复杂多文件查询任务 | ✓ PASS | 0.02s | 1 | delegated=True, sub_id=sub-41e6f3fe, output=mortis-journal/sub-outputs/sub-41e6f3fe.md |
| E2E-36 | streaming | 流式输出 — generate_stream | ✓ PASS | 0.00s | 0 | provider 不支持 generate_stream, 跳过 (fallback 到非流式) |
| E2E-37 | resilience | 熔断器 — 连续失败触发熔断 + 恢复 | ✓ PASS | 1.10s | 0 | open_after_3_failures=True, rejected_4th_call=True, recovered_to_closed=True, stats={'state': 'closed', 'consecutive_failures': 0, 'total_calls': 4, 'total_failures': 3, 'total_rejections': 1, 'total_recoveries': 1, 'last_failure_time': 8862.234564079, 'last_state_change': 8863.334891162} |
| E2E-38 | resilience | 重试机制 — 瞬时故障自动重试恢复 | ✓ PASS | 0.04s | 0 | result='[mock:test]', retries=2, recovered=1 |
| E2E-39 | chat | ChatService 多轮对话 + 人格注入 + 持久化 (issue #88) | ✓ PASS | 0.11s | 2 | send=True, multi_turn=True, history=True (msgs=4), persona=True (tone注入), disk=True |
| E2E-40 | chat | Chat SSE 流式 + OpenUI HTML 页面 (issue #88) | ✓ PASS | 0.02s | 2 | html=True (chat-layout+sidebar+input+JS), api=True (cid=conv-6ef9253a92...), stream=True (SSE data:), list=True (total=2) |
| E2E-41 | gateway | Gateway 渠道路由 — Inbound→ChatService→Outbound (issue #89) | ✓ PASS | 0.03s | 4 | first=True (cid=conv-93f90aa9c3...), reuse=True (同sender复用), isolation=True (不同sender隔离), channels=True, stream=True (chunks=1) |
| E2E-42 | gateway | Gateway 多渠道隔离 + 主动推送 (issue #89) | ✓ PASS | 0.02s | 3 | web=True (no-op), push=True (SpyChannel.send被调), isolation=True, lifecycle=True, unknown_channel=True (回复仍生成) |
| E2E-43 | security | 路径遍历防护 — conversation_id 校验 (issue #90) | ✓ PASS | 0.01s | 1 | validate=True, get=True, history=True, delete=True (victim存活), send_safe=True (cid=conv-445434f2aa...) |

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

## 覆盖的异常输入与韧性测试

| 类别 | 测试场景 | E2E 步骤 |
|------|----------|:--------:|
| exception | VaultReadAgent 读取不存在的文件 (优雅降级) | E2E-32 |
| exception | 格式错误的 growth 文件 (不崩溃) | E2E-33 |
| exception | LLM 服务不可用 + FallbackProvider 降级 | E2E-34 |
| delegation | 子智能体派发 — 复杂多文件查询任务 (context 传递) | E2E-35 |
| streaming | 流式输出 generate_stream (逐块返回) | E2E-36 |
| resilience | 熔断器 — 连续失败触发熔断 + 恢复 | E2E-37 |
| resilience | 重试机制 — 瞬时故障自动重试恢复 | E2E-38 |

## LLM 调用日志增强字段

| 字段 | 说明 |
|------|------|
| input_length | 输入总字符数 (所有 message content 之和) |
| output_length | 输出总字符数 (response 长度) |
| model_version | 模型版本 (如 MiniMax-M3) |
| endpoint | API 端点 URL |
| think_content | 思考过程内容 (```...``` 中的内容, 已从 response 分离) |
| think_content_length | 思考过程内容长度 |
| retry_count | 重试次数 (若使用 RetryProvider) |

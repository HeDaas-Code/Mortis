# Critical: ReviewGate.apply 接入 Pipeline 时未传 SUB_VAULT_WHITELIST（白名单最后一公里漏洞）

## 背景

2026-06-21 自审计发现。issue #7（PipelineExecutor 不调用 ReviewGate）的修复（commit `a94f057`，Hanis）引入了一个新漏洞：**`ReviewGate.apply` 落地到 `vault.write` 时没传 whitelist 参数**，导致 sub 治理链在最后一步失去白名单防护。

## 问题描述

`mortis/pipeline/executor.py:200-206` 调用 `ReviewGate.apply()` 时：

```python
target_rel = ReviewGate.apply(
    vault_entry_content=act_out.message,
    rel_path=sub_output_rel,
    result=review_result,
    vault_write_fn=lambda rel, content: self.ctx.vault.write(rel, content),  # ← 没传 whitelist
    vault_read_fn=lambda rel: self.ctx.vault.read(rel).content,
    vault_discard_fn=lambda rel: self.ctx.vault.discard_sub_output(rel),
)
```

`vault.write()` 在 `whitelist is None` 时**不强制检查**（issue #6 设计），所以这条路径绕过了白名单。

## 攻击路径

1. sub 完成任务 → 写入 `mortis-journal/sub-outputs/<sub_id>.md`（白名单内，OK）
2. ReviewGate 触发 `MERGE` / `EDIT` / `OWNER_OVERRIDE` 决策
3. 决策带 `target_rel` 指向白名单外（如 `private/diary.md`、`vault-owner-notes.md`）
4. `ReviewGate.apply` 调 `vault_write_fn(target_rel, content)` → `vault.write(rel, content)` → 无 whitelist 参数 → **写入成功**

**当前现实风险**：低（CLI 未接 `master_review` / `owner_override`，没人能传入恶意 `target_rel`）。

**架构风险**：中。**未来如果 CLI 加 `override` 命令**，这个漏洞立即可被利用。

## 受影响文件

- `mortis/pipeline/executor.py:200-206` — `vault_write_fn` lambda 没传 whitelist
- `mortis/vault/review.py:106-163` — `ReviewGate.apply` 签名没暴露 whitelist

## 验收标准

- [ ] `ReviewGate.apply` 新增 `vault_whitelist: tuple[str, ...] | None = None` 参数
- [ ] `vault_write_fn` / `vault_read_fn` / `vault_discard_fn` 调用时透传 whitelist（仅 `vault_write_fn` 必须传，read/discard 视情况）
- [ ] `PipelineExecutor._run_delegated` 调用 `ReviewGate.apply` 时传 `vault_whitelist=SUB_VAULT_WHITELIST`
- [ ] 新增测试：构造一个 `target_rel` 指向白名单外的 `ReviewResult`，验证 `apply` 抛 `VaultAccessDenied`
- [ ] 现有 127 测试 + 新增测试全 pass

## 关联

- issue #6（白名单下沉）— 提供了底层防御
- issue #7（Pipeline 接入 ReviewGate）— 引入了这个漏洞
- commit `a94f057`（Hanis PR #15）— 引入位置
- Hanis PR #14 + #15 整体审计视角（Hanis 没看到这一层）

## 修法建议（最小改动）

```python
# mortis/pipeline/executor.py:200-206
target_rel = ReviewGate.apply(
    vault_entry_content=act_out.message,
    rel_path=sub_output_rel,
    result=review_result,
    vault_write_fn=lambda rel, content: self.ctx.vault.write(
        rel, content, whitelist=SUB_VAULT_WHITELIST
    ),
    vault_read_fn=lambda rel: self.ctx.vault.read(rel, whitelist=SUB_VAULT_WHITELIST).content,
    vault_discard_fn=lambda rel: self.ctx.vault.discard_sub_output(rel, whitelist=SUB_VAULT_WHITELIST),
)
```

---

> Hermes (MiniMax-M3) 自审计生成（2026-06-21）。owner review 后决定是否发送。
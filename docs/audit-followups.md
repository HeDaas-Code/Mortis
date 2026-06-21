# Mortis 审计 Follow-ups

记录第三方审计建议里 **当前不修但留 trigger** 的观察。

每次有 follow-up 在这里新增一条。

---

## Follow-up #1 — ReviewGate.read_fn 不走白名单 (issue #17 审计遗留)

**审计人**: 哈尼斯（独立第三方）
**日期**: 2026-06-21
**来源 issue**: [#17](https://github.com/HeDaas-Code/Mortis/issues/17)
**状态**: 📋 parked — 等触发条件

### 哈尼斯原话

> `vault_read_fn` 和 `vault_discard_fn` 没有走 `_safe_write` 的白名单检查。
> 当前安全模型下不构成漏洞（read 只读，discard 只删 sub-output 原文件）。但如果未来 MERGE 需要读白名单外的已有文件做合并，会被 `FileNotFoundError` 而非 `VaultAccessDenied` 挡住——错误类型不对，排查时可能困惑。
> 建议后续在 `vault_read_fn` 也加白名单校验，保持错误类型一致性。

### 实测复现 (commit 时验证)

```python
result = ReviewResult(
    decision=ReviewDecision.MERGE,
    target_rel="私人笔记/2026-06-21.md",  # 白名单外
)
ReviewGate.apply(
    ...,
    vault_read_fn=lambda r: ...,
    vault_whitelist=("mortis-journal/sub-outputs/",),
)
```

**结果**:
- ✓ 抛 `VaultAccessDenied`(不是 `FileNotFoundError`)— Hanis 描述的"错误类型不对"不成立
- ✓ `_safe_write` 拦住,没有写出
- ⚠️ 但 `read_fn` **仍以恶意路径被调用** — 路径会进 vault 内部日志 / 异常 traceback

### 分级

| 维度 | 真实情况 | 等级 |
|---|---|---|
| 错误类型不一致 | 不成立 | 低 |
| 实际写出 | 不成立 | 无 |
| read_fn 被以不可信路径调用 | 存在 | **中** |
| 信息泄露 / 日志污染 | 存在 | 中 |
| 未来 cache 风险 | 潜在 | 低 |

### 触发条件 (任一满足即修)

- [ ] CLI 增加 `master_review --target-rel` 命令
- [ ] Vault 实现 cache 层
- [ ] Vault 实现访问日志
- [ ] 实际用户报告 MERGE 路径异常困惑
- [ ] 任何 sub/owner 能动态指定 `target_rel` 写白名单外

### 修法预览 (届时启用)

```python
def _safe_read(target: str) -> str:
    if vault_whitelist is not None:
        if not VaultSecurity.check_whitelist(target, vault_whitelist):
            raise VaultAccessDenied(
                f"ReviewGate.apply: read target '{target}' 不在白名单"
            )
    return vault_read_fn(target)
```

替换 MERGE 分支的 `vault_read_fn(target)` → `_safe_read(target)`。
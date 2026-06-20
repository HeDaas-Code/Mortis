---
title: Mortis Triage Labels
type: agents-config
parent: AGENTS.md
---

# Triage Labels

Matt Pocock 默认 5 类：

| 标签 | 含义 |
|---|---|
| `status: ready-for-agent` | 需求清晰、上下文完整、owner 拍板 |
| `status: needs-triage` | 信息不全、需 owner 澄清 |
| `status: in-progress` | agent 已开 PR |
| `status: blocked` | 依赖外部（其他 issue / 上游 / owner） |
| `status: needs-human-review` | agent 完成后需 owner 验收 |

## 状态机

```
needs-triage → ready-for-agent → in-progress → needs-human-review → close
                  ↑                                 │
                  └──── blocked ←─────────────────────┘
```

## 特殊考量

Mortis 项目里 **"owner 拍板"** 尤其重要——因为主人格的"人设"涉及哲学/伦理决策（如"主人格可不可以撒谎？"），不能 agent 自主决定。
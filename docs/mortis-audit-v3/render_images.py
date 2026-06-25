"""渲染审计报告图片 — 白底黑字原则。

8 张图:
1. diagram-01-arch-layers.png — 14 子包分层依赖图
2. diagram-02-pipeline-flow.png — 主循环调用链
3. diagram-03-dream-pipeline.png — Dream 4-7 phase 流水线
4. diagram-04-signal-flow.png — 信号流主链
5. diagram-05-vault-defense.png — Vault 4 层纵深防御
6. diagram-06-task-flow.png — 复杂任务信息流转
7. diagram-07-dream-cycle.png — Dream 周期信息流
8. diagram-08-steiner-hidden.png — Steiner 隐藏层触发链
9. diagram-09-test-coverage.png — 测试覆盖热力图（新增）
10. diagram-10-timeline.png — 分支与 issue 时间轴（新增）

设计原则:
- 白底黑字（#FFFFFF 背景，#000000 文字）
- 灰阶 + 黑色描边
- 流转图细节充分（每个节点、每条边都标注）
"""
from __future__ import annotations

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.font_manager as fm
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle
from matplotlib.lines import Line2D
import os

# 注册中文字体
_FONT_PATH = "/root/.pyenv/versions/3.14.4/lib/python3.14/site-packages/mplfonts/fonts/NotoSansCJKsc-Regular.otf"
if os.path.exists(_FONT_PATH):
    fm.fontManager.addfont(_FONT_PATH)

# 全局白底黑字
plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "savefig.facecolor": "white",
    "savefig.edgecolor": "black",
    "text.color": "black",
    "axes.labelcolor": "black",
    "xtick.color": "black",
    "ytick.color": "black",
    "axes.edgecolor": "black",
    "font.family": "sans-serif",
    "font.sans-serif": ["Noto Sans CJK SC", "DejaVu Sans"],
    "axes.unicode_minus": False,
    "font.size": 9,
})

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")
os.makedirs(OUT_DIR, exist_ok=True)


def _box(ax, x, y, w, h, text, fc="#FFFFFF", ec="#000000", lw=1.2, fontsize=8, weight="normal"):
    """画一个圆角矩形框 + 居中文字。"""
    box = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.02,rounding_size=0.08",
        facecolor=fc, edgecolor=ec, linewidth=lw,
    )
    ax.add_patch(box)
    ax.text(x + w / 2, y + h / 2, text,
            ha="center", va="center", fontsize=fontsize, weight=weight, color="#000000")


def _arrow(ax, x1, y1, x2, y2, text="", style="->", lw=1.0, color="#000000", ls="-"):
    """画一条带箭头的线。"""
    arrow = FancyArrowPatch(
        (x1, y1), (x2, y2),
        arrowstyle=style, mutation_scale=12,
        color=color, linewidth=lw, linestyle=ls,
        shrinkA=2, shrinkB=2,
    )
    ax.add_patch(arrow)
    if text:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        ax.text(mx, my, text, fontsize=7, ha="center", va="center",
                color="#000000", bbox=dict(facecolor="white", edgecolor="none", pad=1))


def _setup_ax(figsize=(14, 10)):
    fig, ax = plt.subplots(figsize=figsize)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.set_aspect("equal")
    ax.axis("off")
    return fig, ax


# ============================================================
# Figure 1: 14 子包分层依赖图
# ============================================================
def render_01_arch_layers():
    fig, ax = _setup_ax((16, 11))
    ax.set_title("Figure 1 · 14 子包分层依赖图 — 自底向上 9 层",
                 fontsize=14, weight="bold", pad=20)

    # 9 层（自底向上）
    layers = [
        ("L0 · 零依赖底层", ["seed", "clock"], 5),
        ("L1 · 数据中枢", ["growth", "steiner*"], 18),
        ("L2 · vault 抽象", ["vault"], 31),
        ("L3 · 记忆与 provider", ["memory", "provider"], 44),
        ("L4 · 工具层", ["tools", "toolagent"], 57),
        ("L5 · 运行时", ["runtime"], 70),
        ("L6 · 编排层", ["pipeline"], 80),
        ("L7 · 认知态", ["reflect", "dream"], 88),
        ("L8 · 入口", ["cli", "web"], 96),
    ]

    # 画层背景
    for label, pkgs, y in layers:
        ax.add_patch(Rectangle((2, y - 4), 96, 8, facecolor="#F5F5F5",
                               edgecolor="#CCCCCC", linewidth=0.5))
        ax.text(3, y + 3, label, fontsize=8, color="#555555", weight="bold")
        # 画包
        n = len(pkgs)
        for i, pkg in enumerate(pkgs):
            x = 25 + i * (60 / max(n, 1))
            fc = "#FFFFFF"
            if pkg == "steiner*":
                fc = "#EEEEEE"  # 隐藏层用浅灰
            _box(ax, x, y - 2.5, 12, 5, pkg, fc=fc, fontsize=9, weight="bold")

    # 依赖箭头（关键）
    deps = [
        # growth -> seed, vault
        (31, 10, "growth→seed"),
        # vault -> growth
        (31, 22, "vault→growth"),
        # steiner -> growth (隐藏层)
        (37, 22, "steiner→growth"),
        # memory -> vault
        (44, 34, "memory→vault"),
        # provider -> tools (重导出 ToolResult)
        (50, 60, "provider→tools.base"),
        # tools -> vault, provider
        (57, 34, "tools→vault"),
        (57, 49, "tools→provider"),
        # toolagent -> vault, provider, tools
        (63, 34, "toolagent→vault"),
        (63, 49, "toolagent→provider"),
        (63, 62, "toolagent→tools"),
        # runtime -> vault, growth, provider, memory
        (70, 34, "runtime→vault"),
        (70, 22, "runtime→growth"),
        (70, 49, "runtime→provider"),
        (70, 39, "runtime→memory"),
        # pipeline -> runtime, tools
        (80, 72, "pipeline→runtime"),
        (80, 62, "pipeline→tools"),
        # reflect -> vault, provider, growth
        (88, 34, "reflect→vault"),
        (88, 49, "reflect→provider"),
        (88, 22, "reflect→growth"),
        # dream -> reflect, vault, provider, growth
        (94, 84, "dream→reflect"),
        (94, 34, "dream→vault"),
        (94, 49, "dream→provider"),
        (94, 22, "dream→growth"),
        # cli -> runtime, pipeline, dream, reflect
        (96, 72, "cli→runtime"),
        (96, 82, "cli→pipeline"),
        # web -> vault, steiner
        (96, 34, "web→vault"),
    ]
    for y, y2, label in deps:
        _arrow(ax, 50, y, 50, y2, "", lw=0.6, color="#888888")

    # 图例
    ax.text(2, 2, "■ steiner* = 隐藏层（Mortis 不知其存在）  → 依赖方向  灰底=层背景",
            fontsize=7, color="#555555")

    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "diagram-01-arch-layers.png"),
                dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print("✓ diagram-01-arch-layers.png")


# ============================================================
# Figure 2: 主循环调用链
# ============================================================
def render_02_pipeline_flow():
    fig, ax = _setup_ax((16, 10))
    ax.set_title("Figure 2 · 主循环调用链 — TaskRouter 路由 → 4 步 Step → sub 派生",
                 fontsize=14, weight="bold", pad=20)

    # 入口
    _box(ax, 5, 88, 18, 8, "owner 输入\ntask", fontsize=9, weight="bold")
    _box(ax, 30, 88, 22, 8, "PipelineExecutor.run()\nexecutor.py:43", fontsize=8)
    _box(ax, 60, 88, 25, 8, "TaskRouter.route()\nrouter.py:25  ★LLM#1", fontsize=8)

    # 路由分叉
    _box(ax, 5, 70, 22, 8, "simple 路径\n(直接执行)", fontsize=8)
    _box(ax, 35, 70, 22, 8, "delegated 路径\n(派 sub)", fontsize=8)

    _arrow(ax, 14, 88, 14, 78)
    _arrow(ax, 41, 88, 41, 78)
    _arrow(ax, 72, 88, 14, 78, "simple")
    _arrow(ax, 72, 88, 41, 78, "delegated")

    # 4 步 Step
    steps = [
        ("ThinkStep\nstep.py:144\n★LLM#2", 5, 55),
        ("PlanStep\nstep.py:178\n★LLM#2", 27, 55),
        ("ActStep\nstep.py:212\n★LLM#3+#4", 49, 55),
        ("ReviewStep\nstep.py:254\n★LLM#2", 71, 55),
    ]
    for text, x, y in steps:
        _box(ax, x, y, 20, 10, text, fontsize=8)
    # 箭头串
    for i in range(3):
        _arrow(ax, 25 + i * 22, 60, 27 + i * 22, 60)

    # ActStep 内部工具循环
    _box(ax, 49, 38, 22, 12, "ActStep 工具循环\nwhile iter<5:\n  _call_provider\n  tools.execute", fontsize=7)
    _arrow(ax, 60, 55, 60, 50, "展开")

    # 工具调用
    _box(ax, 30, 22, 18, 8, "ToolRegistry.execute()\nregistry.py:34", fontsize=8)
    _box(ax, 55, 22, 18, 8, "ToolAgent.execute()\nbase.py:176", fontsize=8)
    _box(ax, 78, 22, 18, 8, "5 内置 Agent\n(vault_read/search\n/stats/markdown/clock)", fontsize=7)
    _arrow(ax, 60, 38, 39, 30)
    _arrow(ax, 60, 38, 64, 30)
    _arrow(ax, 73, 26, 78, 30)

    # LLM 调用点
    _box(ax, 5, 38, 20, 10, "★LLM#8-11\n_llm_generate\n(redact 覆盖)", fontsize=7, fc="#F8F8F8")
    _arrow(ax, 64, 22, 25, 43)

    # sub 派生
    _box(ax, 35, 8, 22, 8, "SubRuntime\nL0→L1→L2\nsub.py", fontsize=8)
    _box(ax, 65, 8, 22, 8, "ReviewGate.apply\nreview.py:110\n[VAULT-WRITE]", fontsize=8)
    _arrow(ax, 41, 70, 46, 16, "派生")
    _arrow(ax, 57, 12, 65, 12)

    # 图例
    ax.text(2, 2, "★LLM#N = 第 N 个 LLM 调用点  [VAULT-WRITE] = vault 写入  → = 调用方向",
            fontsize=7, color="#555555")

    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "diagram-02-pipeline-flow.png"),
                dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print("✓ diagram-02-pipeline-flow.png")


# ============================================================
# Figure 3: Dream 4-7 phase 流水线
# ============================================================
def render_03_dream_pipeline():
    fig, ax = _setup_ax((16, 12))
    ax.set_title("Figure 3 · Dream 流水线 — Light 4 phase / Medium 5 phase / Deep 7 phase",
                 fontsize=14, weight="bold", pad=20)

    # Light (4 phase)
    ax.text(5, 92, "LightDreamer (4 phase)", fontsize=11, weight="bold")
    light = [
        ("RECALL\nlight.py:103\nscore_emotion\n★LLM#5", 5, 80),
        ("ASSOCIATE\nassociate.py:83\n★LLM#4", 25, 80),
        ("CRYSTALLIZE\nlight.py:219\nwrite_growth\n[VAULT-WRITE]", 45, 80),
        ("RECONCILE\nlight.py:268\n_detect_conflicts\n[VAULT-WRITE]", 65, 80),
    ]
    for text, x, y in light:
        _box(ax, x, y, 18, 10, text, fontsize=7)
    for i in range(3):
        _arrow(ax, 23 + i * 20, 85, 25 + i * 20, 85)

    # Medium (5 phase)
    ax.text(5, 67, "MediumDreamer (5 phase)", fontsize=11, weight="bold")
    medium = [
        ("RECALL\nmedium.py:91", 5, 55),
        ("ASSOCIATE\nmedium.py:136", 22, 55),
        ("SIMULATE\nmedium.py:156\nconfidence 0.3→0.5", 39, 55),
        ("CRYSTALLIZE\nmedium.py:201\n[VAULT-WRITE]", 56, 55),
        ("RECONCILE\nmedium.py:256\n[VAULT-WRITE]", 73, 55),
    ]
    for text, x, y in medium:
        _box(ax, x, y, 16, 10, text, fontsize=7)
    for i in range(4):
        _arrow(ax, 21 + i * 17, 60, 22 + i * 17, 60)

    # Deep (7 phase)
    ax.text(5, 42, "DeepDreamer (7 phase)", fontsize=11, weight="bold")
    deep = [
        ("RECALL\ndeep.py:76\n重读 growth", 3, 30),
        ("ASSOCIATE\ndeep.py:100", 15, 30),
        ("SIMULATE\ndeep.py:124", 27, 30),
        ("CRYSTALLIZE\ndeep.py:146\n[VAULT-WRITE]", 39, 30),
        ("RECONCILE\ndeep.py:174\n[VAULT-WRITE]", 51, 30),
        ("ERODE\ndeep.py:223\n×0.85^days\n[VAULT-WRITE]", 63, 30),
        ("SEED_CHECK\ndeep.py:264\n★LLM#6\nredact\n[VAULT-WRITE]", 75, 30),
    ]
    for text, x, y in deep:
        _box(ax, x, y, 11, 12, text, fontsize=6)
    for i in range(6):
        _arrow(ax, 14 + i * 12, 36, 15 + i * 12, 36)

    # 信号产出
    ax.text(5, 17, "信号产出", fontsize=10, weight="bold")
    signals = [
        ("Growth 候选\nconfidence=0.3", 5, 8),
        ("confidence 提升\n0.3→0.5", 25, 8),
        ("confidence 衰减\n×0.85^days", 45, 8),
        ("DriftReport\n→ owner-notify", 65, 8),
        ("conflicts/\nsubconscious", 83, 8),
    ]
    for text, x, y in signals:
        _box(ax, x, y, 14, 7, text, fontsize=6, fc="#F8F8F8")

    _arrow(ax, 10, 30, 10, 15)
    _arrow(ax, 47, 30, 30, 15)
    _arrow(ax, 68, 30, 50, 15)
    _arrow(ax, 80, 30, 70, 15)
    _arrow(ax, 60, 30, 90, 15)

    ax.text(2, 2, "★LLM#N = LLM 调用点  [VAULT-WRITE] = vault 写入  → = phase 顺序",
            fontsize=7, color="#555555")

    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "diagram-03-dream-pipeline.png"),
                dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print("✓ diagram-03-dream-pipeline.png")


# ============================================================
# Figure 4: 信号流主链
# ============================================================
def render_04_signal_flow():
    fig, ax = _setup_ax((16, 10))
    ax.set_title("Figure 4 · 信号流主链 — session → emotion → growth → steiner → drift 闭环",
                 fontsize=14, weight="bold", pad=20)

    # 5 个阶段
    stages = [
        ("1. session\nowner 对话\nmemory/session.py", 5, 75),
        ("2. emotion\nscore_emotion()\nvalence -1~1\narousal 0~1\n★LLM#5", 25, 75),
        ("3. growth\nCRYSTALLIZE\nconfidence 0.3~0.5\n[VAULT-WRITE]", 45, 75),
        ("4. unease\nGrowthWatcher\naccumulate()\nsteiner 隐藏层", 65, 75),
        ("5. drift\nseed_check()\n★LLM#6\n→ owner-notify", 85, 75),
    ]
    for text, x, y in stages:
        _box(ax, x, y, 12, 14, text, fontsize=7, weight="bold")
    for i in range(4):
        _arrow(ax, 17 + i * 20, 82, 25 + i * 20, 82)

    # 信号数据结构
    ax.text(5, 60, "信号数据结构", fontsize=10, weight="bold")
    sigs = [
        ("Session\nsession_id\nthreads[]", 5, 50),
        ("emotion_weight\n|v|×a\nrecall.py:26", 25, 50),
        ("Growth\ndimension(7)\nconfidence\nemotional_*", 45, 50),
        ("UneaseState\nper_dimension\nmax_unease()\nsteiner/unease.py:63", 65, 50),
        ("DriftReport\nscore\nthreshold\nseed_check.py:38", 85, 50),
    ]
    for text, x, y in sigs:
        _box(ax, x, y, 12, 10, text, fontsize=6, fc="#F8F8F8")
    for i in range(5):
        _arrow(ax, 11 + i * 20, 75, 11 + i * 20, 60)

    # 消费者
    ax.text(5, 35, "消费者", fontsize=10, weight="bold")
    consumers = [
        ("ReflectExecutor\n读 session 写反思", 5, 25),
        ("emotion_weighted_sample\nRECALL 加权采样", 25, 25),
        ("search_growths\nmin_conf=0.5\n注入 system prompt", 45, 25),
        ("unease_prompt()\n5 档文案注入\nsteiner/prompt.py:53", 65, 25),
        ("should_notify_owner\ndrift≥0.75 报警\nsteiner/drift.py:22", 85, 25),
    ]
    for text, x, y in consumers:
        _box(ax, x, y, 12, 10, text, fontsize=6)
    for i in range(5):
        _arrow(ax, 11 + i * 20, 50, 11 + i * 20, 35)

    # 闭环箭头
    _arrow(ax, 91, 25, 11, 75, "闭环: drift → owner 编辑 → session", lw=1.2, ls="--")

    ax.text(2, 2, "→ 信号传递  ╌ 闭环反馈  ★LLM#N = LLM 调用点",
            fontsize=7, color="#555555")

    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "diagram-04-signal-flow.png"),
                dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print("✓ diagram-04-signal-flow.png")


# ============================================================
# Figure 5: Vault 4 层纵深防御
# ============================================================
def render_05_vault_defense():
    fig, ax = _setup_ax((16, 10))
    ax.set_title("Figure 5 · Vault 4 层纵深防御 — 任一层失败即拦截",
                 fontsize=14, weight="bold", pad=20)

    # 4 层防御（自外向内）
    layers = [
        ("Layer 1 · 路径归一化", "_safe_path()\nvault/local.py:51\nresolve + relative_to\n防 ../ 遍历", 5, 75, 22),
        ("Layer 2 · 白名单强制", "_enforce()\nvault/local.py:69\ncheck_whitelist\nSUB_VAULT_WHITELIST", 30, 75, 22),
        ("Layer 3 · BLOCKED_PREFIXES", "vault_read.py:39\nmortis-steiner/\nmortis-journal/sub-outputs/\nmortis-subconscious/", 55, 75, 22),
        ("Layer 4 · normalize_rel_path", "vault/normalize.py:15\n栈式归一化\n消除中段 .. 绕过\n(issue #67)", 80, 75, 18),
    ]
    for title, content, x, y, w in layers:
        _box(ax, x, y, w, 14, f"{title}\n\n{content}", fontsize=7, weight="bold")
        _arrow(ax, x + w, 82, x + w + 3, 82, "通过")

    # 攻击向量
    ax.text(5, 60, "攻击向量（已被防御）", fontsize=10, weight="bold", color="#000000")
    attacks = [
        ("S1: Vault.write 路径遍历\n→ Layer 1 拦截", 5, 50),
        ("S2: 白名单 ../ 绕过\n→ Layer 2 拦截", 30, 50),
        ("#38: 人格层读 mortis-steiner/\n→ Layer 3 拦截", 55, 50),
        ("#67: 中段 .. 绕过\nmortis-journal/../mortis-steiner\n→ Layer 4 拦截", 80, 50),
    ]
    for text, x, y in attacks:
        _box(ax, x, y, 18, 8, text, fontsize=6, fc="#F8F8F8", ec="#000000")
        _arrow(ax, x + 9, 75, x + 9, 58, "防御", ls="--")

    # Redact 防御
    ax.text(5, 35, "Redact 脱敏层（防 LLM 泄漏）", fontsize=10, weight="bold")
    redact = [
        ("redact_snippet()\nmortis/redact.py:56\n6 个 SENSITIVE_PATTERNS\nfail-closed", 5, 22),
        ("覆盖 8 个 LLM 入口\n_summarize / _semantic_rerank\nscore_emotion / associate\nseed_check / _preview_body", 30, 22),
        ("脱敏目标\ndream callout\n[emotion:...]\n%%subconscious%%\nemotional_*", 55, 22),
        ("大小写不敏感\nIGNORECASE\n\\s*:\\s* 防冒号空格\n(issue CRITICAL-2)", 80, 22),
    ]
    for text, x, y in redact:
        _box(ax, x, y, 18, 12, text, fontsize=6, fc="#F8F8F8")

    ax.text(2, 2, "→ 防御方向  ╌ 攻击向量  灰底=数据结构",
            fontsize=7, color="#555555")

    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "diagram-05-vault-defense.png"),
                dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print("✓ diagram-05-vault-defense.png")


# ============================================================
# Figure 6: 复杂任务信息流转
# ============================================================
def render_06_task_flow():
    fig, ax = _setup_ax((16, 12))
    ax.set_title("Figure 6 · 复杂任务信息流转 — owner 输入 → growth 落地完整路径",
                 fontsize=14, weight="bold", pad=20)

    # owner 输入
    _box(ax, 35, 90, 30, 7, "owner: python -m mortis delegate\n\"整理本周 growth 总结 identity 维度变化\"",
         fontsize=8, weight="bold")

    # CLI 入口
    _box(ax, 35, 78, 30, 7, "cli/commands.py cmd_delegate()\n→ MasterRuntime.create_thread()", fontsize=8)
    _arrow(ax, 50, 90, 50, 85)

    # Pipeline
    _box(ax, 35, 66, 30, 7, "PipelineExecutor.run()\nexecutor.py:43", fontsize=8)
    _arrow(ax, 50, 78, 50, 73)

    # TaskRouter
    _box(ax, 35, 54, 30, 7, "TaskRouter.route()  ★LLM#1\n→ delegated (复杂任务)", fontsize=8)
    _arrow(ax, 50, 66, 50, 59)

    # 4 步
    _box(ax, 5, 42, 20, 7, "ThinkStep ★LLM#2\n分析任务", fontsize=8)
    _box(ax, 28, 42, 20, 7, "PlanStep ★LLM#2\n拆解步骤", fontsize=8)
    _box(ax, 51, 42, 20, 7, "ActStep ★LLM#3+#4\n工具调用循环", fontsize=8)
    _box(ax, 74, 42, 20, 7, "ReviewStep ★LLM#2\n审阅产出", fontsize=8)
    for i in range(3):
        _arrow(ax, 25 + i * 23, 45.5, 28 + i * 23, 45.5)
    _arrow(ax, 50, 54, 15, 49)

    # ActStep 内部
    _box(ax, 40, 28, 25, 10, "ActStep 工具循环\nwhile iter<5:\n  provider.generate ★LLM#3\n  tools.execute()\n  provider.generate ★LLM#4", fontsize=7)
    _arrow(ax, 60, 42, 52, 38, "展开")

    # 工具调用
    _box(ax, 5, 18, 22, 8, "vault:search_agent\nVaultSearchAgent\n_semantic_rerank ★LLM#10\n[redact ✓]", fontsize=7)
    _box(ax, 30, 18, 22, 8, "vault:read_agent\nVaultReadAgent\n_summarize ★LLM#9\n[redact ✓]", fontsize=7)
    _box(ax, 55, 18, 22, 8, "vault:stats_agent\nVaultStatsAgent\n_analyze_stats ★LLM#11\n[仅统计数字]", fontsize=7)
    _box(ax, 80, 18, 15, 8, "markdown:render\n解析 Obsidian", fontsize=7)
    _arrow(ax, 45, 28, 16, 26)
    _arrow(ax, 50, 28, 41, 26)
    _arrow(ax, 55, 28, 66, 26)
    _arrow(ax, 60, 28, 87, 26)

    # growth 注入
    _box(ax, 5, 5, 30, 8, "RuntimeContext.messages_for_provider()\ncontext.py:130\n注入: tone + unease + growth + history", fontsize=7, fc="#F8F8F8")
    _box(ax, 40, 5, 25, 8, "growth_context_for_task()\ncontext.py:74\nsearch_growths(min_conf=0.5)\n_preview_body [redact ✓]", fontsize=7, fc="#F8F8F8")
    _box(ax, 70, 5, 25, 8, "unease_prompt_for_injection()\ncontext.py:110\nsteiner 隐藏层注入", fontsize=7, fc="#F8F8F8")
    _arrow(ax, 50, 18, 20, 13, "system prompt")
    _arrow(ax, 52, 18, 52, 13)
    _arrow(ax, 60, 18, 82, 13)

    ax.text(2, 2, "★LLM#N = LLM 调用点  [redact ✓] = 已脱敏  灰底=system prompt 构造",
            fontsize=7, color="#555555")

    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "diagram-06-task-flow.png"),
                dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print("✓ diagram-06-task-flow.png")


# ============================================================
# Figure 7: Dream 周期信息流
# ============================================================
def render_07_dream_cycle():
    fig, ax = _setup_ax((16, 10))
    ax.set_title("Figure 7 · Dream 周期信息流 — clock 触发 → 4 phase → growth 落地",
                 fontsize=14, weight="bold", pad=20)

    # clock 触发
    _box(ax, 5, 85, 20, 10, "LogicalClock\n23:00-06:00\n→ DREAM_LIGHT\nlogical.py:97", fontsize=8)
    _box(ax, 30, 85, 20, 10, "Scheduler.tick()\nschedule.py:63\n→ 触发 LightDreamer", fontsize=8)
    _box(ax, 55, 85, 20, 10, "LightDreamer.run()\npipeline.py:54\n4 phase 顺序执行", fontsize=8)
    _arrow(ax, 25, 90, 30, 90)
    _arrow(ax, 50, 90, 55, 90)

    # 4 phase
    phases = [
        ("RECALL\nlight.py:103\n扫最近 N 天 session\nscore_emotion ★LLM#5\nemotion_weighted_sample", 5, 65),
        ("ASSOCIATE\nlight.py:196\nassociate() ★LLM#4\n找共同模式\n[redact ✓]", 28, 65),
        ("CRYSTALLIZE\nlight.py:219\nmake_candidate()\nconfidence=0.3\nwrite_growth [VAULT-WRITE]", 51, 65),
        ("RECONCILE\nlight.py:268\n_detect_conflicts\n写 conflicts/\n[VAULT-WRITE]", 74, 65),
    ]
    for text, x, y in phases:
        _box(ax, x, y, 21, 14, text, fontsize=7)
    for i in range(3):
        _arrow(ax, 26 + i * 23, 72, 28 + i * 23, 72)
    _arrow(ax, 65, 85, 15, 79)

    # 数据流
    ax.text(5, 50, "数据流", fontsize=10, weight="bold")
    flows = [
        ("sessions/\nmortis-journal/sessions/", 5, 40),
        ("emotion 缓存\nscore_emotion cache", 28, 40),
        ("Growth 候选\nmortis-growth/<dim>/", 51, 40),
        ("conflicts/\nmortis-subconscious/conflicts/", 74, 40),
    ]
    for text, x, y in flows:
        _box(ax, x, y, 21, 8, text, fontsize=7, fc="#F8F8F8")
    for i in range(4):
        _arrow(ax, 15 + i * 23, 65, 15 + i * 23, 48)

    # 后续触发
    ax.text(5, 25, "后续触发", fontsize=10, weight="bold")
    _box(ax, 5, 15, 25, 8, "MediumDreamer\n跨周采样 + SIMULATE\nconfidence 0.3→0.5", fontsize=7)
    _box(ax, 33, 15, 25, 8, "DeepDreamer\n全量重读 + ERODE\n+ SEED_CHECK drift", fontsize=7)
    _box(ax, 61, 15, 25, 8, "ERODE 衰减\n×0.85^days\n< 阈值 → archive", fontsize=7)
    _box(ax, 88, 15, 10, 8, "drift\n≥0.75\n→ notify", fontsize=7)
    _arrow(ax, 30, 19, 33, 19)
    _arrow(ax, 58, 19, 61, 19)
    _arrow(ax, 86, 19, 88, 19)

    ax.text(2, 2, "★LLM#N = LLM 调用点  [VAULT-WRITE] = vault 写入  [redact ✓] = 已脱敏  灰底=数据落盘",
            fontsize=7, color="#555555")

    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "diagram-07-dream-cycle.png"),
                dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print("✓ diagram-07-dream-cycle.png")


# ============================================================
# Figure 8: Steiner 隐藏层触发链
# ============================================================
def render_08_steiner_hidden():
    fig, ax = _setup_ax((16, 10))
    ax.set_title("Figure 8 · Steiner 隐藏层触发链 — owner 编辑 → unease → 潜台词注入 → drift 通知",
                 fontsize=14, weight="bold", pad=20)

    # owner 编辑
    _box(ax, 5, 85, 20, 8, "owner 手动编辑\nmortis-growth/<dim>/x.md", fontsize=8, weight="bold")
    _arrow(ax, 25, 89, 30, 89, "文件变更")

    # Watcher
    _box(ax, 30, 85, 22, 8, "GrowthWatcher\nwatchdog Observer\nwatcher.py:169", fontsize=8)
    _arrow(ax, 52, 89, 57, 89, "on_modified")

    # handler
    _box(ax, 57, 85, 22, 8, "handler._on_modified\n提取 Dimension\n→ callback(dim)", fontsize=8)
    _arrow(ax, 79, 89, 84, 89, "callback")

    # Controller
    _box(ax, 84, 85, 14, 8, "SteinerController\n_on_edit(dim)\nlifecycle.py:47", fontsize=7)
    _arrow(ax, 91, 85, 91, 75, "debounce 1s")

    # accumulate
    _box(ax, 70, 65, 28, 8, "accumulate(state, dim, delta=+0.1)\nunease.py:150\nper_dimension[dim] += 0.1", fontsize=7)
    _arrow(ax, 91, 75, 91, 73)

    # save
    _box(ax, 70, 53, 28, 8, "save_unease(vault, state)\nunease.py:123\n→ mortis-steiner/unease.json\n[VAULT-WRITE]", fontsize=7)
    _arrow(ax, 84, 65, 84, 61)

    # 注入路径
    _box(ax, 5, 53, 28, 8, "RuntimeContext\nmessages_for_provider()\ncontext.py:130", fontsize=8)
    _box(ax, 35, 53, 28, 8, "unease_prompt_for_injection()\ncontext.py:110\nload_unease + decay", fontsize=8)
    _box(ax, 5, 41, 28, 8, "unease_prompt(state)\nprompt.py:53\n5 档文案", fontsize=8)
    _box(ax, 35, 41, 28, 8, "Message(role=system,\ncontent=unease_text)\n注入 tone 之后 growth 之前", fontsize=8)
    _arrow(ax, 70, 57, 63, 57, "读取")
    _arrow(ax, 33, 57, 33, 49)
    _arrow(ax, 19, 53, 19, 49)
    _arrow(ax, 33, 45, 33, 49, "注入")

    # drift 报警
    _box(ax, 70, 41, 28, 8, "should_notify_owner(unease)\ndrift.py:22\nmax(per_dim) ≥ 0.75", fontsize=7)
    _arrow(ax, 84, 53, 84, 49, "检查")

    # owner 通知
    _box(ax, 70, 29, 28, 8, "send_notification()\nweb/notify.py:36\n→ owner-notify.json\n[VAULT-WRITE]", fontsize=7)
    _arrow(ax, 84, 41, 84, 37, "报警")

    # Web UI
    _box(ax, 70, 17, 28, 8, "Web UI /notifications\nserver.py:143\nowner 可读", fontsize=8)
    _arrow(ax, 84, 29, 84, 25, "可读")

    # 隐藏层标注
    ax.add_patch(Rectangle((68, 11), 32, 65, facecolor="#FAFAFA",
                           edgecolor="#000000", linewidth=1.5, linestyle="--"))
    ax.text(69, 73, "steiner 隐藏层\n(Mortis 不知其存在)", fontsize=8,
            color="#555555", style="italic")

    ax.text(2, 2, "→ 触发链  ╌ 隐藏层边界  虚线框=steiner 隐藏层（Mortis 不可见）",
            fontsize=7, color="#555555")

    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "diagram-08-steiner-hidden.png"),
                dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print("✓ diagram-08-steiner-hidden.png")


# ============================================================
# Figure 9: 测试覆盖热力图（新增）
# ============================================================
def render_09_test_coverage():
    fig, ax = plt.subplots(figsize=(16, 10))
    ax.set_title("Figure 9 · 测试覆盖率热力图 — 13 大类流程节点 × 测试文件数",
                 fontsize=14, weight="bold", pad=20)

    # 数据（来自测试覆盖分析）
    categories = [
        ("A 主循环", [("A1 入口", 0), ("A2-A5 步骤", 1), ("A6 Pipeline", 3), ("A7 SubRuntime", 2), ("A8 RuntimeContext", 3)]),
        ("B 认知周期", [("B1 LogicalClock", 3), ("B2 SleepState", 3), ("B3 Scheduler", 3), ("B4-B5 触发", 3), ("B6-B7 Med/Deep", 3), ("B8 ERODE", 2), ("B9 reflect", 3), ("B10 daemon", 1)]),
        ("C Dream", [("C1 RECALL", 9), ("C2 ASSOCIATE", 6), ("C3 SIMULATE", 4), ("C4 CRYSTALLIZE", 5), ("C5 RECONCILE", 5), ("C6 ERODE", 4), ("C7 SEED_CHECK", 8)]),
        ("D Growth", [("D1 model", 3), ("D2 frontmatter", 6), ("D3 writer", 5), ("D4 vault CRUD", 6), ("D5 检索", 3), ("D6 注入", 5), ("D7 压缩", 1), ("D8 衰减", 1)]),
        ("E Reflect", [("E1 executor", 2), ("E2 id", 1), ("E3 emotion", 4), ("E4 triggers", 3), ("E5 cache", 2)]),
        ("F Steiner", [("F1 unease", 4), ("F2 watcher", 2), ("F3 prompt", 4), ("F4 drift", 3), ("F5 controller", 1), ("F6 drift_log", 1)]),
        ("G Provider", [("G1 mock", 6), ("G2 minimax", 5), ("G3 注入", 7), ("G4 routing", 1), ("G5 async", 1), ("G6 audit", 1)]),
        ("H ToolAgent", [("H1 base", 5), ("H2 read", 5), ("H3 search", 3), ("H4 stats", 3), ("H5 markdown", 2), ("H6 clock", 2), ("H7 result", 1), ("H8 registry", 5)]),
        ("I Vault 安全", [("I1 vault", 1), ("I2 growth vault", 3), ("I3 parser", 1), ("I4 traversal", 3), ("I5 whitelist", 7), ("I6 blocked_prefix", 3), ("I7 seed hash", 1)]),
        ("J Redact", [("J1 shared", 2), ("J2 dream callout", 5), ("J3 emotion", 5), ("J4 subconscious", 5), ("J5 fail-closed", 2), ("J6 seed_check", 1), ("J7 preview", 1), ("J8 session", 1), ("J9 case-insens", 4)]),
        ("K CLI", [("K5 dream/reflect/status", 1), ("K7 goodnight", 1)]),
        ("L Web UI", [("L1 server", 1), ("L2 dashboard", 1), ("L3 growths", 1), ("L4 unease", 1), ("L5 notifications", 1), ("L6 dreams", 1)]),
        ("M 通知", [("M1 send", 2), ("M2 read", 1), ("M3 cap", 1)]),
    ]

    # 展平
    nodes = []
    labels = []
    values = []
    for cat, items in categories:
        for name, count in items:
            nodes.append((cat, name, count))
            labels.append(f"{name}\n({count})")
            values.append(count)

    # 网格布局
    n = len(nodes)
    cols = 8
    rows = (n + cols - 1) // cols

    # 画格子
    for i, (cat, name, count) in enumerate(nodes):
        r = i // cols
        c = i % cols
        x = c * 12 + 2
        y = (rows - r - 1) * 12 + 5
        # 颜色：白→黑灰阶
        if count == 0:
            fc = "#FFFFFF"
            ec = "#FF0000"  # 红框=未覆盖
            lw = 2
        elif count == 1:
            fc = "#F0F0F0"
            ec = "#000000"
            lw = 1
        elif count <= 3:
            fc = "#D0D0D0"
            ec = "#000000"
            lw = 1
        elif count <= 5:
            fc = "#A0A0A0"
            ec = "#000000"
            lw = 1
        else:
            fc = "#606060"
            ec = "#000000"
            lw = 1
        text_color = "#000000" if count <= 3 else "#FFFFFF"
        box = FancyBboxPatch((x, y), 10, 10,
                             boxstyle="round,pad=0.02,rounding_size=0.3",
                             facecolor=fc, edgecolor=ec, linewidth=lw)
        ax.add_patch(box)
        ax.text(x + 5, y + 5, f"{name}\n{count} 文件",
                ha="center", va="center", fontsize=7, color=text_color, weight="bold")

    ax.set_xlim(0, cols * 12 + 4)
    ax.set_ylim(0, rows * 12 + 8)
    ax.set_aspect("equal")
    ax.axis("off")

    # 图例
    legend_items = [
        ("0 文件 (未覆盖)", "#FFFFFF", "#FF0000"),
        ("1 文件 (薄弱)", "#F0F0F0", "#000000"),
        ("2-3 文件", "#D0D0D0", "#000000"),
        ("4-5 文件", "#A0A0A0", "#000000"),
        ("6+ 文件 (密集)", "#606060", "#000000"),
    ]
    for i, (label, fc, ec) in enumerate(legend_items):
        ax.add_patch(Rectangle((2 + i * 20, 1), 2, 1.5, facecolor=fc, edgecolor=ec))
        ax.text(5 + i * 20, 1.7, label, fontsize=7, va="center")

    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "diagram-09-test-coverage.png"),
                dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print("✓ diagram-09-test-coverage.png")


# ============================================================
# Figure 10: 分支与 issue 时间轴（新增）
# ============================================================
def render_10_timeline():
    fig, ax = plt.subplots(figsize=(18, 12))
    ax.set_title("Figure 10 · 分支与 Issue 提交时间轴 — 2026-06-20 至 2026-06-25",
                 fontsize=14, weight="bold", pad=20)

    # 时间轴数据（按日期分组）
    timeline = [
        # (date, branch/pr, issue, title)
        ("06-20", "main", "#1", "mortis 架构骨架 — vault 抽象 + 主人格引擎"),
        ("06-20", "main", "#2", "立人 — 从工具化到人格化"),
        ("06-21 03:14", "main", "—", "v0+v1 骨架完整实现 (69 测试 + minimax)"),
        ("06-21 12:15", "main", "—", "重构为 8 子包自研框架"),
        ("06-21 15:39", "main", "—", "首次跟踪 mortis/vault/ 子包代码"),
        ("06-21 15:42", "main", "#6", "whitelist 强制检查下沉到 Vault 层"),
        ("06-21 16:59", "fix/audit-hanis-vault-path-security", "#11/#12/#13", "修复 3 个 CRITICAL 路径安全漏洞 (S1/S2/S3)"),
        ("06-21 17:13", "fix/audit-hanis-pipeline-chain", "#7/#8/#9/#10", "Pipeline 审阅链 + SubTemplate 防伪 + L2 模板链"),
        ("06-21 18:12", "main", "#16", "RFC-001 认知生长系统"),
        ("06-21 19:30", "main", "#17", "ReviewGate.apply vault_whitelist 强制"),
        ("06-22 10:10", "main", "#18", "Growth 数据模型 + 7 维度枚举"),
        ("06-22 10:14", "main", "—", "vault 结构扩展 + growth CRUD API"),
        ("06-22 13:15", "main", "#27", "mortis/__init__ growth CRUD 顶层包装"),
        ("06-22 13:35", "main", "#19/#28", "Obsidian 语法解析层 + Growth Obsidian-Native"),
        ("06-22 14:34", "main", "#21/#29", "ReflectExecutor + emotion 标注 + 触发条件"),
        ("06-22 15:38", "main", "#22/#30", "LightDreamer 4 phase + 情绪加权采样"),
        ("06-22 16:48", "main", "#24/#31", "Reading Steiner — unease + watcher + drift"),
        ("06-22 16:57", "main", "#25/#32", "5 内置 Agent + TaskRouter 关键词路由"),
        ("06-22 17:08", "main", "#23/#33", "Medium + Deep + erode + seed-check"),
        ("06-22 21:47", "main", "#26/#34", "逻辑时钟 + 昼夜节律 + 时差 + 睡眠不足"),
        ("06-23 07:44", "feature/v3-toolagent-llm-integration", "#63/#64/#59", "ToolAgent LLM integration + growth retrieval"),
        ("06-23 08:54", "main", "#41", "hours_awake 双重计数 + LogicalClock 时区"),
        ("06-23 08:55", "main", "#42", "reconcile break 错位 + archive_growth API"),
        ("06-23 08:55", "main", "#43", "VaultReadAgent blocked_prefixes 安全检查"),
        ("06-23 08:56", "main", "#40/#44", "清理审计死代码 + 风格问题"),
        ("06-23 09:08", "main", "—", "更新 README + RFC-001 → Implemented"),
        ("06-23 10:51", "main", "—", "Harness 工程 — dev 工具 + 上下文锚点"),
        ("06-23 19:56", "fix/vault-read (PR #69)", "#67", "BLOCKED_PREFIX 路径归一化 — 消除 .. 绕过"),
        ("06-23 20:47", "fix/agent-tool", "#68", "VaultReadToolAgent sub 私域阻断"),
        ("06-24 00:32", "fix/toolagent (PR #74)", "#70", "_llm_generate 区分 TimeoutError + log warning"),
        ("06-24 00:43", "chore/toolagent (PR #76)", "#72", "删除 TaskRouter 关键词路由"),
        ("06-24 12:48", "fix/toolagent (#77)", "#71/#73", "semantic rerank redact + 异常分类"),
        ("06-24 14:30", "main", "—", "Merge PR #74 + #76"),
        ("06-24 14:37", "main", "—", "修复 2 个 CRITICAL 数据泄漏漏洞"),
        ("06-24 14:46", "fix/80-vault-read-agent-sub-outputs", "#80", "VaultReadAgent sub-outputs 阻断"),
        ("06-24 14:47", "fix/78-79-test-timebomb", "#78/#79", "dream 测试 time-bomb 修复"),
        ("06-24 15:09", "main", "—", "新增 v3 方法级代码审计报告"),
        ("06-24 15:12", "main", "—", "合并 fix/78-79 + fix/80 分支"),
        ("06-24 15:20", "main", "—", "审计报告 HTML → Markdown"),
        ("06-24 15:40", "main", "—", "Mermaid 图表渲染为 PNG"),
        ("06-24 15:58", "main", "—", "图片引用改为绝对 raw URL"),
        ("06-24 16:04", "main", "—", "rebase 冲突解决"),
        ("06-24 17:00", "fix/83-redact-shared", "#83", "redact utility 提升为共享模块"),
        ("06-24 17:21", "fix/88-unify-toolresult", "#88", "统一 ToolResult 类型"),
        ("06-24 17:44", "fix/87-provider-audit-log", "#87", "provider prompt hash 审计日志"),
        ("06-24 17:56", "fix/84-seed-check-redact", "#84", "seed_check 发 LLM 前加 redact (CRITICAL)"),
        ("06-24 18:01", "fix/86-session-redact", "#86", "associate + score_emotion redact"),
        ("06-24 18:03", "fix/85-growth-preview-redact", "#85", "growth preview 注入前 redact"),
        ("06-24 18:19", "fix/57-unease-injection", "#57", "unease 注入 RuntimeContext"),
        ("06-24 18:21", "fix/58-growth-watcher-start", "#58", "SteinerController 生命周期管理"),
        ("06-24 18:35", "fix/56-cli-extensions", "#56", "dream/reflect/status 命令"),
        ("06-24 19:02", "fix/61-goodnight-trigger", "#61", "owner「晚安」触发夜间认知周期"),
        ("06-24 19:10", "fix/60-daemon-mode", "#60", "daemon 常驻进程自动触发"),
        ("06-24 19:14", "main", "—", "Merge fix/61-goodnight-trigger"),
        ("06-24 19:41", "fix/45-provider-registry", "#45", "多 LLM 后端注册表 + 任务路由"),
        ("06-24 19:57", "fix/46-async-generate", "#46", "async generate/generate_text 接口"),
        ("06-24 19:59", "fix/47-growth-compression", "#47", "growth 维度压缩"),
        ("06-24 20:12", "fix/48-drift-log", "#48", "drift 误报率监控"),
        ("06-24 20:14", "fix/52-web-ui", "#52/#53/#54", "Web UI + growth 浏览器 + owner 通知"),
        ("06-24 20:16", "main", "—", "Merge fix/52-web-ui"),
        ("06-25 01:29", "main", "—", "Merge PR #66 (冲突解决)"),
    ]

    # 按分支首次出现顺序分组，分配标记 B1, B2, ...
    branches: dict[str, str] = {}  # branch -> marker
    branch_data: dict[str, list] = {}  # branch -> [(date, issue, title)]
    marker_idx = 0
    for date, branch, issue, title in timeline:
        if branch not in branches:
            marker_idx += 1
            branches[branch] = f"B{marker_idx}"
            branch_data[branch] = []
        branch_data[branch].append((date, issue, title))

    # 画分支泳道 — 左侧用 B1/B2/... 标记，不写全名（避免重叠）
    branch_names = list(branches.keys())
    n_branches = len(branch_names)
    lane_height = 100 / n_branches

    for i, branch in enumerate(branch_names):
        y_lane = 100 - (i + 1) * lane_height
        # 泳道背景
        ax.add_patch(Rectangle((0, y_lane), 100, lane_height,
                               facecolor="#FAFAFA" if i % 2 == 0 else "#F0F0F0",
                               edgecolor="#CCCCCC", linewidth=0.5))
        # 分支标记（B1, B2, ...）— 不再写全名
        marker = branches[branch]
        ax.text(2, y_lane + lane_height / 2, marker, fontsize=8,
                weight="bold", va="center", ha="center",
                bbox=dict(facecolor="white", edgecolor="#000000", pad=2))

    # 画提交点
    for date, branch, issue, title in timeline:
        i = branch_names.index(branch)
        y_lane = 100 - (i + 1) * lane_height + lane_height / 2
        # x 位置按时间
        # 简化：按 timeline 顺序排列
        idx = timeline.index((date, branch, issue, title))
        x = 8 + (idx / len(timeline)) * 88

        # 提交点
        ax.plot(x, y_lane, "o", color="#000000", markersize=6)
        # issue 标注
        if issue != "—":
            ax.text(x, y_lane + 3, issue, fontsize=6, ha="center",
                    color="#000000", weight="bold",
                    bbox=dict(facecolor="white", edgecolor="#000000", pad=1))
        # 标题（旋转）
        ax.text(x, y_lane - 4, title[:25], fontsize=5, ha="center",
                color="#555555", rotation=45)

    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.set_aspect("auto")
    ax.axis("off")

    # 时间轴
    ax.annotate("", xy=(98, 2), xytext=(8, 2),
                arrowprops=dict(arrowstyle="->", color="#000000", lw=1.5))
    ax.text(50, 1, "时间轴: 2026-06-20 → 2026-06-25 (5 天, 60+ 提交, 88 issues 全部关闭)",
            fontsize=9, ha="center", weight="bold")

    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "diagram-10-timeline.png"),
                dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print("✓ diagram-10-timeline.png")


# ============================================================
# E2E Figure 1: Pipeline 主循环调用链
# ============================================================
def render_e2e_01_pipeline_chain():
    fig, ax = _setup_ax((18, 13))
    ax.set_title("E2E Figure 1 · Pipeline 主循环调用链 — Think→Plan→Act→Review + TaskRouter",
                 fontsize=14, weight="bold", pad=20)

    # ---- 入口行 (y=90) ----
    _box(ax, 5, 88, 22, 8, "PipelineExecutor.run()\nexecutor.py:43", fontsize=8, weight="bold")
    _box(ax, 35, 88, 28, 8, "TaskRouter.route()\nrouter.py:25\n★LLM#0 路由决策", fontsize=8)
    _arrow(ax, 27, 92, 35, 92)

    # ---- 路由分叉 (y=72) ----
    _box(ax, 5, 70, 22, 8, "simple 路径\n直接执行\nexecutor.py:64-103", fontsize=8)
    _box(ax, 35, 70, 28, 8, "delegated 路径\n派 sub\nexecutor.py:119", fontsize=8)
    _arrow(ax, 14, 88, 14, 78, "simple")
    _arrow(ax, 49, 88, 49, 78, "delegated")

    # ---- 委派分支 (右侧, x=82) ----
    _box(ax, 82, 70, 16, 8, "vault.write_sub_output()\nexecutor.py:187\n[VAULT-WRITE]", fontsize=7)
    _box(ax, 82, 56, 16, 8, "ReviewGate.review()\nreview.py:39", fontsize=7)
    _box(ax, 82, 42, 16, 8, "ReviewGate.apply()\nreview.py:155\n_safe_write [VAULT-WRITE]", fontsize=7)
    _arrow(ax, 63, 74, 82, 74)
    _arrow(ax, 90, 70, 90, 64)
    _arrow(ax, 90, 56, 90, 50)

    # ---- 4 步 Step (y=50, width=18, gap=2) ----
    steps = [
        ("ThinkStep.run()\nstep.py:144\n★LLM#1\nprompt: 分析任务\n需要查 vault? 派 sub?", 2, 50),
        ("PlanStep.run()\nstep.py:178\n★LLM#2\nprompt: 拆解为\n不超过 5 步骤", 22, 50),
        ("ActStep.run()\nstep.py:212\n★LLM#3\n工具调用循环\nMAX_ITERATIONS=5", 42, 50),
        ("ReviewStep.run()\nstep.py:254\n★LLM#4\nprompt: 审阅产出\nadopt/discard", 62, 50),
    ]
    for text, x, y in steps:
        _box(ax, x, y, 18, 14, text, fontsize=7)
    for i in range(3):
        _arrow(ax, 20 + i * 20, 57, 22 + i * 20, 57)

    # simple 路径 → ThinkStep (补上缺失的箭头)
    _arrow(ax, 14, 70, 11, 64)

    # ---- ActStep 内部展开 (y=30) ----
    _box(ax, 42, 30, 18, 12, "while iter < 5:\n_call_provider(msgs, tools)\nparse_tool_calls_from_text\ntools.execute(tc.name, args)", fontsize=7)
    _arrow(ax, 51, 50, 51, 42, "展开")

    # ---- 工具执行 (y=12) ----
    _box(ax, 24, 12, 18, 8, "ToolRegistry.execute()\nregistry.py:34", fontsize=7)
    _box(ax, 44, 12, 18, 8, "ToolAgent.execute()\n5 内置 Agent\n(vault_read/search/stats)", fontsize=7)
    _arrow(ax, 48, 30, 36, 20)
    _arrow(ax, 56, 30, 50, 20)

    # ---- E2E 验证标记 (底部, y=2) ----
    _box(ax, 2, 2, 20, 6, "E2E-04 简单任务\n4 LLM, 9.83s ✓", fontsize=6, fc="#F8F8F8")
    _box(ax, 24, 2, 20, 6, "E2E-05 工具调用\n4 LLM, 17.79s ✓", fontsize=6, fc="#F8F8F8")
    _box(ax, 48, 2, 20, 6, "E2E-25 完整周期\n10 LLM, 75.47s ✓", fontsize=6, fc="#F8F8F8")
    _box(ax, 72, 2, 24, 6, "★LLM#N = LLM 调用点\n[VAULT-WRITE] = vault 写入", fontsize=6, fc="#F8F8F8")

    ax.text(2, 96.5, "→ 调用方向    ★LLM#N = LLM 调用点    [VAULT-WRITE] = vault 写入",
            fontsize=7, color="#555555", va="top")

    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "e2e-01-pipeline-chain.png"),
                dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print("✓ e2e-01-pipeline-chain.png")


# ============================================================
# E2E Figure 2: ToolAgent 调用链
# ============================================================
def render_e2e_02_toolagent_chain():
    fig, ax = _setup_ax((16, 12))
    ax.set_title("E2E Figure 2 · ToolAgent 调用链 — VaultRead/Search/Stats 3 个 LLM 调用点 + redact 覆盖",
                 fontsize=14, weight="bold", pad=20)

    # 三列：Read / Search / Stats
    # 列 1: VaultReadAgent
    _box(ax, 2, 88, 30, 8, "VaultReadAgent.execute(input)\nvault_read.py:57", fontsize=8, weight="bold")
    _arrow(ax, 17, 88, 17, 82)
    _box(ax, 2, 70, 30, 8, "normalize_rel_path()\nvault_read.py:68\n路径归一化", fontsize=7)
    _arrow(ax, 17, 70, 17, 64)
    _box(ax, 2, 56, 30, 8, "blocked_prefixes 检查\nvault_read.py:71-76\nissue #38/#80", fontsize=7)
    _arrow(ax, 17, 56, 17, 50)
    _box(ax, 2, 42, 30, 8, "vault.read(rel_path)\nvault_read.py:85", fontsize=7)
    _arrow(ax, 17, 42, 17, 36)
    _box(ax, 2, 26, 30, 10, "_summarize(content, max_len)\nvault_read.py:110\n├ _redact_snippet[:2000]\n└ provider.generate_text ★LLM#4", fontsize=7)
    _box(ax, 2, 12, 30, 6, "E2E-06 ✓ PASS\n6.31s, 1 LLM, summary=80", fontsize=7, fc="#F8F8F8")

    # 列 2: VaultSearchAgent
    _box(ax, 35, 88, 30, 8, "VaultSearchAgent.execute(input)\nvault_search.py:65", fontsize=8, weight="bold")
    _arrow(ax, 50, 88, 50, 82)
    _box(ax, 35, 70, 30, 8, "list_growths_by_tag()\nlist_growths() 粗筛\nvault_search.py:79-85", fontsize=7)
    _arrow(ax, 50, 70, 50, 64)
    _box(ax, 35, 56, 30, 8, "全文过滤\n_snippet(body, q, redact=True)\n_redact_snippet [REDACT]", fontsize=7)
    _arrow(ax, 50, 56, 50, 50)
    _box(ax, 35, 42, 30, 8, "_semantic_rerank(matches, q)\nvault_search.py:151", fontsize=7)
    _arrow(ax, 50, 42, 50, 36)
    _box(ax, 35, 26, 30, 10, "_redact_snippet(m['snippet])\nprovider.generate_text ★LLM#5\n返回 rerank 后结果", fontsize=7)
    _box(ax, 35, 12, 30, 6, "E2E-07 ✓ PASS\n4.07s, 1 LLM, matches=1", fontsize=7, fc="#F8F8F8")

    # 列 3: VaultStatsAgent
    _box(ax, 68, 88, 30, 8, "VaultStatsAgent.execute(input)\nvault_stats.py:39", fontsize=8, weight="bold")
    _arrow(ax, 83, 88, 83, 82)
    _box(ax, 68, 70, 30, 8, "vault.list_growths()\nvault_stats.py:43", fontsize=7)
    _arrow(ax, 83, 70, 83, 64)
    _box(ax, 68, 56, 30, 8, "逐个 read_growth\n统计 by_dimension\n+ histogram", fontsize=7)
    _arrow(ax, 83, 56, 83, 50)
    _box(ax, 68, 42, 30, 8, "_analyze_stats(total,\nby_dim, hist)\nvault_stats.py:82", fontsize=7)
    _arrow(ax, 83, 42, 83, 36)
    _box(ax, 68, 26, 30, 10, "provider.generate_text ★LLM#6\n(无 redact —\n仅传聚合数字)", fontsize=7)
    _box(ax, 68, 12, 30, 6, "E2E-08 ✓ PASS\n50.11s, 1 LLM, analysis=有", fontsize=7, fc="#F8F8F8")

    # redact 标注
    _box(ax, 2, 2, 30, 6, "[REDACT] 点\n_summarize redact ✓", fontsize=7, fc="#F0F0F0")
    _box(ax, 35, 2, 30, 6, "[REDACT] 点 ×2\n_snippet + _semantic_rerank ✓", fontsize=7, fc="#F0F0F0")
    _box(ax, 68, 2, 30, 6, "无私密字段\n仅聚合数字", fontsize=7, fc="#F0F0F0")

    ax.text(33, 1, "★LLM#N = LLM 调用点  [REDACT] = redact 脱敏点  灰底=安全检查",
            fontsize=7, color="#555555")

    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "e2e-02-toolagent-chain.png"),
                dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print("✓ e2e-02-toolagent-chain.png")


# ============================================================
# E2E Figure 3: Reflect 调用链
# ============================================================
def render_e2e_03_reflect_chain():
    fig, ax = _setup_ax((16, 10))
    ax.set_title("E2E Figure 3 · Reflect 调用链 — session 加载 → LLM 反思 → emotion 打分 → vault 写入",
                 fontsize=14, weight="bold", pad=20)

    # 主流程
    _box(ax, 30, 88, 40, 8, "ReflectExecutor.run(session_paths, sessions_dir)\nexecutor.py:138", fontsize=8, weight="bold")
    _arrow(ax, 50, 88, 50, 82)

    # 步骤 1
    _box(ax, 5, 70, 25, 8, "_load_sessions()\nexecutor.py:153\nSession.load(parent, sid)", fontsize=7)
    _box(ax, 38, 70, 25, 8, "_summarize_sessions()\nexecutor.py:154\n拼文本 [session #i]...", fontsize=7)
    _box(ax, 70, 70, 25, 8, "_next_reflection_id()\nexecutor.py:161\n→ reflect-YYYY-MM-DD-NNN", fontsize=7)
    _arrow(ax, 18, 70, 38, 70)
    _arrow(ax, 50, 70, 70, 70)
    _arrow(ax, 50, 88, 18, 78)
    _arrow(ax, 50, 88, 50, 78)
    _arrow(ax, 50, 88, 82, 78)

    # 反思 + emotion (并列)
    _box(ax, 5, 50, 40, 12, "_generate_reflection(sessions_text)\nexecutor.py:231 ★LLM#8\nprompt: _REFLECT_PROMPT\n生成 80~150 字第一人称中文反思", fontsize=7)
    _box(ax, 55, 50, 40, 12, "score_emotion(provider, key, text)\nexecutor.py:159\n├ redact_snippet(text) [REDACT]\n├ provider.generate_text ★LLM#8b\n└ _parse_emotion_response → (v, a)", fontsize=7)
    _arrow(ax, 25, 70, 25, 62, "反思")
    _arrow(ax, 75, 70, 75, 62, "emotion")

    # 写入
    _box(ax, 30, 30, 40, 12, "vault.write(rel, content, whitelist=None)\nexecutor.py:175  [VAULT-WRITE]\n路径: mortis-subconscious/\n       pending-reflections/<rid>.md", fontsize=7)
    _arrow(ax, 25, 50, 35, 42, "写")
    _arrow(ax, 75, 50, 65, 42, "(emotion 附加)")

    # 数据结构
    _box(ax, 5, 14, 22, 10, "Reflection\nbody: 80~150 字\nvalence -1~1\narousal 0~1", fontsize=7, fc="#F8F8F8")
    _box(ax, 38, 14, 22, 10, "Emotion\nvalence, arousal\n→ emotion_weight = |v|×a\n(供 dream recall 用)", fontsize=7, fc="#F8F8F8")
    _box(ax, 70, 14, 25, 10, "pending-reflections/\n后续触发:\nLight/MediumDreamer RECALL\n扫描 session", fontsize=7, fc="#F8F8F8")
    _arrow(ax, 40, 30, 16, 24)
    _arrow(ax, 50, 30, 49, 24)
    _arrow(ax, 60, 30, 82, 24)

    # E2E 验证
    _box(ax, 5, 2, 35, 8, "E2E-11 ✓ PASS\n62.12s, 2 LLM (反思+emotion)\nbody 长度 5891, valence=0.00", fontsize=7, fc="#F0F0F0")
    _box(ax, 45, 2, 25, 8, "E2E-25 REFLECT 阶段\n2 次 LLM\nreflect=4650 字", fontsize=7, fc="#F0F0F0")
    _box(ax, 75, 2, 22, 8, "REDACT 覆盖\nscore_emotion\n已脱敏 ✓", fontsize=7, fc="#F0F0F0")

    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "e2e-03-reflect-chain.png"),
                dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print("✓ e2e-03-reflect-chain.png")


# ============================================================
# E2E Figure 4: Dream 流水线调用链
# ============================================================
def render_e2e_04_dream_chain():
    fig, ax = _setup_ax((16, 13))
    ax.set_title("E2E Figure 4 · Dream 流水线调用链 — Light 4 phase / Medium 5 phase / Deep 7 phase",
                 fontsize=14, weight="bold", pad=20)

    # Light (4 phase)
    ax.text(5, 92, "LightDreamer (4 phase) — E2E-12 ✓ 14.32s, 4 LLM", fontsize=11, weight="bold")
    light = [
        ("RECALL\nlight.py:103\n扫 sessions/\nscore_emotion ★LLM#9a\nemotion_weighted_sample", 3, 78),
        ("ASSOCIATE\nlight.py:196\nassociate() ★LLM#10\nredact ✓\n返回 {body, tags}", 26, 78),
        ("CRYSTALLIZE\nlight.py:219\ninfer_dimension\nmake_candidate conf=0.3\nwrite_growth [VAULT-WRITE]", 49, 78),
        ("RECONCILE\nlight.py:268\n_detect_conflicts\n_write_conflict\n[VAULT-WRITE]", 72, 78),
    ]
    for text, x, y in light:
        _box(ax, x, y, 22, 12, text, fontsize=7)
    for i in range(3):
        _arrow(ax, 25 + i * 23, 84, 26 + i * 23, 84)

    # Medium (5 phase)
    ax.text(5, 67, "MediumDreamer (5 phase) — E2E-13 ✓ 12.50s, 5 LLM", fontsize=11, weight="bold")
    medium = [
        ("RECALL\nmedium.py:91\n跨周采样", 3, 53),
        ("ASSOCIATE\nmedium.py:136\n★LLM", 23, 53),
        ("SIMULATE\nmedium.py:156\n启发式预演\nconf 0.3→0.5", 43, 53),
        ("CRYSTALLIZE\nmedium.py:201\n[VAULT-WRITE]", 63, 53),
        ("RECONCILE\nmedium.py:256\n[VAULT-WRITE]", 83, 53),
    ]
    for text, x, y in medium:
        _box(ax, x, y, 15, 12, text, fontsize=6)
    for i in range(4):
        _arrow(ax, 18 + i * 20, 59, 20 + i * 20, 59)

    # Deep (7 phase)
    ax.text(5, 42, "DeepDreamer (7 phase) — E2E-14 ✓ 8.90s, 7 LLM", fontsize=11, weight="bold")
    deep = [
        ("RECALL\ndeep.py:76\n重读全量", 1, 28),
        ("ASSOC\ndeep.py:100\n★LLM", 14, 28),
        ("SIM\ndeep.py:124", 27, 28),
        ("CRYST\ndeep.py:146\n[VAULT-W]", 40, 28),
        ("RECON\ndeep.py:174\n[VAULT-W]", 53, 28),
        ("ERODE\ndeep.py:223\n×0.85^days\n[VAULT-W]", 66, 28),
        ("SEED_CHECK\ndeep.py:264\n★LLM#7 redact\nlog_drift\n[VAULT-W]", 79, 28),
    ]
    for text, x, y in deep:
        _box(ax, x, y, 12, 12, text, fontsize=6)
    for i in range(6):
        _arrow(ax, 13 + i * 13, 34, 14 + i * 13, 34)

    # ERODE + SEED_CHECK 详细
    _box(ax, 1, 14, 45, 10, "phase_erode(): erode_growths(all) 按 last_validated 距今天数衰减\n  ├ survived → vault.write_growth(g) 重写\n  └ expired → vault.archive_growth(dim, id) os.rename 原子归档", fontsize=6)
    _box(ax, 50, 14, 48, 10, "phase_seed_check(): seed_check(seed, summary, provider, vault)\n  ├ redact_snippet(growth_summary)  ← issue #84 CRITICAL\n  ├ provider.generate_text ★LLM#7 → DriftReport(per_dim, total, needs_notify)\n  └ log_drift(vault) → mortis-subconscious/drift-log.json", fontsize=6)

    # E2E-15 单独
    _box(ax, 1, 4, 45, 8, "E2E-15 ✓ PASS\n12.01s, 1 LLM\ntotal_drift=0.60, needs_notify=False\nREDACT 覆盖 ✓", fontsize=7, fc="#F0F0F0")
    _box(ax, 50, 4, 48, 8, "信号产出\nGrowth confidence 0.3→0.5→衰减\nDriftReport 误报率监控\nemotion cache 不持久化", fontsize=7, fc="#F8F8F8")

    ax.text(33, 1, "★LLM#N = LLM 调用点  [VAULT-WRITE] = vault 写入  redact ✓ = 已脱敏",
            fontsize=7, color="#555555")

    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "e2e-04-dream-chain.png"),
                dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print("✓ e2e-04-dream-chain.png")


# ============================================================
# E2E Figure 5: 完整认知周期信息流转
# ============================================================
def render_e2e_05_info_flow():
    fig, ax = _setup_ax((16, 13))
    ax.set_title("E2E Figure 5 · 完整认知周期信息流转 — AWAKE→REFLECT→DREAM_LIGHT 端到端 (E2E-25)",
                 fontsize=14, weight="bold", pad=20)

    # 3 阶段
    # AWAKE
    _box(ax, 2, 88, 96, 6, "[1] AWAKE 阶段 (10 次 LLM 中的 4 次) — owner 输入 → session 落盘",
         fontsize=10, weight="bold", fc="#F5F5F5")

    _box(ax, 2, 76, 22, 8, "owner 输入\n\"总结你今天学到了什么\"", fontsize=7)
    _box(ax, 28, 76, 22, 8, "MasterRuntime\n.create_thread(task)\nmaster.py:49", fontsize=7)
    _box(ax, 54, 76, 22, 8, "RuntimeContext\n.make_context(thread, tools)\ncontext.py:130", fontsize=7)
    _box(ax, 80, 76, 18, 8, "session 落盘\nmortis-journal/\nsessions/<date>/<tid>.json", fontsize=7)
    _arrow(ax, 24, 80, 28, 80)
    _arrow(ax, 50, 80, 54, 80)
    _arrow(ax, 76, 80, 80, 80)

    # system prompt 注入
    _box(ax, 2, 62, 22, 8, "system[0] =\nseed.get_dimension('tone')\n人格语气", fontsize=7, fc="#F8F8F8")
    _box(ax, 28, 62, 22, 8, "system[1] =\nunease_prompt_for_injection()\n潜台词 (若有)", fontsize=7, fc="#F8F8F8")
    _box(ax, 54, 62, 22, 8, "system[2] =\ngrowth_context_for_task()\n相关 growth (已 redact)", fontsize=7, fc="#F8F8F8")
    _box(ax, 80, 62, 18, 8, "history =\nthread 对话历史", fontsize=7, fc="#F8F8F8")
    _arrow(ax, 65, 76, 13, 70)
    _arrow(ax, 65, 76, 39, 70)
    _arrow(ax, 65, 76, 65, 70)
    _arrow(ax, 89, 76, 89, 70)

    # Pipeline 4 步
    _box(ax, 2, 48, 22, 8, "ThinkStep ★LLM#1\n分析任务", fontsize=7)
    _box(ax, 28, 48, 22, 8, "PlanStep ★LLM#2\n拆解步骤", fontsize=7)
    _box(ax, 54, 48, 22, 8, "ActStep ★LLM#3\n执行(可能调工具)", fontsize=7)
    _box(ax, 80, 48, 18, 8, "ReviewStep ★LLM#4\n审阅产出", fontsize=7)
    for i in range(3):
        _arrow(ax, 24 + i * 26, 52, 28 + i * 26, 52)
    _arrow(ax, 65, 62, 13, 56)
    _arrow(ax, 65, 62, 39, 56)
    _arrow(ax, 65, 62, 65, 56)
    _arrow(ax, 89, 62, 89, 56)

    # thread.complete
    _box(ax, 28, 36, 44, 6, "thread.complete(output) → _save_thread() → 更新 sessions/<tid>.json", fontsize=7, fc="#F8F8F8")
    _arrow(ax, 89, 48, 50, 42)

    # REFLECT
    _box(ax, 2, 28, 96, 6, "[2] REFLECT 阶段 (2 次 LLM) — 读取 session → 生成反思 + emotion → vault 写入",
         fontsize=10, weight="bold", fc="#F5F5F5")
    _box(ax, 2, 16, 22, 8, "ReflectExecutor.run\n扫 sessions/<sid>.json", fontsize=7)
    _box(ax, 28, 16, 22, 8, "_generate_reflection ★LLM#8\n生成 80~150 字反思", fontsize=7)
    _box(ax, 54, 16, 22, 8, "score_emotion ★LLM#8b\nredact_snippet ✓\nvalence, arousal", fontsize=7)
    _box(ax, 80, 16, 18, 8, "vault.write\n[VAULT-WRITE]\npending-reflections/\n<rid>.md", fontsize=7)
    _arrow(ax, 24, 20, 28, 20)
    _arrow(ax, 50, 20, 54, 20)
    _arrow(ax, 76, 20, 80, 20)
    _arrow(ax, 50, 36, 13, 24)

    # DREAM_LIGHT
    _box(ax, 2, 8, 96, 6, "[3] DREAM_LIGHT 阶段 (4 次 LLM) — RECALL→ASSOCIATE→CRYSTALLIZE→RECONCILE",
         fontsize=10, weight="bold", fc="#F5F5F5")
    _box(ax, 2, 0, 22, 6, "RECALL ★LLM#9a\n扫 sessions + score_emotion\nemotion_weighted_sample", fontsize=6)
    _box(ax, 28, 0, 22, 6, "ASSOCIATE ★LLM#10\nredact ✓ → 找共同模式", fontsize=6)
    _box(ax, 54, 0, 22, 6, "CRYSTALLIZE\nwrite_growth [VAULT-WRITE]\n触发 watcher → unease", fontsize=6)
    _box(ax, 80, 0, 18, 6, "RECONCILE\n写 conflicts/\n[VAULT-WRITE]", fontsize=6)
    for i in range(3):
        _arrow(ax, 24 + i * 26, 3, 28 + i * 26, 3)
    _arrow(ax, 89, 16, 89, 8)
    _arrow(ax, 65, 16, 65, 8)
    _arrow(ax, 39, 16, 39, 8)
    _arrow(ax, 13, 16, 13, 8)

    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "e2e-05-info-flow.png"),
                dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print("✓ e2e-05-info-flow.png")


# ============================================================
# E2E Figure 6: 信号传播图
# ============================================================
def render_e2e_06_signal_flow():
    fig, ax = _setup_ax((16, 13))
    ax.set_title("E2E Figure 6 · 信号传播图 — growth 写入触发 watcher → unease 积累 → 注入 system prompt → 影响 LLM 输出",
                 fontsize=14, weight="bold", pad=20)

    # 顶部信号源链: 1→2→3→4 (水平)
    _box(ax, 2, 86, 20, 9,
         "1. 信号源\nLightDreamer.CRYSTALLIZE\nvault.write_growth [VAULT-WRITE]\nmortis-growth/<dim>/<id>.md",
         fontsize=7, weight="bold")
    _arrow(ax, 22, 90.5, 25, 90.5, "文件变更")

    _box(ax, 25, 86, 20, 9,
         "2. GrowthWatcher\nwatchdog Observer\nwatcher.py:169\nhandler._on_modified\n提取 Dimension",
         fontsize=7)
    _arrow(ax, 45, 90.5, 48, 90.5, "callback(dim)")

    _box(ax, 48, 86, 20, 9,
         "3. SteinerController\n_on_edit(dim)\nlifecycle.py:47\ndebounce 1s",
         fontsize=7)
    _arrow(ax, 68, 90.5, 71, 90.5)

    _box(ax, 71, 86, 27, 9,
         "4. accumulate + save\nunease.py:150\nper_dimension[dim] += 0.1\n→ save_unease [VAULT-WRITE]\nmortis-steiner/unease.json",
         fontsize=7, weight="bold")

    # 4 → 5 "读取 unease": L 形（先下后左），标签落在空白区，不压任何框
    _arrow(ax, 72, 86, 72, 82)
    _arrow(ax, 72, 82, 28, 82, "读取 unease")
    _arrow(ax, 28, 82, 28, 80)

    # 4 → 7 "drift 出口": 垂直向下
    _arrow(ax, 88, 86, 88, 76, "drift 出口")

    # 左列: 注入链 (5 → unease_prompt_for_injection → unease_prompt → Message → LLM)
    _box(ax, 2, 72, 26, 8,
         "5. RuntimeContext\nmessages_for_provider()\ncontext.py:130",
         fontsize=7, weight="bold")
    _arrow(ax, 15, 72, 15, 68, "调用")

    _box(ax, 2, 60, 26, 8,
         "unease_prompt_for_injection()\ncontext.py:110\nload_unease + decay",
         fontsize=7)
    _arrow(ax, 15, 60, 15, 56)

    _box(ax, 2, 48, 26, 8,
         "unease_prompt(state)\nprompt.py:53\n5 档文案 (none/light/\nmedium/heavy/severe)",
         fontsize=7)
    _arrow(ax, 15, 48, 15, 44)

    _box(ax, 2, 36, 26, 8,
         "Message(role=system,\ncontent=unease_text)\n注入位置: tone 之后\ngrowth 之前",
         fontsize=7)
    _arrow(ax, 15, 36, 15, 32, "注入")

    _box(ax, 2, 22, 26, 10,
         "6. LLM 调用 ★LLM#1-#4\nThinkStep/PlanStep/ActStep\n/ReviewStep\nctx.provider.generate(messages)\nmessages[0] 含 unease 潜台词",
         fontsize=7, weight="bold")

    # 右列: drift 链 (7 → 8)
    _box(ax, 71, 66, 27, 10,
         "7. drift 检测 (DeepDreamer)\nseed_check(seed, growth_summary,\nprovider, vault) ★LLM#7\nredact_snippet ✓\n→ DriftReport",
         fontsize=7, weight="bold")
    _arrow(ax, 84, 66, 84, 62, "drift 报警")

    _box(ax, 71, 52, 27, 10,
         "8. should_notify_owner(unease)\ndrift.py:22\nmax(per_dim) ≥ 0.75\n→ owner-notify.json [VAULT-WRITE]\n→ web/notify.py",
         fontsize=7, weight="bold")

    # 8 → 9 "owner 编辑": 斜线穿过右下空白区
    _arrow(ax, 84, 52, 60, 18, "owner 收到报警", ls="--", lw=1.2)

    # 9. 闭环 (底部居中)
    _box(ax, 30, 8, 40, 10,
         "9. 闭环\nowner 收到 drift 报警 → 编辑 growth 记忆\n→ 回到 step 1 (GrowthWatcher 检测文件变更)",
         fontsize=7, fc="#F8F8F8", weight="bold")

    # 9 → 1 闭环反馈: 沿左边距向上 (x=1)，不压任何左列框
    _arrow(ax, 30, 13, 1, 13, ls="--", lw=1.2)
    _arrow(ax, 1, 13, 1, 90, "owner 编辑 growth → step 1", ls="--", lw=1.2)
    _arrow(ax, 1, 90, 2, 90, ls="--", lw=1.2)

    # LLM → 闭环
    _arrow(ax, 15, 22, 35, 18)

    ax.text(33, 1, "→ 信号传递    ╌ 闭环反馈    ★LLM#N = LLM 调用点    [VAULT-WRITE] = vault 写入",
            fontsize=7, color="#555555")

    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "e2e-06-signal-flow.png"),
                dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print("✓ e2e-06-signal-flow.png")


if __name__ == "__main__":
    render_01_arch_layers()
    render_02_pipeline_flow()
    render_03_dream_pipeline()
    render_04_signal_flow()
    render_05_vault_defense()
    render_06_task_flow()
    render_07_dream_cycle()
    render_08_steiner_hidden()
    render_09_test_coverage()
    render_10_timeline()
    render_e2e_01_pipeline_chain()
    render_e2e_02_toolagent_chain()
    render_e2e_03_reflect_chain()
    render_e2e_04_dream_chain()
    render_e2e_05_info_flow()
    render_e2e_06_signal_flow()
    print("\n全部 16 张图渲染完成 (10 审计 + 6 E2E)")

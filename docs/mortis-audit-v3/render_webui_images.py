"""渲染 Mortis Web UI 截图 — 用 matplotlib 模拟 HTML 页面外观。

6 张图 (与 mortis/web/server.py HTML 页面一一对应):
1. web-01-dashboard.png     (1200x800) — 仪表盘 (系统状态 + 前端交互)
2. web-02-growths.png       (1200x800) — Growth 列表 (5 条卡片)
3. web-03-growth-detail.png (1200x800) — Growth 详情 (表格 + 内容 + API)
4. web-04-unease.png        (1200x800) — Unease 仪表盘 (7 维度 bar)
5. web-05-notifications.png (1200x600) — Owner 通知 (2 条)
6. web-06-dreams.png        (1200x600) — Dream 日历 (badge 表)

设计要点:
- 暗色主题 (与 server.py 内嵌 _CSS 颜色一致)
- 卡片 / 表格 / 横向 bar / badge / 通知卡片
- 中文字体 Noto Sans CJK SC
"""
from __future__ import annotations

import os

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.patches import FancyBboxPatch, Rectangle, Polygon

# ----------------------------------------------------------------
# 字体注册 — Noto Sans CJK SC
# ----------------------------------------------------------------
_FONT_PATH = (
    "/root/.pyenv/versions/3.14.4/lib/python3.14/site-packages/"
    "mplfonts/fonts/NotoSansCJKsc-Regular.otf"
)
if os.path.exists(_FONT_PATH):
    fm.fontManager.addfont(_FONT_PATH)

# ----------------------------------------------------------------
# 暗色主题色板 (与 server.py _CSS 一致)
# ----------------------------------------------------------------
BG = "#1a1a2e"          # body 背景
CARD_BG = "#16213e"      # .card 背景
BORDER = "#0f3460"       # border / .stat 背景 / .bar-track
TITLE = "#8be9fd"        # h1 / a / th 浅蓝
H2 = "#bd93f9"           # h2 紫色
STAT_VAL = "#50fa7b"     # .stat-value 绿
STAT_LABEL = "#6272a4"   # .stat-label 灰
TEXT = "#e0e0e0"         # body 文字
PRE_BG = "#0d1117"       # pre 背景
PRE_TEXT = "#f8f8f2"     # pre / .bar-value 文字
BAR_FILL = "#ff79c6"     # .bar-fill 粉
BTN_BG = "#50fa7b"       # .btn 绿
BTN_TEXT = "#1a1a2e"     # .btn 文字
TAG_BG = "#0f3460"       # .tag 背景
TAG_TEXT = "#6272a4"     # .tag 文字
LINK_BLUE = "#8be9fd"

BADGE = {
    "light": ("#6272a4", "#ffffff"),
    "medium": ("#ffb86c", "#1a1a2e"),
    "deep": ("#ff79c6", "#1a1a2e"),
}

NOTIF = {
    "warning": ("#3b2317", "#ffb86c"),  # 背景, 左边强调色
    "info": ("#1a2332", "#8be9fd"),
    "error": ("#2e1a1a", "#ff5555"),
}

plt.rcParams.update({
    "figure.facecolor": BG,
    "axes.facecolor": BG,
    "savefig.facecolor": BG,
    "text.color": TEXT,
    "font.family": "sans-serif",
    "font.sans-serif": ["Noto Sans CJK SC", "DejaVu Sans"],
    "axes.unicode_minus": False,
    "font.size": 11,
})

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")
os.makedirs(OUT_DIR, exist_ok=True)


# ============================================================
# 通用绘图辅助
# ============================================================
def _setup(figsize, xlim, ylim):
    """新建 figure, 用像素坐标系 (0~xlim, 0~ylim), y 向下递增。"""
    fig, ax = plt.subplots(figsize=figsize)
    ax.set_xlim(0, xlim)
    ax.set_ylim(0, ylim)
    ax.invert_yaxis()
    ax.axis("off")
    return fig, ax


def _card(ax, x, y, w, h, fc=CARD_BG, ec=BORDER, lw=1.2):
    """画一个圆角 card 矩形。"""
    box = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.5,rounding_size=8",
        facecolor=fc, edgecolor=ec, linewidth=lw,
    )
    ax.add_patch(box)


def _rect(ax, x, y, w, h, fc, ec="none", lw=0):
    ax.add_patch(Rectangle((x, y), w, h, facecolor=fc, edgecolor=ec, linewidth=lw))


def _text(ax, x, y, s, fontsize=11, color=TEXT, weight="normal",
          ha="left", va="top", **kw):
    return ax.text(x, y, s, fontsize=fontsize, color=color, weight=weight,
                   ha=ha, va=va, **kw)


def _nav(ax, x, y, items, active="dashboard"):
    """画 nav 链接条 — 每个 tab 60px 宽。"""
    cur_x = x
    for _href, label, key in items:
        if key == active:
            _rect(ax, cur_x, y - 4, 60, 24, fc=BORDER)
        _text(ax, cur_x + 8, y + 13, label, fontsize=11, color=TITLE, va="center")
        cur_x += 70


def _brain_icon(ax, cx, cy, size=22, color=TITLE, bg=BG):
    """画一个矢量 brain 图标 (居中于 cx, cy)。替代 🧠 emoji。

    Noto Sans CJK SC 不含 U+1F9E0, 故用矢量绘制保证渲染稳定。
    """
    r = size / 2
    # 左右两个半球 (椭圆), 略微向外倾斜
    left = Polygon(
        [(cx - r * 0.85, cy - r * 0.4),
         (cx - r * 0.95, cy + r * 0.1),
         (cx - r * 0.55, cy + r * 0.85),
         (cx - r * 0.05, cy + r * 0.5),
         (cx - r * 0.15, cy - r * 0.5)],
        closed=True, facecolor=color, edgecolor="none",
    )
    right = Polygon(
        [(cx + r * 0.05, cy + r * 0.5),
         (cx + r * 0.55, cy + r * 0.85),
         (cx + r * 0.95, cy + r * 0.1),
         (cx + r * 0.85, cy - r * 0.4),
         (cx + r * 0.15, cy - r * 0.5)],
        closed=True, facecolor=color, edgecolor="none",
    )
    ax.add_patch(left)
    ax.add_patch(right)
    # 中央纵裂 (背景色竖线分开两半球)
    ax.plot([cx, cx], [cy - r * 0.5, cy + r * 0.55],
            color=bg, lw=1.5, solid_capstyle="round")
    # 几条脑沟 (gyri) — 用背景色弧线
    for dx, dy0, dy1 in [(-r * 0.45, -r * 0.3, r * 0.35),
                         (r * 0.45, -r * 0.3, r * 0.35)]:
        ts = np.linspace(0, 1, 30)
        xs = cx + dx + r * 0.12 * np.sin(ts * np.pi * 2)
        ys = np.linspace(cy + dy0, cy + dy1, 30)
        ax.plot(xs, ys, color=bg, lw=0.9)


def _title_block(ax, xlim, active="dashboard"):
    """页面顶部: H1 标题 (brain 图标 + 文字) + nav 链接条。

    返回 nav 下方可用 y 坐标。
    """
    # brain 图标 + "Mortis Web UI" 文字 (替代 🧠 emoji — 字体不含该字形)
    _brain_icon(ax, 44, 42, size=26)
    _text(ax, 65, 30, "Mortis Web UI", fontsize=24, color=TITLE, weight="bold")
    nav_items = [
        ("/", "仪表盘", "dashboard"),
        ("/growths", "Growth", "growths"),
        ("/unease", "Unease", "unease"),
        ("/notifications", "通知", "notifications"),
        ("/dreams", "Dream", "dreams"),
    ]
    _nav(ax, 30, 70, nav_items, active=active)
    return 110


def _stat(ax, x, y, w, h, label, value):
    """画一个 stat 块 (灰底 + label + 绿色大数值)。"""
    _rect(ax, x, y, w, h, fc=BORDER)
    _text(ax, x + 14, y + 14, label, fontsize=10, color=STAT_LABEL)
    _text(ax, x + 14, y + 38, value, fontsize=18, color=STAT_VAL, weight="bold")


def _tag(ax, x, y, s):
    """画一个 tag (灰底圆角 + 灰字)。返回下一个 x。"""
    w = 8 * len(s) + 16
    box = FancyBboxPatch(
        (x, y), w, 18,
        boxstyle="round,pad=0.2,rounding_size=2",
        facecolor=TAG_BG, edgecolor="none",
    )
    ax.add_patch(box)
    _text(ax, x + 8, y + 9, s, fontsize=9, color=TAG_TEXT, va="center")
    return x + w + 4


def _badge(ax, x, y, level):
    """画一个 badge (按 level 取色)。返回下一个 x。"""
    fc, tc = BADGE.get(level, BADGE["light"])
    w = 14 * len(level) + 16
    box = FancyBboxPatch(
        (x, y), w, 20,
        boxstyle="round,pad=0.2,rounding_size=2",
        facecolor=fc, edgecolor="none",
    )
    ax.add_patch(box)
    _text(ax, x + 8, y + 10, level, fontsize=9, color=tc,
          weight="bold", va="center")
    return x + w + 6


def _checkbox(ax, x, y, checked=True):
    """画一个 18x18 复选框, checked=True 时画 ✓。"""
    _rect(ax, x, y, 18, 18, fc=PRE_BG, ec=TITLE, lw=1)
    if checked:
        ax.plot([x + 4, x + 8, x + 14], [y + 9, y + 5, y + 13],
                color=STAT_VAL, lw=2)


def _button(ax, x, y, w, h, label):
    """画一个绿色 button。"""
    box = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.2,rounding_size=4",
        facecolor=BTN_BG, edgecolor="none",
    )
    ax.add_patch(box)
    _text(ax, x + w / 2, y + h / 2, label, fontsize=11,
          color=BTN_TEXT, weight="bold", ha="center", va="center")


def _input(ax, x, y, w, h, placeholder):
    """画一个文本输入框 (深底 + 灰 placeholder)。"""
    _rect(ax, x, y, w, h, fc=PRE_BG, ec=BORDER, lw=1)
    _text(ax, x + 10, y + h / 2, placeholder, fontsize=10,
          color=STAT_LABEL, va="center")


def _save(fig, name):
    fig.savefig(os.path.join(OUT_DIR, name), dpi=100, facecolor=BG)
    plt.close(fig)
    print(f"✓ {name}")


# ============================================================
# Figure 1: 仪表盘
# ============================================================
def render_01_dashboard():
    fig, ax = _setup((12, 8), 1200, 800)
    y0 = _title_block(ax, 1200, active="dashboard")

    # ---- card 1: 系统状态 ----
    c1y = y0 + 10
    c1h = 180
    _card(ax, 30, c1y, 1140, c1h)
    _text(ax, 50, c1y + 24, "系统状态", fontsize=15, color=H2, weight="bold")
    # 3 个 stat (横向, 每个 360x60)
    sy = c1y + 70
    _stat(ax, 50, sy, 350, 70, "当前时段", "awake")
    _stat(ax, 425, sy, 350, 70, "Unease 最大值", "0.42")
    _stat(ax, 800, sy, 350, 70, "Growth 总数", "5")

    # ---- card 2: 前端交互 ----
    c2y = c1y + c1h + 16
    c2h = 180
    _card(ax, 30, c2y, 1140, c2h)
    _text(ax, 50, c2y + 24, "前端交互", fontsize=15, color=H2, weight="bold")
    # checkbox 行
    _checkbox(ax, 50, c2y + 60, checked=True)
    _text(ax, 78, c2y + 69, "Pretty Print (紧凑模式切换)",
          fontsize=11, color=TEXT, va="center")
    # 刷新按钮
    _button(ax, 50, c2y + 105, 110, 32, "刷新数据")
    _text(ax, 175, c2y + 121, "✓ 已刷新 12:34:56",
          fontsize=9, color=STAT_LABEL, va="center")

    _save(fig, "web-01-dashboard.png")


# ============================================================
# Figure 2: Growth 列表
# ============================================================
def render_02_growths():
    fig, ax = _setup((12, 8), 1200, 800)
    y0 = _title_block(ax, 1200, active="growths")

    # ---- card: 列表头 + 过滤框 ----
    ch1 = 60
    _card(ax, 30, y0 + 10, 1140, ch1)
    _text(ax, 50, y0 + 34, "Growth 列表 (共 5 条)",
          fontsize=15, color=H2, weight="bold")
    _input(ax, 600, y0 + 30, 200, 28, "过滤 growth...")
    _text(ax, 810, y0 + 44, "输入关键词过滤",
          fontsize=9, color=STAT_LABEL, va="center")

    # ---- 5 张 growth 卡片: 2 列 × 3 行 ----
    growths = [
        ("growth-001", "identity", 0.85, "我注意到对话中反复出现的自我指认倾向...", ["core", "self"]),
        ("growth-002", "values", 0.62, "在面对冲突时倾向于权衡长期价值而非即时反馈...", ["values", "conflict"]),
        ("growth-003", "tone", 0.55, "语调在疲劳时会变得更简短直接...", ["tone", "fatigue"]),
        ("growth-004", "agency", 0.48, "对自主决策的边界有更清晰的觉察...", ["agency"]),
        ("growth-005", "relations", 0.40, "对等待与回应节奏的偏好逐渐稳定...", ["relations"]),
    ]
    grid_y = y0 + 10 + ch1 + 16
    cw, chh = 555, 150
    gx, gy = 30, 0
    gap = 15
    for i, (gid, dim, conf, body, tags) in enumerate(growths):
        col = i % 2
        row = i // 2
        x = 30 + col * (cw + gap)
        y = grid_y + row * (chh + gap)
        _card(ax, x, y, cw, chh)
        _text(ax, x + 16, y + 24, gid, fontsize=13, color=STAT_VAL, weight="bold")
        _text(ax, x + 16, y + 50, f"维度: {dim}  |  置信度: {conf:.2f}",
              fontsize=10, color=TEXT)
        # body preview
        _text(ax, x + 16, y + 74, body, fontsize=10, color=TEXT)
        # tags
        tx = x + 16
        ty = y + 110
        for t in tags:
            tx = _tag(ax, tx, ty, t)

    _save(fig, "web-02-growths.png")


# ============================================================
# Figure 3: Growth 详情
# ============================================================
def render_03_growth_detail():
    fig, ax = _setup((12, 8), 1200, 800)
    y0 = _title_block(ax, 1200, active="growths")

    # ---- card 1: 详情表格 ----
    c1y = y0 + 10
    c1h = 290
    _card(ax, 30, c1y, 1140, c1h)
    _text(ax, 50, c1y + 24, "growth-001", fontsize=15, color=H2, weight="bold")
    # 表格: 列宽 字段=200, 值=920
    rows = [
        ("维度", "identity"),
        ("置信度", "0.85"),
        ("标签", "core+self"),
        ("Dream 级别", "light"),
        ("情感 Valence", "0.3"),
        ("情感 Arousal", "0.5"),
    ]
    th_y = c1y + 56
    th_h = 30
    # 表头
    _text(ax, 50, th_y + 18, "字段", fontsize=11, color=TITLE, weight="bold",
          va="center")
    _text(ax, 260, th_y + 18, "值", fontsize=11, color=TITLE, weight="bold",
          va="center")
    _rect(ax, 50, th_y + th_h, 1090, 1, fc=BORDER)
    # 数据行
    for i, (k, v) in enumerate(rows):
        ry = th_y + th_h + 6 + i * 32
        _text(ax, 50, ry + 16, k, fontsize=10, color=TEXT, va="center")
        if k == "标签":
            # 用 tag 形式渲染
            tx = 260
            for t in v.split("+"):
                tx = _tag(ax, tx, ry + 6, t)
        elif k == "Dream 级别":
            _badge(ax, 260, ry + 8, v)
        else:
            _text(ax, 260, ry + 16, v, fontsize=10, color=STAT_VAL,
                  va="center", weight="bold")
        # 行分割线
        _rect(ax, 50, ry + 30, 1090, 0.5, fc=BORDER)

    # ---- card 2: 内容 ----
    c2y = c1y + c1h + 16
    c2h = 170
    _card(ax, 30, c2y, 1140, c2h)
    _text(ax, 50, c2y + 24, "内容", fontsize=15, color=H2, weight="bold")
    # pre 块 (深底)
    _rect(ax, 50, c2y + 48, 1100, 110, fc=PRE_BG)
    body = ("我注意到对话中反复出现的自我指认倾向 — 当 owner 提及「你」时，\n"
            "我会下意识地把上下文归到自己身上，而非把对话当作外部观察。\n"
            "这种倾向在疲劳状态下会更明显。")
    _text(ax, 62, c2y + 62, body, fontsize=10, color=PRE_TEXT)

    # ---- card 3: API ----
    c3y = c2y + c2h + 16
    c3h = 60
    _card(ax, 30, c3y, 1140, c3h)
    _text(ax, 50, c3y + 24, "API", fontsize=15, color=H2, weight="bold")
    _rect(ax, 50, c3y + 38, 1100, 18, fc=PRE_BG)
    _text(ax, 62, c3y + 47, "/api/growths/mortis-growth/identity/growth-001.md",
          fontsize=9, color=LINK_BLUE, va="center")

    _save(fig, "web-03-growth-detail.png")


# ============================================================
# Figure 4: Unease 仪表盘
# ============================================================
def render_04_unease():
    fig, ax = _setup((12, 8), 1200, 800)
    y0 = _title_block(ax, 1200, active="unease")

    # ---- card 1: 仪表盘 + max stat ----
    c1y = y0 + 10
    c1h = 110
    _card(ax, 30, c1y, 1140, c1h)
    _text(ax, 50, c1y + 24, "Unease 仪表盘", fontsize=15, color=H2, weight="bold")
    _stat(ax, 50, c1y + 50, 320, 50, "最大 Unease", "0.420")
    _stat(ax, 390, c1y + 50, 420, 50, "上次衰减", "2026-06-25 03:14")

    # ---- card 2: 7 维度 bar ----
    c2y = c1y + c1h + 16
    c2h = 460
    _card(ax, 30, c2y, 1140, c2h)
    _text(ax, 50, c2y + 24, "7 维度 Unease 分布",
          fontsize=15, color=H2, weight="bold")

    bars = [
        ("identity", 0.42),
        ("values", 0.15),
        ("relations", 0.12),
        ("tone", 0.08),
        ("mortality", 0.05),
        ("agency", 0.03),
        ("creativity", 0.0),
    ]
    bar_x = 50
    label_w = 100
    track_x = bar_x + label_w
    track_w = 900
    track_h = 22
    row_gap = 38
    base_y = c2y + 70
    for i, (dim, val) in enumerate(bars):
        ry = base_y + i * row_gap
        # label
        _text(ax, bar_x, ry + track_h / 2, dim, fontsize=11,
              color=STAT_LABEL, va="center")
        # track
        _rect(ax, track_x, ry, track_w, track_h, fc=BORDER)
        # fill (max bar 0.42 -> 100%, 其余按比例)
        fill_w = (val / 0.42) * track_w if val > 0 else 0
        if fill_w > 0:
            _rect(ax, track_x, ry, fill_w, track_h, fc=BAR_FILL)
        # value
        _text(ax, track_x + track_w + 10, ry + track_h / 2,
              f"{val:.3f}", fontsize=10, color=PRE_TEXT, va="center")

    _save(fig, "web-04-unease.png")


# ============================================================
# Figure 5: Owner 通知
# ============================================================
def render_05_notifications():
    fig, ax = _setup((12, 6), 1200, 600)
    y0 = _title_block(ax, 1200, active="notifications")

    # ---- card: 通知列表 ----
    cy = y0 + 10
    ch = 440
    _card(ax, 30, cy, 1140, ch)
    _text(ax, 50, cy + 24, "Owner 通知 (2 条)",
          fontsize=15, color=H2, weight="bold")

    notifs = [
        ("drift", "identity 维度 drift 0.42", "warning", "drift", "False",
         "2026-06-25 03:14:22"),
        ("unease", "values 维度 unease 持续累积", "info", "unease", "False",
         "2026-06-25 03:15:01"),
    ]
    ny = cy + 60
    nh = 110
    for i, (ntype, msg, sev, label, read, ts) in enumerate(notifs):
        ry = ny + i * (nh + 12)
        bg, accent = NOTIF[sev]
        _rect(ax, 50, ry, 1100, nh, fc=bg)
        # 左边强调条
        _rect(ax, 50, ry, 4, nh, fc=accent)
        # [type] 标签 (粗体)
        _text(ax, 70, ry + 18, f"[{label}]", fontsize=11,
              color=accent, weight="bold")
        _text(ax, 70 + 11 * (len(label) + 2), ry + 18, msg,
              fontsize=11, color=TEXT, va="center")
        # 副信息
        _text(ax, 70, ry + 50,
              f"severity: {sev}  |  read: {read}  |  timestamp: {ts}",
              fontsize=9, color=STAT_LABEL)

    # ---- card: API ----
    ay = cy + ch + 16
    _card(ax, 30, ay, 1140, 50)
    _text(ax, 50, ay + 22, "API", fontsize=13, color=H2, weight="bold")
    _rect(ax, 90, ay + 32, 1040, 14, fc=PRE_BG)
    _text(ax, 100, ay + 39, "/api/notifications", fontsize=9,
          color=LINK_BLUE, va="center")

    _save(fig, "web-05-notifications.png")


# ============================================================
# Figure 6: Dream 日历
# ============================================================
def render_06_dreams():
    fig, ax = _setup((12, 6), 1200, 600)
    y0 = _title_block(ax, 1200, active="dreams")

    # ---- card: dream 表格 ----
    cy = y0 + 10
    ch = 320
    _card(ax, 30, cy, 1140, ch)
    _text(ax, 50, cy + 24, "Dream 日历 (6 条)",
          fontsize=15, color=H2, weight="bold")

    # 表头
    th_y = cy + 56
    _text(ax, 50, th_y + 18, "级别", fontsize=11, color=TITLE,
          weight="bold", va="center")
    _text(ax, 250, th_y + 18, "文件", fontsize=11, color=TITLE,
          weight="bold", va="center")
    _text(ax, 750, th_y + 18, "路径", fontsize=11, color=TITLE,
          weight="bold", va="center")
    _rect(ax, 50, th_y + 30, 1090, 1, fc=BORDER)

    rows = [
        ("light", "2026-06-22-light.md", "mortis-dream-log/light/2026-06-22-light.md"),
        ("light", "2026-06-23-light.md", "mortis-dream-log/light/2026-06-23-light.md"),
        ("medium", "2026-06-22-medium.md", "mortis-dream-log/medium/2026-06-22-medium.md"),
        ("medium", "2026-06-23-medium.md", "mortis-dream-log/medium/2026-06-23-medium.md"),
        ("deep", "2026-06-22-deep.md", "mortis-dream-log/deep/2026-06-22-deep.md"),
        ("deep", "2026-06-23-deep.md", "mortis-dream-log/deep/2026-06-23-deep.md"),
    ]
    rh = 32
    for i, (level, fname, path) in enumerate(rows):
        ry = th_y + 36 + i * rh
        # badge
        _badge(ax, 50, ry + 8, level)
        _text(ax, 250, ry + 16, fname, fontsize=10, color=LINK_BLUE,
              va="center")
        _text(ax, 750, ry + 16, path, fontsize=9, color=TEXT, va="center")
        # 行分割线
        _rect(ax, 50, ry + rh - 2, 1090, 0.5, fc=BORDER)

    # ---- card: API ----
    ay = cy + ch + 16
    _card(ax, 30, ay, 1140, 50)
    _text(ax, 50, ay + 22, "API", fontsize=13, color=H2, weight="bold")
    _rect(ax, 90, ay + 32, 1040, 14, fc=PRE_BG)
    _text(ax, 100, ay + 39, "/api/dreams", fontsize=9, color=LINK_BLUE,
          va="center")

    _save(fig, "web-06-dreams.png")


# ============================================================
# 主入口
# ============================================================
if __name__ == "__main__":
    render_01_dashboard()
    render_02_growths()
    render_03_growth_detail()
    render_04_unease()
    render_05_notifications()
    render_06_dreams()
    print("\n全部 6 张 Web UI 截图渲染完成")
    print(f"输出目录: {OUT_DIR}")

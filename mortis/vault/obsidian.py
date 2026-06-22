"""Mortis Obsidian 语法解析层。

issue #19: vault 文件按 Obsidian-Native 格式存储,需要解析:
- [[wikilink]]  /  [[wikilink|alias]]   —— 双链
- ![[embed]]    /  ![[embed|alias]]     —— 嵌入
- #tag                                    —— 正文中标签(区别于 frontmatter tags)
- > [!note] ...    > [!warning] ...       —— callout 元认知
- %%comment%%                             —— 潜意识注释(默认不读入 prompt)
- 代码块围栏 (```...```)                  —— 内部内容视为字面量,不做解析
- 折叠区  ``%%...%%``(单行)/ ``%%%...%%%``(块) —— 折叠区,默认隐藏

设计原则 (RFC §12.2):
- 解析器**纯文本 → 结构化对象** (无副作用)。
- 渲染函数**结构化对象 → 纯文本** (无副作用)。
- 解析 → 渲染 往返 (round-trip) 允许内部规范化 (空白/空行)。
- 嵌入 (`![[...]]`) 解析后,target 字段保留 vault 内的相对路径 — 跨文件引用解析
  留给调用方 (mortis.growth.writer 或更高层),本层只做文本级解析。
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ============================================================
# 数据结构
# ============================================================


@dataclass(frozen=True)
class Wikilink:
    """`[[双链]]` 或 `![[嵌入]]` 解析后的对象。

    target: 目标名 / 相对路径 (不含别名和锚点段 — 解析时拆分)。
    alias: 可选别名 (即 `[[target|alias]]` 中的 alias)。
    is_embed: True 表示 `![[...]]` 嵌入,False 表示 `[[...]]` 双链。
    """

    target: str
    alias: str | None = None
    is_embed: bool = False

    def render(self) -> str:
        """还原为 Obsidian 文本。"""
        prefix = "!" if self.is_embed else ""
        if self.alias is not None:
            return f"{prefix}[[{self.target}|{self.alias}]]"
        return f"{prefix}[[{self.target}]]"


@dataclass(frozen=True)
class Callout:
    """`> [!kind] body` callout 块。

    kind: callout 类型 (note/warning/tip/danger/info/example/quote/...)。
    title: 可选标题 (即 `> [!kind] title` 后面的文本)。
    body: 主体内容 (去掉 `> ` 前缀后的累积行)。
    """

    kind: str
    body: str
    title: str | None = None

    def render(self) -> str:
        """还原为 Obsidian 文本。"""
        head = f"> [!{self.kind}]"
        if self.title is not None:
            head += f" {self.title}"
        lines = [head] + [f"> {line}" if line else ">" for line in self.body.splitlines()]
        return "\n".join(lines)


@dataclass(frozen=True)
class Fold:
    """``%%...%%`` 折叠区(单行或块)。

    body: 折叠区内部文本(原样保留)。
    """

    body: str

    def render(self) -> str:
        return f"%%\n{self.body}\n%%"


@dataclass(frozen=True)
class ParsedObsidian:
    """Obsidian 文本解析后的完整结构。

    body: 经过规范化后的纯文本主体 — 包含 wikilinks/callouts 的**原始文本**
          (即不把双链/标签从文中剔除;这些语法是**结构上的**,读 prompt 时
          走 [tags_inline]/[wikilinks] 字段,正文保留原貌)。
          **但** `%%comment%%` 和 `%%fold%%` 区在 body 中被**移除** — 它们
          单独存到对应字段。
    wikilinks: 文中所有 `[[...]]` 双链 (按出现顺序)。
    embed_links: 文中所有 `![[...]]` 嵌入 (按出现顺序)。
    tags_inline: 文中所有 `#tag` 标签(排除出现在代码块内的)。
    callouts: 文中所有 `> [!kind] ...` callout 块。
    comments: 文中所有 `%%...%%` 潜意识注释(单行,不含折叠)。
    foldable_sections: 文中所有 `%%\\n...\\n%%` 折叠块。
    """

    body: str
    wikilinks: tuple[Wikilink, ...] = field(default_factory=tuple)
    embed_links: tuple[Wikilink, ...] = field(default_factory=tuple)
    tags_inline: tuple[str, ...] = field(default_factory=tuple)
    callouts: tuple[Callout, ...] = field(default_factory=tuple)
    comments: tuple[str, ...] = field(default_factory=tuple)
    foldable_sections: tuple[Fold, ...] = field(default_factory=tuple)


# ============================================================
# 解析
# ============================================================


# 行内 `[[...]]` / `![[...]]` (非贪婪,允许内部 | 切分 alias)
_WIKILINK_RE = __import__("re").compile(
    r"(!?)\[\[([^\[\]\n|]+?)(?:\|([^\[\]\n]+?))?\]\]"
)
# 行内 `#tag` — 字母/数字/中文/下划线/短横,至少 1 字符,前面必须是空白/行首/标点
_TAG_RE = __import__("re").compile(
    r"(?:^|[\s(\[])(#[\w\u4e00-\u9fff-]+)"
)
# 代码块围栏
_FENCE_RE = __import__("re").compile(r"^(\s*)(```+|~~~+)(.*)$")
# callout 行首: `> [!kind] optional title`
_CALLOUT_RE = __import__("re").compile(r"^>\s*\[!(\w+)\]\s*(.*)$")
# 折叠块边界
_FOLD_BLOCK_OPEN = "%%"
# 单行注释 `%% ... %%`(非贪婪,不允许跨行)
_COMMENT_INLINE_RE = __import__("re").compile(r"%%([^%\n][^%\n]*?)%%")


def parse(text: str) -> ParsedObsidian:
    """把 Obsidian md 文本解析为结构化对象。

    解析顺序(避免冲突):
    1. 提取代码块 (内部内容**完全不解析** — 优先于其他规则)。
    2. 提取 `%%块%%` 折叠 (跨行,以 `%%\\n` 开头 `\\n%%` 结尾)。
    3. 提取 `%%xxx%%` 单行注释 (折叠块已剥离,不会重复匹配)。
    4. 提取 `> [!kind]` callout 块(以连续 `> ` 行为一块)。
    5. 提取 `[[...]]` / `![[...]]` 双链/嵌入(代码块内不计入)。
    6. 提取 `#tag` 标签(代码块内不计入)。

    返回的 `body` 是**去掉了注释和折叠块**后的纯文本;
    双链/标签/callout 保留在 body 里(原样)。
    """
    if not text:
        return ParsedObsidian(body="")

    code_block_spans: list[tuple[int, int]] = []
    # 1. 剥离代码块,记录偏移(其他正则都跳过这些偏移)
    text_wo_code = _extract_code_blocks(text, code_block_spans)

    callouts: list[Callout] = []
    # 2. 剥离 callout(只扫 code block 外的行)
    text_wo_callouts = _extract_callouts(text_wo_code, callouts, code_block_spans)

    folds: list[Fold] = []
    # 3. 剥离折叠块
    text_wo_folds = _extract_fold_blocks(text_wo_callouts, folds)

    comments: list[str] = []
    # 4. 剥离单行注释
    text_wo_comments = _extract_inline_comments(text_wo_folds, comments)

    wikilinks: list[Wikilink] = []
    embed_links: list[Wikilink] = []
    # 在**原始 text** 上跑 wikilink regex — 这样 code_block_spans 偏移才匹配
    for m in _WIKILINK_RE.finditer(text):
        start = m.start()
        if _is_in_code_block(start, code_block_spans):
            continue
        is_embed = m.group(1) == "!"
        link = Wikilink(target=m.group(2).strip(), alias=(m.group(3) or None), is_embed=is_embed)
        if is_embed:
            embed_links.append(link)
        else:
            wikilinks.append(link)

    tags_inline: list[str] = []
    # 同理 — tag regex 必须在原始 text 上跑,否则偏移和 code_block_spans 错位
    for m in _TAG_RE.finditer(text):
        start = m.start(1)
        if _is_in_code_block(start, code_block_spans):
            continue
        tags_inline.append(m.group(1))

    body = _normalize_blank_lines(text_wo_comments)

    return ParsedObsidian(
        body=body,
        wikilinks=tuple(wikilinks),
        embed_links=tuple(embed_links),
        tags_inline=tuple(tags_inline),
        callouts=tuple(callouts),
        comments=tuple(comments),
        foldable_sections=tuple(folds),
    )


# ============================================================
# 渲染
# ============================================================


def render_wikilink(target: str, alias: str | None = None) -> str:
    """生成 `[[双链]]` 文本。"""
    if alias is not None:
        return f"[[{target}|{alias}]]"
    return f"[[{target}]]"


def render_embed(target: str) -> str:
    """生成 `![[嵌入]]` 文本。"""
    return f"![[{target}]]"


def render_callout(kind: str, body: str, title: str | None = None) -> str:
    """生成 callout 文本。

    body 中**不含** `> ` 前缀(本函数会加)。
    当 body 为单行时,head 与 body 同行(更紧凑、更接近 Obsidian 实际写法)。
    """
    head = f"> [!{kind}]"
    if title is not None:
        head += f" {title}"
    if not body:
        return head
    lines = body.splitlines()
    if len(lines) == 1:
        # 单行 — head 与 body 同行
        return f"{head} {lines[0]}" if lines[0] else head
    # 多行 — head 独立,后续行加 > 前缀
    out = [head]
    for line in lines:
        out.append(f"> {line}" if line else ">")
    return "\n".join(out)


def render_subconscious(body: str) -> str:
    """生成 `%%潜意识%%` 块(单行)。

    body 内部不含 `%%` (调用方负责)。多行内容自动加换行。
    """
    return f"%%\n{body}\n%%"


# ============================================================
# 内部辅助
# ============================================================


def _extract_fold_blocks(text: str, out: list[Fold]) -> str:
    """剥离 `%%\\n...\\n%%` 折叠块,放入 out,返回剥后文本。"""
    lines = text.split("\n")
    result: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].strip() == _FOLD_BLOCK_OPEN:
            j = i + 1
            block_lines: list[str] = []
            while j < len(lines) and lines[j].strip() != _FOLD_BLOCK_OPEN:
                block_lines.append(lines[j])
                j += 1
            out.append(Fold(body="\n".join(block_lines)))
            i = j + 1
        else:
            result.append(lines[i])
            i += 1
    return "\n".join(result)


def _extract_inline_comments(text: str, out: list[str]) -> str:
    """剥离 `%%...%%` 单行注释(折叠块已剥离),放入 out,返回剥后文本。"""
    parts: list[str] = []
    cursor = 0
    for m in _COMMENT_INLINE_RE.finditer(text):
        parts.append(text[cursor : m.start()])
        out.append(m.group(1))
        cursor = m.end()
    parts.append(text[cursor:])
    return "".join(parts)


# (旧的 _extract_callouts_and_code 合并函数已拆分为 _extract_code_blocks +
# _extract_callouts — 顺序问题(code block span 在扫描中累积) 无法在单函数
# 内干净处理,拆开后 parse 顺序调对即可。)


def _extract_code_blocks(text: str, code_block_spans: list[tuple[int, int]]) -> str:
    """单独剥离代码块 — 返回去码的文本(占位空行),记录 (start, end) 偏移。

    独立抽出,避免 callout 提取时与 code block 检测相互嵌套。
    """
    lines = text.split("\n")
    out_lines: list[str] = []
    cursor = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        line_start = cursor
        cursor += len(line) + 1  # +1 for \n

        fence_m = _FENCE_RE.match(line)
        if fence_m is not None:
            fence = fence_m.group(2)
            block_start = line_start
            j = i + 1
            while j < len(lines):
                inner_line = lines[j]
                cursor += len(inner_line) + 1
                if _FENCE_RE.match(inner_line) and inner_line.lstrip().startswith(fence[:3]):
                    break
                j += 1
            code_block_spans.append((block_start, cursor))
            out_lines.append("")
            i = j + 1
            continue

        out_lines.append(line)
        i += 1

    return "\n".join(out_lines)


def _extract_callouts(
    text: str,
    callouts: list[Callout],
    code_block_spans: list[tuple[int, int]],
) -> str:
    """从已剥离 code block 的文本中提取 callout 块。

    不在 code block 偏移内的 `> [!kind]...` 才算 callout。
    """
    lines = text.split("\n")
    out_lines: list[str] = []
    cursor = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        line_start = cursor
        line_end = cursor + len(line)
        cursor = line_end + 1

        callout_m = _CALLOUT_RE.match(line)
        if callout_m is not None and not _is_in_code_block(line_start, code_block_spans):
            kind = callout_m.group(1).lower()
            head_rest = callout_m.group(2).strip()
            # head 行 `> [!kind] ...` 的 ... 部分**整体**作为 body 第一行
            body_lines: list[str] = []
            if head_rest:
                body_lines.append(head_rest)
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                nxt_end = cursor + len(nxt)
                cursor = nxt_end + 1
                if nxt.startswith("> ") or nxt == ">":
                    inner = nxt[1:] if nxt.startswith("> ") else ""
                    if _CALLOUT_RE.match(nxt):
                        break
                    body_lines.append(inner.lstrip() if inner else "")
                    j += 1
                elif nxt == "":
                    body_lines.append("")
                    j += 1
                else:
                    break
            while body_lines and body_lines[-1] == "":
                body_lines.pop()
            callouts.append(Callout(kind=kind, body="\n".join(body_lines)))
            out_lines.append("")
            i = j
            continue

        out_lines.append(line)
        i += 1

    return "\n".join(out_lines)


def _is_in_code_block(pos: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= pos < end for start, end in spans)


def _normalize_blank_lines(text: str) -> str:
    """合并连续空行为单个空行,strip 首尾空白。"""
    lines = text.split("\n")
    out: list[str] = []
    prev_blank = True
    for line in lines:
        is_blank = line.strip() == ""
        if is_blank and prev_blank:
            continue
        out.append(line)
        prev_blank = is_blank
    while out and out[-1].strip() == "":
        out.pop()
    return "\n".join(out)

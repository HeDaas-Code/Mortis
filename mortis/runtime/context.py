"""Mortis runtime context — 运行时上下文（seed + memory + tools + vault）。"""

from __future__ import annotations

from dataclasses import dataclass, field

from mortis.seed import Seed
from mortis.memory import Session, Thread
from mortis.vault import Vault
from mortis.provider import LLMProviderProtocol

from .growth_search import growth_system_prompt, search_growths


@dataclass
class RuntimeContext:
    """运行时上下文 — 所有执行体共享的依赖注入。"""
    seed: Seed
    vault: Vault
    provider: LLMProviderProtocol
    session: Session
    thread: Thread
    tools: "ToolRegistry | None" = None  # 延迟导入避免循环

    # ----- 快捷访问 -----

    @property
    def vault_root(self) -> str:
        return str(self.vault.root)

    # ----- growth 检索 (issue #20) -----

    def search_growths(
        self,
        dimension=None,
        tag: str | None = None,
        query: str | None = None,
        min_confidence: float = 0.0,
        limit: int = 10,
    ):
        """主人格检索 growth — 见 mortis.runtime.growth_search.search_growths。

        Args:
            dimension: 可选 Dimension 过滤。
            tag: 可选 frontmatter tag 精确匹配。
            query: 全文关键词(命中 body / wikilinks / tags_inline / tags)。
            min_confidence: 置信度下界(>=)。
            limit: 返回数量上限。

        Returns:
            排序后的 Growth 列表(confidence 降序, last_validated 降序)。
        """
        return search_growths(
            self.vault,
            dimension=dimension,
            tag=tag,
            query=query,
            min_confidence=min_confidence,
            limit=limit,
        )

    def growth_system_prompt(self, max_items: int = 10) -> str:
        """生成 growth 摘要 prompt — 注入到 system message 之前。

        Args:
            max_items: 注入的最大 growth 数量(默认 10)。

        Returns:
            markdown 段 — 若无 growth 则返回空字符串。
        """
        items = self.search_growths(limit=max_items)
        return growth_system_prompt(items)

    def growth_context_for_task(
        self,
        task: str,
        dimension=None,
        tag: str | None = None,
        max_items: int = 5,
    ) -> str:
        """根据任务动态检索相关 growth 上下文 (issue #59)。

        Args:
            task: 当前任务描述，用于 query 检索。
            dimension: 可选，按 dimension 过滤。
            tag: 可选，按 tag 过滤。
            max_items: 最大返回数量，默认 5。

        Returns:
            格式化后的 growth 上下文字符串，如果无相关 growth 则返回空字符串。

        issue #94: 排除 expression growth — 它们走 ``expression_patterns_prompt``
        单独注入完整 body, 避免在 growth 段被截断为 preview 行后重复出现。
        """
        if not task:
            return ""

        # 使用 task 作为 query 进行动态检索
        growths = self.search_growths(
            query=task,
            dimension=dimension,
            tag=tag,
            min_confidence=0.5,
            limit=max_items,
        )
        if not growths:
            return ""

        # issue #94: 排除 expression growth (它们走 expression_patterns_prompt 单独注入)
        from mortis.expression.distill import is_expression_growth
        growths = [g for g in growths if not is_expression_growth(g.id)]
        if not growths:
            return ""

        return growth_system_prompt(growths)

    # ----- expression patterns 注入 (issue #94 第三步) -----

    def expression_patterns_prompt(self, max_items: int = 3) -> str:
        """扫描 ``mortis-growth/tone/expression-*.md``, 注入 ``## Expression Patterns (learned)`` 段。

        issue #94 第三步: dream 的 EXPRESSION_DISTILL phase 产出 expression growth
        (id 形如 ``expression-YYYY-MM-DD``, 同天覆盖), 这里读取它们的完整 body
        注入 system prompt, 让 Mortis 回复风格随用户偏好演化。

        排序: 按 id (含日期) 降序 — 最新 dream 产出的模式在前。取最近 ``max_items`` 条。

        静默失败 — 任何异常返回空串 (expression 是增强层, 不应干扰主流程)。

        Args:
            max_items: 注入的最大条数 (默认 3, 避免无限增长)。

        Returns:
            ``## Expression Patterns (learned)\\n<body1>\\n<body2>...`` 段;
            无 expression growth 时返回空字符串 (调用方不注入)。
        """
        try:
            from mortis.expression.distill import is_expression_growth
            from mortis.growth.model import Dimension
            from mortis.growth.frontmatter import FrontmatterError

            paths = self.vault.list_growths(dimension=Dimension.TONE)
            expr_growths = []
            for rel in paths:
                try:
                    g = self.vault.read_growth(rel)
                except (FileNotFoundError, FrontmatterError):
                    continue
                if not is_expression_growth(g.id):
                    continue
                if g.body and g.body.strip():
                    expr_growths.append(g)
            if not expr_growths:
                return ""
            # 按 id (含日期) 降序 — 最新 dream 产出的模式在前
            expr_growths.sort(key=lambda g: g.id, reverse=True)
            bodies = [g.body.strip() for g in expr_growths[:max_items]]
            if not bodies:
                return ""
            return "## Expression Patterns (learned)\n" + "\n".join(bodies)
        except Exception:
            return ""

    # ----- steiner unease 注入 (issue #57) -----

    def unease_prompt_for_injection(self) -> str:
        """读 mortis-steiner/unease.json → decay → unease_prompt。

        静默失败：任何异常返回 ''（steiner 是隐藏层，不能干扰主流程）。
        不写回 decay 结果（只读不写，写由 watcher 回调负责）。

        Returns:
            注入到 system prompt 的潜台词文本。空串表示不注入。
        """
        try:
            from mortis.steiner import load_unease, decay, unease_prompt
            from datetime import datetime, timezone
            state = load_unease(self.vault)
            state = decay(state, datetime.now(tz=timezone.utc))
            return unease_prompt(state)
        except Exception:
            return ""

    # ----- LLM 消息构造 -----

    def messages_for_provider(self) -> list["Message"]:
        """构建发给 provider 的消息列表。

        重建完整对话历史 (issue #20 增量):
        - system[0]: seed tone
        - system[1] (可选): unease 潜台词 — steiner 隐藏层 (issue #57)
        - system[2] (可选): growth 摘要 — 在 tone 之后, step output 之前
        - system[3] (可选): expression patterns — dream 提炼的表达模式 (issue #94)
        - assistant: 每条 Thread step 的 output（按顺序）

        issue #57: unease 注入在 tone 之后、growth 之前（steiner 隐藏层）。
        issue #59: growth 检索现在根据当前任务动态进行。
        issue #94: expression patterns 注入在 growth 之后, step output 之前 —
            让 Mortis 回复风格随用户偏好演化。
        """
        from mortis.provider import Message
        msgs: list[Message] = [
            Message(role="system", content=self.seed.to_prompt()),
        ]
        # issue #57: 注入 unease 潜台词（steiner 隐藏层）
        unease_text = self.unease_prompt_for_injection()
        if unease_text:
            msgs.append(Message(role="system", content=unease_text))
        # issue #59: 动态检索 growth — 调用 growth_context_for_task 统一入口
        task_context = self.thread.task or ""
        growth_prompt = self.growth_context_for_task(task_context)
        if growth_prompt:
            msgs.append(Message(role="system", content=growth_prompt))
        # issue #94: 注入 expression patterns (learned) 段
        expr_prompt = self.expression_patterns_prompt()
        if expr_prompt:
            msgs.append(Message(role="system", content=expr_prompt))
        for step in self.thread.steps:
            msgs.append(Message(role="assistant", content=step.output))
        return msgs

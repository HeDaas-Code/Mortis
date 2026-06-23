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

        return growth_system_prompt(growths)

    # ----- LLM 消息构造 -----

    def messages_for_provider(self) -> list["Message"]:
        """构建发给 provider 的消息列表。

        重建完整对话历史 (issue #20 增量):
        - system[0]: seed tone
        - system[1] (可选): growth 摘要 — 在 tone 之后, step output 之前
        - assistant: 每条 Thread step 的 output（按顺序）

        issue #59: growth 检索现在根据当前任务动态进行。
        """
        from mortis.provider import Message
        msgs: list[Message] = [
            Message(role="system", content=self.seed.get_dimension("tone")),
        ]
        # issue #59: 动态检索 growth
        task_context = self.thread.task or ""
        growths = self.search_growths(query=task_context, limit=5)
        if growths:
            msgs.append(Message(role="system", content=growth_system_prompt(growths)))
        for step in self.thread.steps:
            msgs.append(Message(role="assistant", content=step.output))
        return msgs

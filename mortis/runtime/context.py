"""Mortis runtime context — 运行时上下文（seed + memory + tools + vault）。"""

from __future__ import annotations

from dataclasses import dataclass, field

from mortis.seed import Seed
from mortis.memory import Session, Thread
from mortis.vault import Vault
from mortis.provider import LLMProviderProtocol


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

    def messages_for_provider(self) -> list["Message"]:
        """构建发给 provider 的消息列表。

        重建完整对话历史：
        - system: seed tone
        - assistant: 每条 Thread step 的 output（按顺序）
        """
        from mortis.provider import Message
        msgs: list[Message] = [
            Message(role="system", content=self.seed.get_dimension("tone")),
        ]
        for step in self.thread.steps:
            msgs.append(Message(role="assistant", content=step.output))
        return msgs

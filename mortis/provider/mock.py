"""Mortis mock provider — 不调外部，返回确定性 mock。"""

from __future__ import annotations

from .base import LLMProviderProtocol, Message


class MockProvider:
    """v0 默认 provider — 不调外部，返回 deterministic mock。"""

    def generate(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> Message:
        snippet = ""
        for m in reversed(messages):
            if m.role == "user":
                text = m.content.strip()
                lines = text.splitlines()
                snippet = lines[0][:30] if lines else "empty"
                break
        return Message(role="assistant", content=f"[mock:{snippet}]")

    def generate_text(
        self,
        prompt: str,
        system: str = "",
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        snippet = prompt.strip().splitlines()[0][:30] if prompt.strip() else "empty"
        return f"[mock:{snippet}]"

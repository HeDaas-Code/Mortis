"""Mortis mock provider — 不调外部，返回确定性 mock。"""

from __future__ import annotations

from .base import LLMProviderProtocol, Message


class MockProvider:
    """v0 默认 provider — 不调外部，返回 deterministic mock。

    可选传入 responses 列表实现多轮对话模拟：
    - 不传：返回 [mock:<user 首行>]
    - 传 responses：按调用顺序依次返回，超出后循环
    """

    def __init__(self, responses: list[str] | None = None) -> None:
        self._responses = responses
        self._call_count = 0

    def generate(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> Message:
        if self._responses:
            idx = self._call_count % len(self._responses)
            self._call_count += 1
            return Message(role="assistant", content=self._responses[idx])

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
        if self._responses:
            idx = self._call_count % len(self._responses)
            self._call_count += 1
            return self._responses[idx]

        snippet = prompt.strip().splitlines()[0][:30] if prompt.strip() else "empty"
        return f"[mock:{snippet}]"

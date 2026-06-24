"""Mortis mock provider — 不调外部，返回确定性 mock。"""

from __future__ import annotations

import logging
import time

from .audit import messages_hash, sha256_prefix
from .base import Message

_logger = logging.getLogger(__name__)


class MockProvider:
    """v0 默认 provider — 不调外部，返回 deterministic mock。

    可选传入 responses 列表实现多轮对话模拟：
    - 不传：返回 [mock:<user 首行>]
    - 传 responses：按调用顺序依次返回，超出后循环

    issue #87: generate / generate_text 均产出审计 log (DEBUG),
    含 prompt/response 的 SHA256 前 16 位 + 耗时, **不记原文** —
    与 MinimaxProvider 保持一致, 便于本地/CI 也能验证审计链路。
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
        # issue #87: 审计 hash (前 16 位), 不记 prompt 原文
        prompt_hash = messages_hash(messages)
        start = time.monotonic()
        if self._responses:
            idx = self._call_count % len(self._responses)
            self._call_count += 1
            message = Message(role="assistant", content=self._responses[idx])
        else:
            snippet = ""
            for m in reversed(messages):
                if m.role == "user":
                    text = m.content.strip()
                    lines = text.splitlines()
                    snippet = lines[0][:30] if lines else "empty"
                    break
            message = Message(role="assistant", content=f"[mock:{snippet}]")
        # issue #87: 审计 log — 含 prompt/response hash + 耗时, 不含原文
        _logger.debug(
            "[provider] method=generate prompt_hash=%s resp_hash=%s elapsed=%.3fs",
            prompt_hash,
            sha256_prefix(message.content),
            time.monotonic() - start,
        )
        return message

    def generate_text(
        self,
        prompt: str,
        system: str = "",
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        # issue #87: 审计 hash (前 16 位), 不记 prompt 原文
        prompt_hash = sha256_prefix(prompt)
        start = time.monotonic()
        if self._responses:
            idx = self._call_count % len(self._responses)
            self._call_count += 1
            content = self._responses[idx]
        else:
            snippet = prompt.strip().splitlines()[0][:30] if prompt.strip() else "empty"
            content = f"[mock:{snippet}]"
        # issue #87: 审计 log — 含 prompt/response hash + 耗时, 不含原文
        _logger.debug(
            "[provider] method=generate_text prompt_hash=%s resp_hash=%s elapsed=%.3fs",
            prompt_hash,
            sha256_prefix(content),
            time.monotonic() - start,
        )
        return content

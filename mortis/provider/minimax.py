"""Mortis minimax API provider。"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any

from .audit import messages_hash, sha256_prefix
from .base import Message

_logger = logging.getLogger(__name__)

MINIMAX_DEFAULT_BASE_URL = "https://api.minimax.chat/v1"
MINIMAX_DEFAULT_MODEL = "MiniMax-M3"


class MinimaxAuthError(RuntimeError):
    """minimax API 鉴权失败（401/403）。"""


class MinimaxAPIError(RuntimeError):
    """minimax API 调用失败（其他 4xx/5xx/网络错误）。"""


class MinimaxProvider:
    """minimax API provider。

    接口契约与 MockProvider 一致（generate(messages) -> Message），
    便于 Mortis 主人格无缝切换。
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = MINIMAX_DEFAULT_BASE_URL,
        model: str = MINIMAX_DEFAULT_MODEL,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key or os.environ.get("MINIMAX_API_KEY", "")
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def _messages_to_openai_format(
        self, messages: list[Message]
    ) -> list[dict[str, str]]:
        result = []
        for m in messages:
            if m.role == "tool":
                result.append({
                    "role": "tool",
                    "content": m.content,
                    "tool_call_id": m.tool_call_id,
                })
            elif m.name:
                result.append({
                    "role": m.role,
                    "content": m.content,
                    "name": m.name,
                })
            else:
                result.append({"role": m.role, "content": m.content})
        return result

    def generate(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> Message:
        if not self._api_key:
            raise MinimaxAuthError(
                "MINIMAX_API_KEY not set — export it before using MinimaxProvider"
            )
        # issue #87: 审计 hash (前 16 位), 不记 prompt 原文
        prompt_hash = messages_hash(messages)
        body = self._build_body(messages, temperature, max_tokens)
        req = urllib.request.Request(
            url=f"{self._base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )
        start = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            elapsed = time.monotonic() - start
            _logger.debug(
                "[provider] method=generate prompt_hash=%s resp_hash= "
                "elapsed=%.3fs status=http_error_%d",
                prompt_hash,
                elapsed,
                e.code,
            )
            if e.code in (401, 403):
                raise MinimaxAuthError(f"minimax auth failed: HTTP {e.code}") from e
            raise MinimaxAPIError(f"minimax API HTTP {e.code}") from e
        except urllib.error.URLError as e:
            elapsed = time.monotonic() - start
            _logger.debug(
                "[provider] method=generate prompt_hash=%s resp_hash= "
                "elapsed=%.3fs status=url_error",
                prompt_hash,
                elapsed,
            )
            raise MinimaxAPIError(f"minimax API network error: {e}") from e
        message = self._extract_message(payload)
        # issue #87: 成功路径审计 log — 含 prompt/response hash + 耗时, 不含原文
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
        messages = []
        if system:
            messages.append(Message(role="system", content=system))
        messages.append(Message(role="user", content=prompt))
        content = self.generate(
            messages, temperature=temperature, max_tokens=max_tokens
        ).content
        # issue #87: 成功路径审计 log — 含 prompt/response hash + 耗时, 不含原文
        _logger.debug(
            "[provider] method=generate_text prompt_hash=%s resp_hash=%s elapsed=%.3fs",
            prompt_hash,
            sha256_prefix(content),
            time.monotonic() - start,
        )
        return content

    # ---- 异步接口 (issue #46) ----
    # 用 asyncio.to_thread() 把同步 HTTP 调用移到独立线程,
    # 避免阻塞事件循环, 让 daemon 模式可并发触发多个认知周期。

    async def async_generate(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> Message:
        """异步 generate — 用 asyncio.to_thread 包装同步 HTTP 调用 (issue #46)。"""
        return await asyncio.to_thread(
            self.generate, messages, temperature=temperature, max_tokens=max_tokens
        )

    async def async_generate_text(
        self,
        prompt: str,
        system: str = "",
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        """异步 generate_text — 用 asyncio.to_thread 包装同步 HTTP 调用 (issue #46)。"""
        return await asyncio.to_thread(
            self.generate_text,
            prompt,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def _build_body(
        self,
        messages: list[Message],
        temperature: float,
        max_tokens: int | None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self._model,
            "messages": self._messages_to_openai_format(messages),
            "temperature": temperature,
        }
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        return body

    def _extract_message(self, payload: dict[str, Any]) -> Message:
        try:
            choice = payload["choices"][0]["message"]
            return Message(
                role=choice.get("role", "assistant"),
                content=choice.get("content", ""),
            )
        except (KeyError, IndexError, TypeError) as e:
            raise MinimaxAPIError(f"unexpected minimax response shape: {e}") from e

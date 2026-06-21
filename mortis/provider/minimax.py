"""Mortis minimax API provider。"""

from __future__ import annotations

import json
import os
from typing import Any

import urllib.error
import urllib.request

from .base import LLMProviderProtocol, Message

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
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise MinimaxAuthError(f"minimax auth failed: HTTP {e.code}") from e
            raise MinimaxAPIError(f"minimax API HTTP {e.code}") from e
        except urllib.error.URLError as e:
            raise MinimaxAPIError(f"minimax API network error: {e}") from e
        return self._extract_message(payload)

    def generate_text(
        self,
        prompt: str,
        system: str = "",
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        messages = []
        if system:
            messages.append(Message(role="system", content=system))
        messages.append(Message(role="user", content=prompt))
        return self.generate(messages, temperature=temperature, max_tokens=max_tokens).content

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

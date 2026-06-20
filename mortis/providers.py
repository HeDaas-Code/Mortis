"""Mortis v1-issue-2: minimax API provider。

Mortis 默认 LLM provider —— 通过 minimax API 调用真实模型。
v1-issue-2 把 v0 的 MockProvider 替换掉。

配置:
    minimax_api_key  从环境变量 MINIMAX_API_KEY 读取(不写进文件/log)
    base_url         默认 https://api.minimax.chat/v1
    model            默认 MiniMax-M3
"""

from __future__ import annotations

import os
from typing import Any

import urllib.error
import urllib.request
import json


MINIMAX_DEFAULT_BASE_URL = "https://api.minimax.chat/v1"
MINIMAX_DEFAULT_MODEL = "MiniMax-M3"


class MinimaxAuthError(RuntimeError):
    """minimax API 鉴权失败(401/403)。"""


class MinimaxAPIError(RuntimeError):
    """minimax API 调用失败(其他 4xx/5xx/网络错误)。"""


class MinimaxProvider:
    """minimax API provider — v1-issue-2 真实 LLM 接入。

    接口契约与 MockProvider 一致(generate(prompt, system="") -> str),
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

    def generate(self, prompt: str, system: str = "") -> str:
        if not self._api_key:
            raise MinimaxAuthError(
                "MINIMAX_API_KEY not set — export it before using MinimaxProvider"
            )
        body = self._build_body(prompt, system)
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
        return self._extract_content(payload)

    def _build_body(self, prompt: str, system: str) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return {
            "model": self._model,
            "messages": messages,
        }

    def _extract_content(self, payload: dict[str, Any]) -> str:
        try:
            return str(payload["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as e:
            raise MinimaxAPIError(f"unexpected minimax response shape: {e}") from e


def make_provider(kind: str = "auto") -> Any:
    """工厂函数 — 根据 kind 返回合适的 provider。

    Args:
        kind: "auto" = 有 MINIMAX_API_KEY 就用 MinimaxProvider,否则 MockProvider
              "minimax" = 强制 MinimaxProvider(无 key 报错)
              "mock" = 强制 MockProvider
    """
    from .persona import MockProvider  # 局部 import 避免循环

    if kind == "mock":
        return MockProvider()
    if kind == "minimax":
        return MinimaxProvider()
    if kind == "auto":
        if os.environ.get("MINIMAX_API_KEY"):
            return MinimaxProvider()
        return MockProvider()
    raise ValueError(f"unknown provider kind: {kind!r}")
"""Mortis minimax API provider。"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any, Generator

import re

from .audit import messages_hash, sha256_prefix
from .base import Message, StreamChunk

_logger = logging.getLogger(__name__)

MINIMAX_DEFAULT_BASE_URL = "https://api.minimax.chat/v1"
MINIMAX_DEFAULT_MODEL = "MiniMax-M3"

# MiniMax-M3 会输出 <think>...</think> 推理过程, 需要从最终输出中剥离
_THINK_PATTERN = re.compile(r"<think>.*?</think>", re.DOTALL)


def strip_think_tags(text: str) -> str:
    """剥离 MiniMax-M3 的 <think>...</think> 推理过程标签。

    think 块是模型的内部推理, 不应展示给用户。
    剥离后清理多余空白, 保持输出干净。
    """
    cleaned = _THINK_PATTERN.sub("", text)
    # 清理剥离后可能残留的首尾空白
    return cleaned.strip() if cleaned != text else text


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
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "tool":
                result.append({
                    "role": "tool",
                    "content": m.content,
                    "tool_call_id": m.tool_call_id,
                })
            elif m.tool_calls:
                # issue #93: assistant 消息携带 tool_calls (function calling 多轮)
                # OpenAI 要求把 tool_calls 原样回传, 否则 tool 结果消息会被拒收。
                # 注意: 内部存储时 arguments 已 parse 为 dict, 回传 API 时需转回 JSON 字符串。
                serializable_calls: list[dict[str, Any]] = []
                for tc in m.tool_calls:
                    tc_copy: dict[str, Any] = dict(tc)
                    func = dict(tc_copy.get("function", {}) or {})
                    args = func.get("arguments")
                    if isinstance(args, dict):
                        func["arguments"] = json.dumps(args, ensure_ascii=False)
                    tc_copy["function"] = func
                    serializable_calls.append(tc_copy)
                entry: dict[str, Any] = {
                    "role": m.role,
                    "tool_calls": serializable_calls,
                }
                if m.content:
                    entry["content"] = m.content
                result.append(entry)
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
        tools: list[dict] | None = None,
    ) -> Message:
        if not self._api_key:
            raise MinimaxAuthError(
                "MINIMAX_API_KEY not set — export it before using MinimaxProvider"
            )
        # issue #87: 审计 hash (前 16 位), 不记 prompt 原文
        prompt_hash = messages_hash(messages)
        body = self._build_body(messages, temperature, max_tokens, tools)
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
        # 剥离 <think> 推理标签 (issue #89)
        cleaned_content = strip_think_tags(message.content)
        # issue #93: 解析响应里的 tool_calls (OpenAI function calling 格式)
        tool_calls = self._extract_tool_calls(payload)
        message = Message(
            role=message.role,
            content=cleaned_content,
            tool_calls=tool_calls,
        )
        # issue #87: 成功路径审计 log — 含 prompt/response hash + 耗时, 不含原文
        _logger.debug(
            "[provider] method=generate prompt_hash=%s resp_hash=%s elapsed=%.3fs"
            " tool_calls=%d",
            prompt_hash,
            sha256_prefix(message.content),
            time.monotonic() - start,
            len(tool_calls) if tool_calls else 0,
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
        # generate() 已剥离 <think> 标签, 这里直接用
        # issue #87: 成功路径审计 log — 含 prompt/response hash + 耗时, 不含原文
        _logger.debug(
            "[provider] method=generate_text prompt_hash=%s resp_hash=%s elapsed=%.3fs",
            prompt_hash,
            sha256_prefix(content),
            time.monotonic() - start,
        )
        return content

    # ---- 流式接口 ----

    def generate_stream(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> Generator[StreamChunk, None, None]:
        """流式 generate — 通过 SSE 逐块返回增量文本。

        使用 HTTP chunked transfer + Server-Sent Events 格式,
        每收到一个 ``data: {...}`` 块就解析出 delta 并 yield。

        适用于长文本生成场景, 避免单次调用耗时过长。
        """
        if not self._api_key:
            raise MinimaxAuthError(
                "MINIMAX_API_KEY not set — export it before using MinimaxProvider"
            )
        body = self._build_body(messages, temperature, max_tokens)
        body["stream"] = True
        req = urllib.request.Request(
            url=f"{self._base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
                "Accept": "text/event-stream",
            },
            method="POST",
        )
        try:
            resp = urllib.request.urlopen(req, timeout=self._timeout)
            # 流式 think 标签过滤状态机 (issue #89)
            # MiniMax-M3 流式输出可能包含 <think>...</think>, 需要跨块过滤
            in_think = False
            buffer = ""
            for line in resp:
                line = line.decode("utf-8").strip()
                if not line or not line.startswith("data:"):
                    continue
                data_str = line[len("data:"):].strip()
                if data_str == "[DONE]":
                    yield StreamChunk(delta="", finish_reason="stop")
                    return
                try:
                    chunk = json.loads(data_str)
                    choice = chunk.get("choices", [{}])[0]
                    delta = choice.get("delta", {}).get("content", "")
                    finish = choice.get("finish_reason")
                    if not delta and not finish:
                        continue

                    # think 标签过滤: 逐块处理, 维护 in_think 状态
                    if delta:
                        buffer += delta
                        output = ""
                        while buffer:
                            if in_think:
                                # 在 think 块内, 寻找 </think>
                                idx = buffer.find("</think>")
                                if idx != -1:
                                    # 找到闭合标签, 跳过 think 内容
                                    buffer = buffer[idx + len("</think>"):]
                                    in_think = False
                                    # 跳过闭合后的换行
                                    if buffer.startswith("\n"):
                                        buffer = buffer[1:]
                                else:
                                    # think 块还没闭合, 全部留在 buffer 里
                                    buffer = ""
                                    break
                            else:
                                # 在 think 块外, 寻找 <think>
                                idx = buffer.find("<think>")
                                if idx != -1:
                                    # 输出 <think> 之前的内容
                                    output += buffer[:idx]
                                    buffer = buffer[idx + len("<think>"):]
                                    in_think = True
                                    # 跳过 <think> 后的换行
                                    if buffer.startswith("\n"):
                                        buffer = buffer[1:]
                                else:
                                    # 检查 buffer 末尾是否有不完整的 <think 标签
                                    # 避免把 "<t" 当普通文本输出
                                    partial = ""
                                    for i in range(min(len(buffer), 6), 0, -1):
                                        if "<think>"[:i] == buffer[-i:]:
                                            partial = buffer[-i:]
                                            break
                                    if partial:
                                        output += buffer[:-len(partial)]
                                        buffer = partial
                                    else:
                                        output += buffer
                                        buffer = ""
                                    break
                        if output:
                            yield StreamChunk(delta=output, finish_reason=None)
                    if finish:
                        # 流结束时, 如果 buffer 里还有内容 (think 块未闭合), 丢弃
                        yield StreamChunk(delta="", finish_reason=finish)
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
            resp.close()
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise MinimaxAuthError(f"minimax auth failed: HTTP {e.code}") from e
            raise MinimaxAPIError(f"minimax API HTTP {e.code}") from e
        except urllib.error.URLError as e:
            raise MinimaxAPIError(f"minimax API network error: {e}") from e

    # ---- 异步接口 (issue #46) ----
    # 用 asyncio.to_thread() 把同步 HTTP 调用移到独立线程,
    # 避免阻塞事件循环, 让 daemon 模式可并发触发多个认知周期。

    async def async_generate(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        tools: list[dict] | None = None,
    ) -> Message:
        """异步 generate — 用 asyncio.to_thread 包装同步 HTTP 调用 (issue #46)。

        issue #93: 透传 tools 参数 (function calling) 到同步 generate。
        """
        return await asyncio.to_thread(
            self.generate, messages,
            temperature=temperature, max_tokens=max_tokens, tools=tools,
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
        tools: list[dict] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self._model,
            "messages": self._messages_to_openai_format(messages),
            "temperature": temperature,
        }
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        # issue #93: 透传 tools (OpenAI function calling schema) — 让 LLM 知道有哪些工具可用
        if tools:
            body["tools"] = tools
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

    def _extract_tool_calls(self, payload: dict[str, Any]) -> list[dict] | None:
        """从 OpenAI 兼容响应里解析 tool_calls (issue #93)。

        响应格式 (OpenAI / MiniMax-M3 兼容)::

            {"choices": [{"message": {"role": "assistant", "content": "",
              "tool_calls": [{"id": "call_xxx", "type": "function",
                "function": {"name": "vault:read", "arguments": "{\\"path\\": \\"x\\"}"}}]}}]}

        Args:
            payload: 完整 API 响应 dict。

        Returns:
            list[dict] — 每个 dict 含 id/type/function{name,arguments(arguments 已 parse 为 dict)}。
            无 tool_calls 或解析失败时返回 None。
        """
        try:
            choice = payload["choices"][0]
            raw_calls = choice.get("message", {}).get("tool_calls") or choice.get("tool_calls")
            if not raw_calls:
                return None
            parsed: list[dict] = []
            for tc in raw_calls:
                if not isinstance(tc, dict):
                    continue
                func = tc.get("function", {}) or {}
                args_raw = func.get("arguments", "")
                # arguments 是 JSON 字符串, parse 成 dict; parse 失败保留原字符串
                try:
                    args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                except (json.JSONDecodeError, TypeError):
                    args = {"_raw": args_raw}
                parsed.append({
                    "id": tc.get("id", ""),
                    "type": tc.get("type", "function"),
                    "function": {
                        "name": func.get("name", ""),
                        "arguments": args,
                    },
                })
            return parsed if parsed else None
        except (KeyError, IndexError, TypeError) as e:
            _logger.debug("extract tool_calls: no tool_calls in response (%s)", e)
            return None

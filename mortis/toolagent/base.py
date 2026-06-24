"""Mortis toolagent base — 无人格工具执行体抽象。

issue #25: 把 ``mortis.tools`` 中的 ``ToolProtocol`` 包装成可被 ToolRegistry
注册的 ``ToolAgent``。ToolAgent 是**无人格**的 — 不走 seed / identity / 人格 prompt,
不写 vault, 不读 seed。设计上可以调 LLM 做工具性任务 (摘要/分类/语义搜索),
但 LLM 调用不带人格上下文。

issue #63: 基类已加 provider 字段 (LLMProviderProtocol), 子类可注入。
5 个内置 agent 全部支持 LLM 能力。

设计要点:
- ``ToolResult`` (本模块) 与 ``mortis.tools.ToolResult`` 是两个独立 dataclass,
  字段不冲突 — 前者面向 agent 层 (success/data/error),后者面向 tool 层
  (name/content/error)。ToolAgent 在两者之间翻译。
- ``ToolAgent.from_tool(...)`` 工厂把任何 ``ToolProtocol`` 包成 ``ToolAgent``,
  agent_id 默认为 ``tool.name`` (例如 ``"vault:read"``)。
- ``ToolAgent.execute(input: dict)`` 把 dict 当作 ``**kwargs`` 透传给
  ``tool.execute``。tool 抛任何异常 → 返回 ``ToolResult(success=False, error=str(e))``。
- ``ToolAgentProtocol`` 让上层 (registry) 可以鸭子类型地接受任意 agent 实现,
  不必依赖具体类 (VaultReadAgent / MarkdownRenderAgent 等)。

issue #72: 已删除 task 字符串关键词路由 (TaskRouter)。
路由决策改为 LLM 通过 ToolRegistry tool calling 自发决定 — 见 issue #64。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from mortis.provider.audit import sha256_prefix
from mortis.provider.base import LLMProviderProtocol
from mortis.tools.base import ToolProtocol
from mortis.tools.base import ToolResult as ToolLayerResult

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolResult:
    """ToolAgent 执行结果。

    与 ``mortis.tools.ToolResult`` 不同 — 本 dataclass 面向 agent 层:
    - ``success``: True = 成功, False = 失败
    - ``data``: 成功时的载荷 (任意类型 — vault entry / parsed obsidian / stats dict ...)
    - ``error``: 失败时的错误描述;成功时为 None
    """

    success: bool
    data: Any
    error: str | None = None


class ToolAgentProtocol(Protocol):
    """ToolAgent 协议 — 任何实现 ``agent_id`` + ``execute`` 的类都是 ToolAgent。

    与 ``ToolProtocol`` 的区别:
    - ``ToolProtocol`` 描述**工具** (LLM 可见的 JSON schema,面向 schema 的协议)
    - ``ToolAgentProtocol`` 描述**执行体** (接收 dict 输入,返回 ToolResult;
      不暴露 schema — 调用方已知道这个 agent 是做什么的)

    协议层而非继承 — 任何类只要满足 duck typing 就算 ToolAgent。
    """

    agent_id: str

    def execute(self, input: dict) -> ToolResult:
        """执行 agent。``input`` 是 dict,具体 schema 取决于 agent 实现。"""
        ...


class ToolAgent:
    """把 ``ToolProtocol`` 包成 ``ToolAgent`` 的薄包装。

    适用场景:
    - vault:read / vault:list / vault:write / vault:exists 等现有 tool 已有
      ``ToolProtocol`` 实现,但 router 想用 ToolAgent 接口调度。
    - 第三方 tool (ToolProtocol) 想接入 agent 层而无须改源码。

    字段:
    - ``agent_id``: 唯一标识,默认 = ``tool.name`` (e.g. ``"vault:read"``)。
    - ``tool``: 底层 ``ToolProtocol`` 实例。
    - ``provider``: LLM provider (issue #63),可为 None (纯工具操作)。
    - ``timeout``: 预留超时参数 (秒)。当前实现不强制 — 留给 #26 接入。
    """

    agent_id: str
    tool: ToolProtocol
    provider: LLMProviderProtocol | None
    timeout: int = 30

    def __init__(
        self,
        tool: ToolProtocol,
        agent_id: str | None = None,
        provider: LLMProviderProtocol | None = None,
        timeout: int = 30,
    ) -> None:
        self.tool = tool
        self.agent_id = agent_id if agent_id is not None else tool.name
        self.provider = provider
        self.timeout = timeout

    @classmethod
    def from_tool(
        cls,
        tool: ToolProtocol,
        agent_id: str | None = None,
        provider: LLMProviderProtocol | None = None,
        timeout: int = 30,
    ) -> "ToolAgent":
        """工厂方法 — 包任意 ``ToolProtocol`` 为 ``ToolAgent``。

        与 ``__init__`` 等价,只是显式表达"包装"语义,方便 router 代码阅读。
        """
        return cls(tool=tool, agent_id=agent_id, provider=provider, timeout=timeout)

    def _llm_generate(
        self,
        prompt: str,
        system: str = "",
        *,
        redact: bool = False,
        **kwargs,
    ) -> str | None:
        """调用 LLM 生成文本 (issue #63)。

        若无 provider,返回 None。

        Args:
            prompt: 用户 prompt。
            system: 可选系统提示词。
            redact: issue #87 — 标记 prompt 是否已由调用方脱敏 (默认 False)。
                **本方法不执行脱敏**, 仅在审计 log 中记录该状态, 便于事后排查
                是否有未脱敏的私密内容被发给外部 LLM。调用方 (如 VaultSearchAgent)
                应在调用前自行 redact (HARNESS.md '数据不外流')。
            **kwargs: 透传给 provider.generate_text() 的额外参数。

        Returns:
            LLM 生成的文本,或 None (无 provider 或降级失败)。

        审计日志 (issue #87):
            - 成功: DEBUG log 含 prompt 的 SHA256 前 16 位 + redact 标记
              (不记 prompt 原文, 可事后追溯)
            - 失败: WARNING log 在原 prompt_len 基础上追加 prompt_hash + redact

        失败处理 (issue #70 MEDIUM-E):
            - ``TimeoutError``: 网络/算力超时, 降级返回 None + log warning
            - 其他 ``Exception``: provider 异常 (rate limit / auth fail / invalid response),
              降级返回 None + log warning (含异常类型 + 消息)
            - 任意路径均 **不再静默** — 调用方可据 None 判断失败并自行降级
            - 未来如需重试或抛错,在此扩展即可 — 保持接口契约不变
        """
        if self.provider is None:
            return None
        # issue #87: 计算 prompt hash (前 16 位), 用于审计追溯 — 不记原文
        prompt_hash = sha256_prefix(prompt)
        try:
            result = self.provider.generate_text(prompt, system=system, **kwargs)
        except TimeoutError as e:
            _logger.warning(
                "LLM generate timed out (provider=%s, prompt_len=%d, "
                "prompt_hash=%s, redact=%s): %s",
                type(self.provider).__name__,
                len(prompt),
                prompt_hash,
                redact,
                e,
            )
            return None
        except Exception as e:  # noqa: BLE001 — 降级路径, 错误已 log
            _logger.warning(
                "LLM generate failed (provider=%s, prompt_len=%d, "
                "prompt_hash=%s, redact=%s, exc=%s): %s",
                type(self.provider).__name__,
                len(prompt),
                prompt_hash,
                redact,
                type(e).__name__,
                e,
            )
            return None
        # issue #87: 成功路径审计 log — 含 hash + redact 标记, 不含原文
        _logger.debug(
            "[provider] method=_llm_generate prompt_hash=%s redact=%s prompt_len=%d",
            prompt_hash,
            redact,
            len(prompt),
        )
        return result

    def execute(self, input: dict) -> ToolResult:
        """把 ``input`` dict 透传给 ``tool.execute(**input)``,翻译结果。

        行为:
        - 底层抛**任何**异常 → ``ToolResult(success=False, data=None, error=str(e))``
        - 底层 ``ToolResult.success == True`` → ``ToolResult(success=True, data=result.content)``
        - 底层 ``ToolResult.success == False`` → ``ToolResult(success=False, data=None, error=result.error)``
        """
        try:
            layer_result: ToolLayerResult = self.tool.execute(**input)
        except Exception as e:  # noqa: BLE001 — 包所有异常统一翻译
            return ToolResult(success=False, data=None, error=str(e))
        if layer_result.success:
            return ToolResult(success=True, data=layer_result.content, error=None)
        return ToolResult(
            success=False,
            data=None,
            error=layer_result.error or "tool reported failure without error message",
        )

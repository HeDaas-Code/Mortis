"""Mortis pipeline step — 步骤基类与具体步骤实现。"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from mortis.provider import LLMProviderProtocol, Message, ToolCall
from mortis.tools.base import ToolResult
from mortis.runtime import RuntimeContext, SubRuntime, SubTemplate
from mortis.tools import ToolRegistry, ToolResult as TRes


# ----- 步骤结果 -----

@dataclass
class StepOutput:
    """步骤输出。"""
    step_id: str
    step_type: str
    message: str  # 步骤的文本输出（给主人格/owner 看）
    tool_results: list[dict] = field(default_factory=list)  # 工具调用记录
    next_action: str = "done"  # done | continue | delegate


# ----- 工具调用解析 -----

def parse_tool_calls_from_text(text: str) -> list[ToolCall]:
    """从文本回复中解析 [TOOL: name {...}] 格式的工具调用（TextCall 降级）。"""
    pattern = r"\[TOOL:\s*(\w+):(\w+)\s*(\{.*?\})?\]"
    matches = re.findall(pattern, text, re.DOTALL)
    calls = []
    for ns, action, args_str in matches:
        name = f"{ns}:{action}"
        args: dict[str, Any] = {}
        if args_str:
            try:
                args = json.loads(args_str)
            except json.JSONDecodeError:
                pass
        calls.append(ToolCall(
            id=f"tc-{len(calls)}",
            name=name,
            arguments=args,
        ))
    return calls


# ----- 步骤基类 -----

class Step(ABC):
    """步骤基类。步骤可以内部循环（Option B：可嵌套 LLM 调用）。"""

    def __init__(
        self,
        step_id: str,
        ctx: RuntimeContext,
        max_iterations: int = 3,
    ) -> None:
        self.step_id = step_id
        self.ctx = ctx
        self.max_iterations = max_iterations
        self._iteration = 0

    @property
    @abstractmethod
    def step_type(self) -> str:
        """步骤类型标识。"""
        ...

    def run(self) -> StepOutput:
        """执行步骤。子类可 override 实现自己的循环逻辑。"""
        raise NotImplementedError

    def _increment(self) -> bool:
        """递增迭代计数器，返回是否还有迭代空间。"""
        self._iteration += 1
        return self._iteration < self.max_iterations

    def _call_provider(
        self,
        messages: list[Message],
        tools: ToolRegistry | None = None,
    ) -> tuple[Message, list[ToolResult]]:
        """调用 provider，返回 (回复消息, 工具结果)。"""
        resp = self.ctx.provider.generate(messages)
        tool_results: list[ToolResult] = []

        # 优先：从响应中提取 function_call（原生 function calling）
        tool_calls = self._extract_function_calls(resp)
        if not tool_calls:
            # 降级：TextCall 解析
            tool_calls = parse_tool_calls_from_text(resp.content)

        if tool_calls and tools:
            for tc in tool_calls:
                tr = tools.execute(tc.name, tc.arguments)
                tool_results.append({
                    "id": tc.id,
                    "name": tc.name,
                    "arguments": tc.arguments,
                    "result": tr.content,
                    "is_error": tr.error or False,
                })
                # 把工具结果加回消息历史
                messages.append(Message(
                    role="tool",
                    content=tr.content,
                    tool_call_id=tc.id,
                ))
            # 再次调用 provider（看工具结果后再回复）
            resp = self.ctx.provider.generate(messages)

        return resp, tool_results

    def _extract_function_calls(self, msg: Message) -> list[ToolCall]:
        """从 provider 响应中提取 function_call（OpenAI 格式）。

        默认返回空列表（走 TextCall 降级）。
        子类可 override 此方法以支持原生 function calling。
        """
        # MinimaxProvider 等支持 function calling 的 provider
        # 可在子类中 override 此方法解析 choice.message.tool_calls
        return []


# ----- 步骤类型实现 -----

class ThinkStep(Step):
    """Think 步骤 — 主人格分析任务，决定行动方向。"""

    MAX_ITERATIONS = 2

    def __init__(self, step_id: str, ctx: RuntimeContext) -> None:
        super().__init__(step_id, ctx, max_iterations=self.MAX_ITERATIONS)

    @property
    def step_type(self) -> str:
        return "think"

    def run(self) -> StepOutput:
        messages = self.ctx.messages_for_provider()
        messages.append(Message(
            role="user",
            content=(
                f"分析这个任务：{self.ctx.thread.task}\n\n"
                "思考以下问题：\n"
                "1. 这个任务需要查 vault 吗？\n"
                "2. 这个任务简单到可以直接完成，还是需要拆解？\n"
                "3. 需要派 sub 吗？\n"
                "请给出简短的分析和行动建议。"
            ),
        ))
        resp, _ = self._call_provider(messages)
        return StepOutput(
            step_id=self.step_id,
            step_type=self.step_type,
            message=resp.content,
            next_action="continue",
        )


class PlanStep(Step):
    """Plan 步骤 — 将任务拆解为有序步骤。"""

    MAX_ITERATIONS = 2

    def __init__(self, step_id: str, ctx: RuntimeContext) -> None:
        super().__init__(step_id, ctx, max_iterations=self.MAX_ITERATIONS)

    @property
    def step_type(self) -> str:
        return "plan"

    def run(self) -> StepOutput:
        messages = self.ctx.messages_for_provider()
        messages.append(Message(
            role="user",
            content=(
                f"将以下任务拆解为具体的执行步骤：\n{self.ctx.thread.task}\n\n"
                "要求：\n"
                "- 每个步骤有清晰的输入和输出\n"
                "- 步骤数量不超过 5 个\n"
                "- 用编号列表格式输出"
            ),
        ))
        resp, _ = self._call_provider(messages)
        return StepOutput(
            step_id=self.step_id,
            step_type=self.step_type,
            message=resp.content,
            next_action="continue",
        )


class ActStep(Step):
    """Act 步骤 — 执行具体任务（可工具调用，可循环）。"""

    MAX_ITERATIONS = 5

    def __init__(self, step_id: str, ctx: RuntimeContext, tools: ToolRegistry | None = None) -> None:
        super().__init__(step_id, ctx, max_iterations=self.MAX_ITERATIONS)
        self.tools = tools or self.ctx.tools

    @property
    def step_type(self) -> str:
        return "act"

    def run(self) -> StepOutput:
        messages = self.ctx.messages_for_provider()
        messages.append(Message(
            role="user",
            content=f"执行任务：{self.ctx.thread.task}",
        ))

        all_tool_results: list[dict] = []
        while self._iteration < self.max_iterations:
            resp, tool_results = self._call_provider(messages, self.tools)
            all_tool_results.extend(tool_results)
            messages.append(resp)

            # 检查是否还有工具调用
            if not tool_results:
                break

            if not self._increment():
                break

        final_msg = messages[-1].content
        return StepOutput(
            step_id=self.step_id,
            step_type=self.step_type,
            message=final_msg,
            tool_results=all_tool_results,
            next_action="done",
        )


class ReviewStep(Step):
    """Review 步骤 — 主人格审阅产出，决定是否接受。"""

    MAX_ITERATIONS = 2

    def __init__(self, step_id: str, ctx: RuntimeContext) -> None:
        super().__init__(step_id, ctx, max_iterations=self.MAX_ITERATIONS)

    @property
    def step_type(self) -> str:
        return "review"

    def run(self) -> StepOutput:
        # 从 thread 的最后一步获取内容
        if not self.ctx.thread.steps:
            message = "(no prior steps to review)"
        else:
            last = self.ctx.thread.steps[-1]
            message = last.output

        messages = self.ctx.messages_for_provider()
        messages.append(Message(
            role="user",
            content=(
                f"审阅以下产出：\n\n{message}\n\n"
                "评估：\n"
                "1. 产出是否解决了原始任务？\n"
                "2. 是否有 OOC 风险？\n"
                "3. 采纳/丢弃/需要修改？\n"
                "简短回复你的决定。"
            ),
        ))
        resp, _ = self._call_provider(messages)
        decision = resp.content
        # 简单判断：含 adopt/yes/ok → done，含 discard/no → 需要修改
        if any(k in decision.lower() for k in ("adopt", "采纳", "ok", "yes", "done")):
            next_action = "done"
        else:
            next_action = "continue"
        return StepOutput(
            step_id=self.step_id,
            step_type=self.step_type,
            message=resp.content,
            next_action=next_action,
        )

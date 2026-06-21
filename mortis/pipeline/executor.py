"""Mortis pipeline executor — 步骤执行引擎。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from mortis.memory import StepRecord, Thread
from mortis.runtime import RuntimeContext, SubRuntime, SubTemplate
from mortis.tools import ToolRegistry
from .step import ActStep, PlanStep, ReviewStep, StepOutput, ThinkStep
from .router import RouteDecision, TaskRouter


@dataclass
class PipelineResult:
    """Pipeline 执行结果。"""
    thread_id: str
    task: str
    output: str
    steps: list[dict]  # StepRecord.to_dict() 格式
    delegated: bool
    sub_id: str | None


class PipelineExecutor:
    """Pipeline 执行器 — 运行任务管道。"""

    def __init__(
        self,
        ctx: RuntimeContext,
        tools: ToolRegistry | None = None,
        verbose: bool = False,
    ) -> None:
        self.ctx = ctx
        self.tools = tools or ctx.tools
        self.verbose = verbose

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(f"  [executor] {msg}")

    def run(self) -> PipelineResult:
        """运行完整的 pipeline。

        流程:
        1. Router — 判断是否需要 sub
        2a. 简单路径：Think → Act → Review → 完成
        2b. 复杂路径：Think → Plan → Act → Review → 完成
        3. 产出写入 thread，完成 thread
        """
        thread = self.ctx.thread
        step_outputs: list[dict] = []

        # 1. 路由判断
        router = TaskRouter(self.ctx)
        route = router.route()
        self._log(f"route: {route.route} — {route.reason}")

        if route.should_delegate:
            return self._run_delegated(thread, step_outputs)

        # 2a / 2b: 直接执行
        steps = [
            ("think", ThinkStep),
            ("plan", PlanStep),  # plan 始终跑，输出简单时 plan 输出会很短
            ("act", ActStep),
            ("review", ReviewStep),
        ]

        for step_type, step_cls in steps:
            step_id = f"step-{step_type}-{uuid.uuid4().hex[:4]}"
            self._log(f"running step: {step_type} ({step_id})")

            if step_type == "act":
                step = ActStep(step_id, self.ctx, self.tools)
            else:
                step = step_cls(step_id, self.ctx)

            output = step.run()
            step_outputs.append({
                "step_id": step_id,
                "step_type": output.step_type,
                "input": thread.task,
                "output": output.message,
                "tool_calls": output.tool_results,
            })

            thread.add_step(StepRecord(
                step_id=step_id,
                step_type=output.step_type,
                input=thread.task,
                output=output.message,
                tool_calls=output.tool_results,
            ))

            # 记录 context refs
            for tc in output.tool_results:
                if "path" in tc.get("arguments", {}):
                    thread.add_context_ref(tc["arguments"]["path"])

            if output.next_action == "done":
                break

        # 3. 完成
        final_output = thread.steps[-1].output if thread.steps else ""
        thread.complete(final_output)
        self._save_thread(thread)

        return PipelineResult(
            thread_id=thread.thread_id,
            task=thread.task,
            output=final_output,
            steps=[s.__dict__ for s in thread.steps],
            delegated=False,
            sub_id=None,
        )

    def _run_delegated(
        self,
        thread: Thread,
        step_outputs: list[dict],
    ) -> PipelineResult:
        """运行委派路径：主人格派 sub，sub 执行任务，主人格审阅。

        审阅链路（issue #7 修复）：
        1. sub 产出写入 vault sub-outputs/
        2. ReviewGate.review() 自动审阅
        3. ReviewGate.apply() 执行决定（adopt/discard/merge/edit）
        4. 只有 ADOPT/MERGE/EDIT 才写入正式 vault
        """
        from mortis.vault import ReviewDecision, ReviewGate
        from mortis.runtime import SUB_VAULT_WHITELIST

        sub_id = f"sub-{uuid.uuid4().hex[:8]}"
        self._log(f"delegating to sub: {sub_id}")

        # 1. 主人格 Think（分析任务）
        think_id = f"step-think-{uuid.uuid4().hex[:4]}"
        think_step = ThinkStep(think_id, self.ctx)
        think_out = think_step.run()
        step_outputs.append({
            "step_id": think_id,
            "step_type": "think",
            "input": thread.task,
            "output": think_out.message,
            "tool_calls": [],
        })
        thread.add_step(StepRecord(
            step_id=think_id,
            step_type="think",
            input=thread.task,
            output=think_out.message,
            tool_calls=[],
        ))

        # 2. 生成 sub template（L1）— 用 from_seed 自动注入 parent_seed_hash
        sub_template = SubTemplate.from_seed(
            sub_id=sub_id,
            task=thread.task,
            seed=self.ctx.seed,
        )
        sub_runtime = SubRuntime(template=sub_template, ctx=self.ctx)

        # 3. sub 执行 Act
        act_id = f"step-act-{sub_id}"
        act_step = ActStep(act_id, self.ctx, self.tools)
        act_out = act_step.run()
        step_outputs.append({
            "step_id": act_id,
            "step_type": "act",
            "input": thread.task,
            "output": act_out.message,
            "tool_calls": act_out.tool_results,
        })
        thread.add_step(StepRecord(
            step_id=act_id,
            step_type="act",
            input=thread.task,
            output=act_out.message,
            tool_calls=act_out.tool_results,
        ))

        sub_runtime.complete(act_out.message)

        # 4. sub 产出写入 sub-outputs（pending_review）
        sub_output_rel = self.ctx.vault.write_sub_output(sub_id, act_out.message)
        self._log(f"sub output written to: {sub_output_rel}")

        # 5. ReviewGate 审阅（issue #7 核心）
        sub_entry = self.ctx.vault.read(sub_output_rel)
        review_result = ReviewGate.review(
            content=sub_entry.content,
            rel_path=sub_output_rel,
        )
        self._log(f"review decision: {review_result.decision.value} — {review_result.reason}")

        # 6. 执行审阅决定
        target_rel = ReviewGate.apply(
            vault_entry_content=act_out.message,
            rel_path=sub_output_rel,
            result=review_result,
            vault_write_fn=lambda rel, content: self.ctx.vault.write(rel, content),
            vault_read_fn=lambda rel: self.ctx.vault.read(rel).content,
            vault_discard_fn=lambda rel: self.ctx.vault.discard_sub_output(rel),
        )

        # 7. 记录审阅步骤
        review_id = f"step-review-{uuid.uuid4().hex[:4]}"
        review_message = f"ReviewGate: {review_result.decision.value} — {review_result.reason}"
        if target_rel:
            review_message += f" → 写入 {target_rel}"
        step_outputs.append({
            "step_id": review_id,
            "step_type": "review",
            "input": thread.task,
            "output": review_message,
            "tool_calls": [],
        })
        thread.add_step(StepRecord(
            step_id=review_id,
            step_type="review",
            input=thread.task,
            output=review_message,
            tool_calls=[],
        ))

        # 8. 完成
        final_output = target_rel if target_rel else "(discarded by ReviewGate)"
        thread.complete(final_output)
        self._save_thread(thread)

        return PipelineResult(
            thread_id=thread.thread_id,
            task=thread.task,
            output=final_output,
            steps=[s.__dict__ for s in thread.steps],
            delegated=True,
            sub_id=sub_id,
        )

    def _save_thread(self, thread: Thread) -> None:
        """持久化 thread 到磁盘。"""
        from pathlib import Path
        from datetime import datetime, timezone
        date = thread.created_at[:10]
        d = Path(self.ctx.vault.root) / "mortis-journal" / "sessions" / date
        d.mkdir(parents=True, exist_ok=True)
        thread.save(d)

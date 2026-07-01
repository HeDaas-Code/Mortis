"""Mortis Web Chat — 对话服务, 直接与主人格对话。

issue #88: 对话页面 — 参考 OpenUI 设计的对话交互。
区别于 ``cmd_delegate`` (任务派发, 走完整 pipeline Think→Plan→Act→Review),
对话是直接与主人格交谈: system[tone + unease + growth] + 多轮历史 → LLM。

ChatService 职责:
- 维护多个对话 (conversation_id → 消息历史)
- 构造 system prompt (复用 RuntimeContext 的 tone/unease/growth 注入逻辑)
- 调用 provider.generate / generate_stream
- 持久化对话到 vault (mortis-journal/conversations/<cid>.json)

设计要点:
- 对话 ≠ 任务。对话是闲聊/询问/讨论; 任务是「帮我做 X」走 pipeline。
- 多轮上下文: 显式保存 user/assistant 消息对, 而非靠 step.output 重建。
- 流式: 优先 provider.generate_stream, 未实现时 fallback 到 generate 单块。
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

from mortis.memory import StepRecord, Thread
from mortis.provider import Message, StreamChunk
from mortis.runtime import MasterRuntime

_logger = logging.getLogger(__name__)

# conversation_id 合法模式 — 防 path traversal (issue #90)
# 系统生成的 ID 形如 "conv-a1b2c3d4e5",只允许字母/数字/连字符。
_CID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9-]*$")


def is_valid_conversation_id(cid: str) -> bool:
    """校验 conversation_id 是否安全 (无 path traversal 风险, issue #90)。

    合法: 非空, 首字符为字母/数字, 只含字母/数字/连字符, 长度 ≤ 64。
    非法: 含 ``/`` ``\\`` ``..`` 等路径分隔/遍历字符。
    """
    if not cid or len(cid) > 64:
        return False
    return _CID_PATTERN.match(cid) is not None


@dataclass
class ChatMessage:
    """对话中的单条消息。"""
    role: str  # user | assistant | system
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now(tz=timezone.utc).isoformat())


@dataclass
class Conversation:
    """单个对话 — 多轮消息历史。"""
    conversation_id: str
    created_at: str = field(default_factory=lambda: datetime.now(tz=timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(tz=timezone.utc).isoformat())
    messages: list[ChatMessage] = field(default_factory=list)
    title: str = ""
    # issue #92: 对话→Session 管道 — 对话绑定的 thread_id (写入 sessions/<date>/<thread_id>.json)
    # 首次 send() 时由 master.create_thread() 创建, 后续 send() 复用同一 thread。
    thread_id: str | None = None

    def add_user(self, content: str) -> ChatMessage:
        msg = ChatMessage(role="user", content=content)
        self.messages.append(msg)
        self.updated_at = datetime.now(tz=timezone.utc).isoformat()
        if not self.title:
            self.title = content[:40]
        return msg

    def add_assistant(self, content: str) -> ChatMessage:
        msg = ChatMessage(role="assistant", content=content)
        self.messages.append(msg)
        self.updated_at = datetime.now(tz=timezone.utc).isoformat()
        return msg

    def to_dict(self) -> dict:
        return {
            "conversation_id": self.conversation_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "title": self.title,
            "thread_id": self.thread_id,
            "messages": [
                {"role": m.role, "content": m.content, "timestamp": m.timestamp}
                for m in self.messages
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> Conversation:
        msgs = [ChatMessage(role=m["role"], content=m["content"], timestamp=m["timestamp"])
                for m in data.get("messages", [])]
        return cls(
            conversation_id=data["conversation_id"],
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            title=data.get("title", ""),
            messages=msgs,
            thread_id=data.get("thread_id"),
        )


@dataclass
class ChatResponse:
    """单次对话响应。"""
    conversation_id: str
    message: str
    role: str = "assistant"
    elapsed_sec: float = 0.0


class ChatService:
    """对话服务 — 封装 MasterRuntime 提供多轮对话能力。

    用法::

        chat = ChatService(master)
        resp = chat.send("你好")
        print(resp.message)

        for chunk in chat.stream("继续聊聊"):
            print(chunk.delta, end="")
    """

    def __init__(self, master: MasterRuntime) -> None:
        self.master = master
        self._conversations: dict[str, Conversation] = {}

    # ----- 对话管理 -----

    def create_conversation(self) -> Conversation:
        cid = f"conv-{uuid.uuid4().hex[:10]}"
        conv = Conversation(conversation_id=cid)
        self._conversations[cid] = conv
        self._save_conversation(conv)
        return conv

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        if not is_valid_conversation_id(conversation_id):
            return None
        if conversation_id in self._conversations:
            return self._conversations[conversation_id]
        # 尝试从磁盘加载
        conv = self._load_conversation(conversation_id)
        if conv:
            self._conversations[conversation_id] = conv
        return conv

    def list_conversations(self) -> list[dict]:
        """列出所有对话 (摘要, 不含完整消息)。"""
        # 合并内存 + 磁盘
        seen: set[str] = set()
        result: list[dict] = []
        for cid, conv in self._conversations.items():
            seen.add(cid)
            result.append({
                "conversation_id": conv.conversation_id,
                "title": conv.title,
                "created_at": conv.created_at,
                "updated_at": conv.updated_at,
                "message_count": len(conv.messages),
            })
        # 补充磁盘上的对话
        for d in self._list_disk_conversations():
            if d["conversation_id"] not in seen:
                result.append(d)
        # 按 updated_at 降序
        result.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return result

    def delete_conversation(self, conversation_id: str) -> bool:
        if not is_valid_conversation_id(conversation_id):
            return False
        existed = conversation_id in self._conversations
        if existed:
            del self._conversations[conversation_id]
        p = self._conversation_path(conversation_id)
        if p.exists():
            p.unlink()
            return True
        return existed

    def get_history(self, conversation_id: str) -> list[dict] | None:
        conv = self.get_conversation(conversation_id)
        if conv is None:
            return None
        return [
            {"role": m.role, "content": m.content, "timestamp": m.timestamp}
            for m in conv.messages
        ]

    def get_or_create_conversation(self, conversation_id: str | None) -> Conversation:
        """公开入口 — 获取或新建对话 (不添加消息)。

        供 SSE 流式 handler 在流式开始前预先拿到 conversation_id,
        以便在第一个 chunk 里带回给前端。
        """
        return self._get_or_create(conversation_id)

    # ----- 核心: 发送消息 -----

    def send(
        self,
        user_message: str,
        conversation_id: str | None = None,
        *,
        temperature: float = 0.7,
    ) -> ChatResponse:
        """发送一条消息, 同步返回响应。

        Args:
            user_message: 用户消息文本。
            conversation_id: 对话 ID。None = 新建对话。
            temperature: 采样温度。

        Returns:
            ChatResponse 含 assistant 回复。
        """
        conv = self._get_or_create(conversation_id)
        conv.add_user(user_message)

        messages = self._build_messages(conv)
        start = datetime.now(tz=timezone.utc)
        reply = self.master.provider.generate(messages, temperature=temperature)
        elapsed = (datetime.now(tz=timezone.utc) - start).total_seconds()

        conv.add_assistant(reply.content)
        self._save_conversation(conv)
        # issue #92: 对话→Session 管道 — 把这轮 chat 写入 thread (sessions/<date>/<thread_id>.json)
        # dream pipeline 读 sessions/ 目录, 没 thread 文件 → 永远空 → growth 不增长。
        self._record_chat_step(conv, user_message, reply.content)

        return ChatResponse(
            conversation_id=conv.conversation_id,
            message=reply.content,
            elapsed_sec=elapsed,
        )

    def stream(
        self,
        user_message: str,
        conversation_id: str | None = None,
        *,
        temperature: float = 0.7,
    ) -> Generator[StreamChunk, None, None]:
        """流式发送消息, 逐块 yield StreamChunk。

        provider 未实现 generate_stream 时 fallback 到 generate 单块。
        流式完成后, 完整回复仍会写入对话历史。
        """
        conv = self._get_or_create(conversation_id)
        conv.add_user(user_message)
        messages = self._build_messages(conv)

        provider = self.master.provider
        full_content = ""
        if hasattr(provider, "generate_stream"):
            for chunk in provider.generate_stream(messages, temperature=temperature):
                full_content += chunk.delta
                yield chunk
        else:
            # fallback: 非流式 → 单块
            reply = provider.generate(messages, temperature=temperature)
            full_content = reply.content
            yield StreamChunk(delta=reply.content, finish_reason="stop")

        conv.add_assistant(full_content)
        self._save_conversation(conv)
        # issue #92: 流式对话也写入 thread, 与 send() 对齐
        self._record_chat_step(conv, user_message, full_content)

    # ----- 消息构造 -----

    def _build_messages(self, conv: Conversation) -> list[Message]:
        """构建发给 provider 的消息列表。

        - system[0]: seed tone (主人格语气)
        - system[1] (可选): unease 潜台词 (steiner 隐藏层)
        - system[2] (可选): growth 摘要 (相关 growth 上下文)
        - system[3] (可选): expression patterns (learned) — dream 提炼的表达模式 (issue #94)
        - user/assistant: 对话历史

        issue #94: 与 RuntimeContext.messages_for_provider 注入顺序对齐,
        让对话也享受 expression patterns 注入。
        """
        from mortis.memory import Thread
        # 借用 RuntimeContext 的注入逻辑 (tone / unease / growth)
        # 用一个内存中的临时 thread (不持久化), 仅为了访问 growth_context_for_task
        last_user = ""
        for m in reversed(conv.messages):
            if m.role == "user":
                last_user = m.content
                break
        thread = Thread(
            thread_id=f"ephemeral-{conv.conversation_id}",
            session_id=self.master.session.session_id,
            task=last_user or conv.title or "",
        )
        ctx = self.master.make_context(thread)

        msgs: list[Message] = [
            Message(role="system", content=self.master.seed.to_prompt()),
        ]
        # unease 潜台词
        unease_text = ctx.unease_prompt_for_injection()
        if unease_text:
            msgs.append(Message(role="system", content=unease_text))
        # growth 上下文 (基于最近 user 消息检索)
        growth_prompt = ctx.growth_context_for_task(last_user)
        if growth_prompt:
            msgs.append(Message(role="system", content=growth_prompt))
        # issue #94: expression patterns (learned) 段
        expr_prompt = ctx.expression_patterns_prompt()
        if expr_prompt:
            msgs.append(Message(role="system", content=expr_prompt))

        # 对话历史 (provider 需要看到完整历史)
        for m in conv.messages:
            msgs.append(Message(role=m.role, content=m.content))
        return msgs

    def _get_or_create(self, conversation_id: str | None) -> Conversation:
        if conversation_id:
            conv = self.get_conversation(conversation_id)
            if conv is None:
                conv = self.create_conversation()
            return conv
        return self.create_conversation()

    # ----- issue #92: 对话→Session 管道 -----

    def _record_chat_step(
        self,
        conv: Conversation,
        user_message: str,
        assistant_reply: str,
    ) -> None:
        """把这轮 user→assistant 对话作为 step 写入 thread 文件。

        thread 文件路径: ``vault/mortis-journal/sessions/<date>/<thread_id>.json`` —
        与 dream pipeline 的 ``_load_recent_sessions`` 读的目录一致。

        首次调用为对话创建 thread (task=首条消息前 50 字); 后续调用复用同一 thread,
        每轮对话追加一个 ``step_type="chat"`` 的 StepRecord。
        静默失败 — thread 写入异常不应阻断主对话流程。

        issue #94: thread 写入后追加 ``record_turn_stats`` — 把这轮对话双侧
        文本统计写入 ``mortis-journal/expression-stats/<date>.json``,
        供 dream EXPRESSION_DISTILL phase 读取提炼表达模式。
        """
        try:
            thread = self._get_or_create_thread(conv, user_message)
            if thread is None:
                return
            step_id = f"step-chat-{len(thread.steps) + 1:03d}"
            step = StepRecord(
                step_id=step_id,
                step_type="chat",
                input=user_message,
                output=assistant_reply,
                tool_calls=[],
            )
            thread.add_step(step)
            thread.save(self._thread_session_dir())
        except Exception as e:
            _logger.warning(
                "record chat step to thread failed (conv=%s): %s",
                conv.conversation_id, e,
            )
        # issue #94: 对话后触发表达统计写入 (静默失败, 不阻断主流程)
        # 放在独立 try — thread 写入失败不影响 stats 写入, 反之亦然
        try:
            from mortis.expression.stats import record_turn_stats
            record_turn_stats(self.master.vault, user_message, assistant_reply)
        except Exception as e:
            _logger.warning(
                "record expression stats failed (conv=%s): %s",
                conv.conversation_id, e,
            )

    def _get_or_create_thread(
        self,
        conv: Conversation,
        user_message: str,
    ) -> Thread | None:
        """获取或新建对话绑定的 thread。

        - conv.thread_id 已存在 → 复用 (内存缓存或磁盘加载)
        - 否则 → ``master.create_thread(task=首条消息前 50 字)`` 新建,
          并把 thread_id 回填到 conv, 持久化 conv 让后续 send() 能复用
        """
        if conv.thread_id:
            thread = self.master.get_thread(conv.thread_id)
            if thread is not None:
                return thread
            # 内存里没了 (新进程) → 从磁盘 load; 失败则重建
            try:
                thread = Thread.load(self._thread_session_dir(), conv.thread_id)
                return thread
            except FileNotFoundError:
                _logger.warning(
                    "thread %s not on disk, recreating for conv %s",
                    conv.thread_id, conv.conversation_id,
                )
        # 新建 thread: task 用首条用户消息前 50 字 (与 issue 文档对齐)
        task = f"对话: {user_message[:50]}"
        thread = self.master.create_thread(task=task)
        conv.thread_id = thread.thread_id
        # 回填 thread_id 后立即持久化 conv, 防止下次 send() 重复创建 thread
        self._save_conversation(conv)
        return thread

    def _thread_session_dir(self) -> Path:
        """thread 文件目录 — 与 master._session_dir() 同源。

        ``vault/mortis-journal/sessions/<YYYY-MM-DD>/`` — 按 session.created_at 取日期。
        dream pipeline 扫这个目录读 thread/session 文件。
        """
        date = self.master.session.created_at[:10]
        d = self.master.vault.root / "mortis-journal" / "sessions" / date
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ----- 持久化 -----

    def _conversations_dir(self) -> Path:
        d = self.master.vault.root / "mortis-journal" / "conversations"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _conversation_path(self, conversation_id: str) -> Path:
        return self._conversations_dir() / f"{conversation_id}.json"

    def _save_conversation(self, conv: Conversation) -> None:
        try:
            p = self._conversation_path(conv.conversation_id)
            p.write_text(
                json.dumps(conv.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            _logger.warning("save conversation %s failed: %s", conv.conversation_id, e)

    def _load_conversation(self, conversation_id: str) -> Conversation | None:
        p = self._conversation_path(conversation_id)
        if not p.exists():
            return None
        try:
            return Conversation.from_dict(json.loads(p.read_text(encoding="utf-8")))
        except Exception as e:
            _logger.warning("load conversation %s failed: %s", conversation_id, e)
            return None

    def _list_disk_conversations(self) -> list[dict]:
        d = self._conversations_dir()
        result: list[dict] = []
        for f in sorted(d.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                result.append({
                    "conversation_id": data["conversation_id"],
                    "title": data.get("title", ""),
                    "created_at": data.get("created_at", ""),
                    "updated_at": data.get("updated_at", ""),
                    "message_count": len(data.get("messages", [])),
                })
            except Exception:
                pass
        return result


__all__ = [
    "ChatMessage", "Conversation", "ChatResponse", "ChatService",
    "is_valid_conversation_id",
]

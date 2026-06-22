"""Mortis reflect — ReflectExecutor 主流程。

issue #21: REFLECT phase 把多个 session 合成一篇反思。

完整流程:
1. 读 session_paths 里的所有 session(本 JSON 已落盘,直接 Session.load)
2. 拼成 session 摘要文本(每个 session 取 threads 列表 + task 摘要)
3. 调 LLM 写反思 body(self-provider 决定语气/格式)
4. 调 emotion.score_emotion 给整篇打分
5. 写 mortis-subconscious/pending-reflections/<id>.md
   - frontmatter: id / session_paths / valence / arousal / created_at
   - H1 标题
   - body
   - `> [!note]` 元认知 callout
6. 返回 Reflection frozen dataclass

设计原则:
- 不破坏 #20 messages_for_provider 契约(system[0]=tone, system[1]=growth 段)
- executor 写文件走 vault.write(rel, content, whitelist=None)
  subconscious 不在 growth whitelist 内(也不应在 — 它是中间态)
- 不在 executor 里改 Session 实例(它也是 frozen-by-usage)
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

from mortis.growth.frontmatter import serialize_frontmatter
from mortis.memory.session import Session
from mortis.provider.base import LLMProviderProtocol
from mortis.vault.local import Vault
from mortis.vault.obsidian import render_callout

from .emotion import score_emotion


_logger = logging.getLogger(__name__)


# pending-reflections 子目录(对应 mortis.growth.vault_layout.SUBCONSCIOUS_SUBDIRS[0])
PENDING_REFLECTIONS_SUBDIR = "pending-reflections"
SUBCONSCIOUS_ROOT = "mortis-subconscious"

# 反思 prompt — 喂给 LLM 写反思文本
_REFLECT_PROMPT = """你是 {mortis_name},一位正在反思的智能体。
请阅读以下最近的 session 内容,写一段 80~150 字的反思,覆盖:
- 这几个 session 里你(和 owner)主要在做什么
- 你的语气 / 取舍是否有反复出现的模式
- 哪条经验似乎稳定(可以记下来)
- 哪条还存疑(还不敢写死)

要求:
- 用第一人称(我),中文
- 末尾不要总结/收束(那是后续 DREAM 阶段的事)
- 不要 markdown 标题 / 列表 — 一段连续文字即可

sessions:
\"\"\"
{sessions_text}
\"\"\"
"""

# 元认知 callout 模板(写入 md 末尾)
_METACOGNITION_NOTE = (
    "本反思由 REFLECT phase 写入 pending-reflections/。"
    "下一步:DREAM-LIGHT 会扫描此目录做联想 / 关联 / 标记 候选 growth。"
)


# ============================================================
# 数据结构
# ============================================================


@dataclass(frozen=True)
class Reflection:
    """一篇反思的不可变快照 — 写盘 + 返回给调用方。

    frozen: 与 Growth 风格一致。frozen 之后修改走 dataclasses.replace。
    """
    id: str  # reflect-YYYY-MM-DD-NNN
    session_paths: tuple[str, ...]
    valence: float  # -1.0 ~ 1.0
    arousal: float  # 0.0 ~ 1.0
    body: str  # 反思文本
    created_at: str  # ISO8601
    rel_path: str  # mortis-subconscious/pending-reflections/<id>.md


# ============================================================
# 路径辅助
# ============================================================


def reflection_rel(reflection_id: str) -> str:
    """Reflection 相对路径(写盘位置)。"""
    return f"{SUBCONSCIOUS_ROOT}/{PENDING_REFLECTIONS_SUBDIR}/{reflection_id}.md"


def list_pending_reflections(vault: Vault) -> list[str]:
    """列 vault 内所有 pending reflections 的相对路径(按 id 升序)。"""
    rel_dir = f"{SUBCONSCIOUS_ROOT}/{PENDING_REFLECTIONS_SUBDIR}"
    try:
        entries = vault.list_entries(rel_dir)
    except Exception:
        return []
    return sorted(e for e in entries if e.endswith(".md"))


# ============================================================
# 主流程
# ============================================================


class ReflectExecutor:
    """REFLECT phase 执行体 — 读 session → 写反思。

    构造时注入 vault / provider / mortis_name(注入便于测试 + 多实例)。
    """

    def __init__(
        self,
        vault: Vault,
        provider: LLMProviderProtocol,
        mortis_name: str = "Mortis",
    ) -> None:
        self.vault = vault
        self.provider = provider
        self.mortis_name = mortis_name

    # ----- 公开 API -----

    def run(
        self,
        session_paths: Sequence[str],
        sessions_dir: Path | None = None,
    ) -> Reflection:
        """对一组 session 执行 REFLECT。

        Args:
            session_paths: 要反思的 session 相对路径列表(给 cache key 用 + 写盘记录)。
            sessions_dir: 实际 JSON 文件目录。None 时用 vault.root / mortis-journal/sessions。
                传参便于测试(把 fixture 放 tmp dir)。
        """
        if not session_paths:
            raise ValueError("session_paths must be non-empty")

        sessions = self._load_sessions(session_paths, sessions_dir)
        sessions_text = self._summarize_sessions(sessions)

        body = self._generate_reflection(sessions_text)
        # 情绪打分:用第一个 session_path 作 cache key(同批 session 共享情绪基调)
        cache_key = session_paths[0]
        valence, arousal = score_emotion(self.provider, cache_key, sessions_text)

        rid = self._next_reflection_id()
        created_at = datetime.now(tz=timezone.utc).isoformat()
        rel = reflection_rel(rid)

        content = self._render_reflection_md(
            rid=rid,
            session_paths=tuple(session_paths),
            valence=valence,
            arousal=arousal,
            created_at=created_at,
            body=body,
        )
        # 走 vault.write 但不传 whitelist — subconscious 是 owner 私有
        # 中间态,不在 GROWTH_WHITELIST 内(也不应被 owner 重读成 growth)
        self.vault.write(rel, content, whitelist=None)

        return Reflection(
            id=rid,
            session_paths=tuple(session_paths),
            valence=valence,
            arousal=arousal,
            body=body,
            created_at=created_at,
            rel_path=rel,
        )

    # ----- 内部 -----

    def _load_sessions(
        self,
        session_paths: Sequence[str],
        sessions_dir: Path | None,
    ) -> list[Session]:
        """从 sessions_dir / <sid>.json 读所有 session。"""
        if sessions_dir is None:
            sessions_dir = self.vault.root / "mortis-journal" / "sessions"
        sessions: list[Session] = []
        for rel in session_paths:
            # rel 可能是带日期子目录(s-sessions/2026-06-22/x.json),也可能是
            # 仅文件名。优先按 rel 当相对 sessions_dir;若不存在再按 stem 找。
            sid = Path(rel).stem
            candidates = [sessions_dir / rel, sessions_dir / f"{sid}.json"]
            for c in candidates:
                if c.exists():
                    sessions.append(Session.load(c.parent, sid))
                    break
            else:
                raise FileNotFoundError(
                    f"session file not found under {sessions_dir}: {rel}"
                )
        return sessions

    def _summarize_sessions(self, sessions: Iterable[Session]) -> str:
        """把多 session 拼成一段喂给 LLM 的纯文本。"""
        chunks: list[str] = []
        for i, s in enumerate(sessions, 1):
            threads_str = ", ".join(s.threads) if s.threads else "(no threads)"
            chunks.append(
                f"[session #{i}] id={s.session_id}\n"
                f"created_at={s.created_at}\n"
                f"threads={threads_str}"
            )
        return "\n\n".join(chunks) or "(empty sessions)"

    def _generate_reflection(self, sessions_text: str) -> str:
        """调 LLM 写反思文本。"""
        prompt = _REFLECT_PROMPT.format(
            mortis_name=self.mortis_name,
            sessions_text=sessions_text,
        )
        text = self.provider.generate_text(prompt)
        # 防御:LLM 偶尔返回空 — 退到占位
        return (text or "").strip() or "(no reflection generated)"

    def _next_reflection_id(self) -> str:
        """生成下一个 reflection id: reflect-YYYY-MM-DD-NNN(当天序号从 001 开始)。"""
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        prefix = f"reflect-{today}-"
        existing = list_pending_reflections(self.vault)
        # 只数今天的(其它日期不占序号)
        same_day = [e for e in existing if Path(e).name.startswith(prefix)]
        n = len(same_day) + 1
        return f"{prefix}{n:03d}"

    def _render_reflection_md(
        self,
        rid: str,
        session_paths: tuple[str, ...],
        valence: float,
        arousal: float,
        created_at: str,
        body: str,
    ) -> str:
        """把 reflection 序列化为完整 md 文本。"""
        meta: dict[str, object] = {
            "id": rid,
            "session_paths": list(session_paths),
            "valence": valence,
            "arousal": arousal,
            "created_at": created_at,
        }
        front = serialize_frontmatter(meta, "")
        # 取 body 第一句作 H1 标题(更易在 Obsidian 里浏览)
        title = self._title_for(body, rid)
        callout = render_callout("note", _METACOGNITION_NOTE)
        parts: list[str] = [
            front,
            "",  # frontmatter 收尾空行
            title,
            "",
            body.rstrip(),
            "",
            callout,
            "",
        ]
        text = "\n".join(parts)
        return text.rstrip() + "\n"

    @staticmethod
    def _title_for(body: str, fallback: str) -> str:
        """从 body 抽首句作 H1 标题。失败用 id。"""
        src = (body or "").strip()
        if not src:
            return f"# {fallback}"
        for sep in ("。", ".", "!", "?", "！", "?"):
            idx = src.find(sep)
            if idx != -1 and idx < 80:
                return f"# {src[: idx + 1].strip()}"
        head = src.split("\n", 1)[0].strip()
        if len(head) <= 80:
            return f"# {head}"
        return f"# {head[:80]}…"

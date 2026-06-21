"""Mortis runtime master — 主人格运行时。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mortis.seed import Seed
from mortis.vault import Vault
from mortis.memory import Session, Thread, MemoryArchive
from mortis.provider import LLMProviderProtocol, Message
from .context import RuntimeContext

if TYPE_CHECKING:
    from mortis.tools import ToolRegistry


MORTIS_NAME = "Mortis"


@dataclass
class MasterRuntime:
    """主人格运行时 — 主人格的执行体。"""
    seed: Seed
    vault: Vault
    provider: LLMProviderProtocol
    session: Session
    _threads: dict[str, Thread] = field(default_factory=dict)
    _archive: MemoryArchive | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self._archive = MemoryArchive(self.vault)

    def identify(self) -> str:
        first_line = self.seed.identity.strip().splitlines()[0]
        return f"{MORTIS_NAME}. {first_line}"

    def make_context(self, thread: Thread, tools: "ToolRegistry | None" = None) -> RuntimeContext:
        return RuntimeContext(
            seed=self.seed,
            vault=self.vault,
            provider=self.provider,
            session=self.session,
            thread=thread,
            tools=tools,
        )

    def create_thread(self, task: str) -> Thread:
        thread_id = f"th-{uuid.uuid4().hex[:8]}"
        thread = Thread(
            thread_id=thread_id,
            session_id=self.session.session_id,
            task=task,
        )
        self._threads[thread_id] = thread
        self.session.add_thread(thread_id)
        thread.save(self._session_dir())
        return thread

    def get_thread(self, thread_id: str) -> Thread | None:
        if thread_id in self._threads:
            return self._threads[thread_id]
        try:
            t = Thread.load(self._session_dir(), thread_id)
            self._threads[thread_id] = t
            return t
        except FileNotFoundError:
            return None

    def complete_thread(self, thread_id: str, output: str) -> Thread | None:
        thread = self.get_thread(thread_id)
        if thread:
            thread.complete(output)
            thread.save(self._session_dir())
        return thread

    def discard_thread(self, thread_id: str) -> Thread | None:
        thread = self.get_thread(thread_id)
        if thread:
            thread.discard()
            thread.save(self._session_dir())
        return thread

    def archive_thread(
        self,
        thread_id: str,
        summary: str,
        target_rel: str | None = None,
    ) -> None:
        thread = self.get_thread(thread_id)
        if not thread:
            raise FileNotFoundError(f"thread not found: {thread_id}")
        self._archive.archive_thread(
            thread_id=thread_id,
            thread_json_path=self._session_dir() / f"{thread_id}.json",
            summary=summary,
            target_rel=target_rel,
        )

    def read_vault(self, rel_path: str) -> str:
        return self.vault.read(rel_path).content

    def write_vault(self, rel_path: str, content: str) -> None:
        self.vault.write(rel_path, content)

    def _session_dir(self) -> "Path":
        from pathlib import Path
        date = self.session.created_at[:10]
        d = self.vault.root / "mortis-journal" / "sessions" / date
        d.mkdir(parents=True, exist_ok=True)
        return d

    def generate(self, messages: list[Message]) -> Message:
        return self.provider.generate(messages)

    def generate_text(self, prompt: str, system: str = "") -> str:
        return self.provider.generate_text(prompt, system=system)

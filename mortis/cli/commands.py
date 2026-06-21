"""Mortis CLI commands — 命令注册表。"""

from __future__ import annotations

import argparse
from pathlib import Path

from mortis.seed import load_seed
from mortis.vault import Vault
from mortis.provider import make_provider
from mortis.memory import Session
from mortis.runtime import MasterRuntime
from mortis.pipeline import PipelineExecutor
from mortis.tools import make_default_registry


def _default_seed_path() -> Path:
    for candidate in (Path("seed.md"), Path("vault/mortis-seed.md")):
        if candidate.exists():
            return candidate
    raise FileNotFoundError("no seed.md found in ./ or ./vault/")


def _default_vault_path() -> Path:
    return Path("vault")


def _build_master(vault_path: Path, seed_path: Path, provider_kind: str = "auto"):
    seed = load_seed(seed_path)
    vault = Vault(vault_path)
    provider = make_provider(provider_kind)
    session = Session(session_id=f"cli-{Path.cwd().name}")
    master = MasterRuntime(
        seed=seed,
        vault=vault,
        provider=provider,
        session=session,
    )
    return master


def cmd_list(args: argparse.Namespace) -> int:
    vault = Vault(args.vault)
    entries = vault.list_entries(args.dir)
    for e in entries:
        print(e)
    return 0


def cmd_whoami(args: argparse.Namespace) -> int:
    master = _build_master(args.vault, args.seed, args.provider)
    print(master.identify())
    return 0


def cmd_dump(args: argparse.Namespace) -> int:
    vault = Vault(args.vault)
    entry = vault.read(args.path)
    print(entry.content)
    return 0


def cmd_delegate(args: argparse.Namespace) -> int:
    """派一个 sub 跑任务（走新 pipeline）。"""
    master = _build_master(args.vault, args.seed, args.provider)

    # 创建线程
    thread = master.create_thread(args.task)

    # 构建上下文
    tools = make_default_registry(master.vault)
    ctx = master.make_context(thread, tools=tools)

    # 执行 pipeline
    executor = PipelineExecutor(ctx, tools=tools, verbose=args.verbose)
    result = executor.run()

    # 写 sub 产出到 vault
    if result.delegated and result.sub_id:
        rel = master.vault.write_sub_output(result.sub_id, result.output)
        print(f"sub_id: {result.sub_id}")
        print(f"output_rel: {rel}")
    else:
        print(f"thread_id: {result.thread_id}")

    print(f"status: {thread.status}")
    print("---")
    print(result.output[:500] if len(result.output) > 500 else result.output)
    if args.verbose:
        print(f"--- steps ---")
        for step in result.steps:
            print(f"  [{step['step_type']}] {step['step_id']}")
    return 0


def cmd_pending(args: argparse.Namespace) -> int:
    vault = Vault(args.vault)
    pending = vault.list_pending_sub_outputs()
    if not pending:
        print("(no pending sub outputs)")
    else:
        for p in pending:
            print(p)
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    vault = Vault(args.vault)
    target = vault.approve_sub_output(args.rel, args.target)
    print(f"approved -> {target}")
    return 0


def cmd_discard(args: argparse.Namespace) -> int:
    vault = Vault(args.vault)
    vault.discard_sub_output(args.rel)
    print(f"discarded -> {args.rel}")
    return 0


def cmd_archive(args: argparse.Namespace) -> int:
    """归档一个 thread 到 vault。"""
    master = _build_master(args.vault, args.seed)
    thread_id = args.thread_id
    summary = args.summary or args.task or "untitled"
    target = args.target
    master.archive_thread(thread_id, summary, target_rel=target)
    print(f"archived: {thread_id} -> {target or 'auto'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mortis",
        description="Mortis — 基于 vault 的主人格 agent",
    )
    parser.add_argument(
        "--vault", type=Path, default=_default_vault_path(),
        help="vault 根目录（default: ./vault）",
    )
    parser.add_argument(
        "--seed", type=Path, default=_default_seed_path(),
        help="seed 文件路径（default: ./seed.md 或 ./vault/mortis-seed.md）",
    )

    sub = parser.add_subparsers(dest="command")

    # list
    p_list = sub.add_parser("list", help="列 vault 内文件")
    p_list.add_argument("dir", nargs="?", default="", help="子目录（默认根）")

    # whoami
    p_who = sub.add_parser("whoami", help="主人格自报身份")
    p_who.add_argument(
        "--provider", default="auto",
        choices=["auto", "minimax", "mock"],
        help="LLM provider（default: auto）",
    )

    # dump
    p_dump = sub.add_parser("dump", help="读 vault 内一个文件")
    p_dump.add_argument("path", help="相对 vault 根的路径")

    # delegate (走新 pipeline)
    p_del = sub.add_parser("delegate", help="派一个 sub 跑任务")
    p_del.add_argument("task", help="sub 要完成的任务")
    p_del.add_argument(
        "--provider", default="auto",
        choices=["auto", "minimax", "mock"],
        help="LLM provider（default: auto）",
    )
    p_del.add_argument("--verbose", action="store_true", help="打印详细执行信息")

    # pending
    sub.add_parser("pending", help="列待审 sub 产出")

    # approve
    p_app = sub.add_parser("approve", help="批准 sub 产出")
    p_app.add_argument("rel", help="sub 产出相对 vault 的路径")
    p_app.add_argument("--target", default=None, help="合并到的目标路径")

    # discard
    p_dis = sub.add_parser("discard", help="丢弃 sub 产出")
    p_dis.add_argument("rel", help="sub 产出相对 vault 的路径")

    # archive (新增)
    p_arc = sub.add_parser("archive", help="归档 thread 经验到 vault")
    p_arc.add_argument("thread_id", help="要归档的 thread ID")
    p_arc.add_argument("--summary", default=None, help="经验摘要")
    p_arc.add_argument("--task", default=None, help="任务描述（用于自动摘要）")
    p_arc.add_argument("--target", default=None, help="归档到的 vault 路径")

    return parser


COMMANDS = {
    "list": cmd_list,
    "whoami": cmd_whoami,
    "dump": cmd_dump,
    "delegate": cmd_delegate,
    "pending": cmd_pending,
    "approve": cmd_approve,
    "discard": cmd_discard,
    "archive": cmd_archive,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    handler = COMMANDS[args.command]
    return handler(args)

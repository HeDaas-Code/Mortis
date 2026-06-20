"""Mortis CLI 入口。

子命令:
    list        列 vault 内文件
    whoami      主人格自报身份
    dump <path> 读 vault 内一个文件
    help        帮助

v1 新增:
    delegate <task>    派一个 sub 完成任务
    pending            列出待审阅的 sub 产出
    approve <rel>      批准 sub 产出
    discard <rel>      丢弃 sub 产出
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .persona import Mortis
from .seed import load_seed
from .vault import Vault


def _default_seed_path() -> Path:
    """默认 seed 路径 — 先看 ./seed.md,再看 ./vault/mortis-seed.md。"""
    for candidate in (Path("seed.md"), Path("vault/mortis-seed.md")):
        if candidate.exists():
            return candidate
    raise FileNotFoundError("no seed.md found in ./ or ./vault/")


def _default_vault_path() -> Path:
    """默认 vault 路径 — ./vault/。"""
    return Path("vault")


def cmd_list(args: argparse.Namespace) -> int:
    vault = Vault(args.vault)
    entries = vault.list_entries(args.dir)
    for e in entries:
        print(e)
    return 0


def cmd_whoami(args: argparse.Namespace) -> int:
    seed = load_seed(args.seed)
    master = Mortis(seed=seed, vault_path=str(args.vault))
    print(master.identify())
    return 0


def cmd_dump(args: argparse.Namespace) -> int:
    vault = Vault(args.vault)
    entry = vault.read(args.path)
    print(entry.content)
    return 0


def cmd_help(args: argparse.Namespace) -> int:
    parser = build_parser()
    parser.print_help()
    return 0


# ----- v1 新增:委派 + 审稿 -----

def cmd_delegate(args: argparse.Namespace) -> int:
    """派一个 sub 跑任务(v1-issue-1 + v1-issue-2)。

    用法: mortis delegate <task> [--provider minimax|mock|auto]
    """
    from .layers import delegate, complete_delegation
    from .providers import make_provider

    seed = load_seed(args.seed)
    vault = Vault(args.vault)
    provider = make_provider(args.provider)

    master = Mortis(seed=seed, vault_path=str(args.vault), provider=provider)
    sub = delegate(master, args.task, sub_id=args.sub_id, context=None)

    # v1-issue-1 的 sub 任务执行 — 现在用 prompt 直接调 LLM provider
    # 让 sub 知道它是什么(task + voice),生成 output
    prompt = (
        f"You are a Mortis sub.\n"
        f"Task: {sub.template.task}\n"
        f"Voice: {sub.template.voice}\n"
        f"Agency scope: {sub.template.agency_scope}\n"
        f"Constraints: {', '.join(sub.template.constraints)}\n\n"
        f"Complete the task. Return only the result."
    )
    output = provider.generate(prompt, system=seed.tone)
    result = complete_delegation(sub, output)

    # 写产出到 vault(F:sub 产出合并回 vault — 先存待审)
    rel = vault.write_sub_output(result.sub_id, result.output)

    print(f"sub_id: {result.sub_id}")
    print(f"status: {result.status}")
    print(f"output_rel: {rel}")
    print(f"---")
    print(result.output)
    return 0


def cmd_pending(args: argparse.Namespace) -> int:
    """列待审 sub 产出。"""
    vault = Vault(args.vault)
    pending = vault.list_pending_sub_outputs()
    if not pending:
        print("(no pending sub outputs)")
    else:
        for p in pending:
            print(p)
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    """批准 sub 产出。"""
    vault = Vault(args.vault)
    target = vault.approve_sub_output(args.rel, args.target)
    print(f"approved -> {target}")
    return 0


def cmd_discard(args: argparse.Namespace) -> int:
    """丢弃 sub 产出。"""
    vault = Vault(args.vault)
    vault.discard_sub_output(args.rel)
    print(f"discarded -> {args.rel}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mortis",
        description="Mortis — 基于 vault 的主人格 agent",
    )
    parser.add_argument(
        "--vault", type=Path, default=_default_vault_path(),
        help="vault 根目录 (default: ./vault)",
    )
    parser.add_argument(
        "--seed", type=Path, default=_default_seed_path(),
        help="seed 文件路径 (default: ./seed.md 或 ./vault/mortis-seed.md)",
    )

    sub = parser.add_subparsers(dest="command")

    # list
    p_list = sub.add_parser("list", help="列 vault 内文件")
    p_list.add_argument("dir", nargs="?", default="", help="子目录(默认根)")

    # whoami
    sub.add_parser("whoami", help="主人格自报身份")

    # dump
    p_dump = sub.add_parser("dump", help="读 vault 内一个文件")
    p_dump.add_argument("path", help="相对 vault 根的路径")

    # help
    sub.add_parser("help", help="帮助")

    # delegate (v1)
    p_del = sub.add_parser("delegate", help="派一个 sub 跑任务")
    p_del.add_argument("task", help="sub 要完成的任务")
    p_del.add_argument("--sub-id", default=None, help="sub id(默认 uuid)")
    p_del.add_argument(
        "--provider", default="auto",
        choices=["auto", "minimax", "mock"],
        help="LLM provider(默认 auto:有 key 用 minimax,否则 mock)",
    )

    # pending (v1)
    sub.add_parser("pending", help="列待审 sub 产出")

    # approve (v1)
    p_app = sub.add_parser("approve", help="批准 sub 产出")
    p_app.add_argument("rel", help="sub 产出相对 vault 的路径")
    p_app.add_argument("--target", default=None, help="合并到的目标路径")

    # discard (v1)
    p_dis = sub.add_parser("discard", help="丢弃 sub 产出")
    p_dis.add_argument("rel", help="sub 产出相对 vault 的路径")

    return parser


COMMANDS = {
    "list": cmd_list,
    "whoami": cmd_whoami,
    "dump": cmd_dump,
    "help": cmd_help,
    "delegate": cmd_delegate,
    "pending": cmd_pending,
    "approve": cmd_approve,
    "discard": cmd_discard,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    handler = COMMANDS[args.command]
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
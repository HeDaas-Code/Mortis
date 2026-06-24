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


def cmd_dream(args: argparse.Namespace) -> int:
    """手动触发梦境。--level light/medium/deep。

    issue #56: owner 可手动触发认知周期中的 DREAM 阶段。
    """
    master = _build_master(args.vault, args.seed, args.provider)
    from mortis.dream import LightDreamer, MediumDreamer
    from mortis.dream.deep import DeepDreamer

    if args.level == "light":
        dreamer = LightDreamer(master.vault, master.provider)
    elif args.level == "medium":
        dreamer = MediumDreamer(master.vault, master.provider, k=args.k)
    else:
        dreamer = DeepDreamer(master.vault, master.provider, master.seed)

    result = dreamer.run()
    print(f"dream {args.level}: ok={result.ok}, phases={len(result.traces)}")
    if not result.ok:
        for t in result.traces:
            if not t.ok:
                err = t.detail.get("error", "failed")
                print(f"  {t.phase}: {err}")
        return 1
    return 0


def cmd_reflect(args: argparse.Namespace) -> int:
    """手动触发反思。

    issue #56: owner 可手动触发认知周期中的 REFLECT 阶段。
    --sessions 显式传 session 文件名;不传则扫最近一天的 sessions。
    """
    master = _build_master(args.vault, args.seed, args.provider)
    from mortis.reflect import ReflectExecutor

    executor = ReflectExecutor(master.vault, master.provider, mortis_name="Mortis")

    if args.sessions:
        # 显式传 session 路径 — 不传 sessions_dir,executor 走默认
        # (vault.root / mortis-journal / sessions),rel 可含日期子目录
        session_paths = args.sessions
        sessions_dir = None
    else:
        # 扫最近一天的 sessions
        root_sessions = master.vault.root / "mortis-journal" / "sessions"
        if not root_sessions.exists():
            print("no sessions found")
            return 1
        date_dirs = sorted(d for d in root_sessions.iterdir() if d.is_dir())
        if not date_dirs:
            print("no session dates found")
            return 1
        latest = date_dirs[-1]
        session_paths = [f.name for f in latest.glob("*.json")]
        if not session_paths:
            print(f"no sessions in {latest.name}")
            return 1
        sessions_dir = latest

    reflection = executor.run(session_paths, sessions_dir=sessions_dir)
    print(f"reflect: id={reflection.id}, valence={reflection.valence:.2f}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """查看当前状态：clock phase + unease + pending counts。

    issue #56: owner 视角的状态总览。owner 可以读 unease(不是 Mortis agent 视角)。
    """
    from mortis.clock import LogicalClock
    from mortis.steiner import load_unease
    from mortis.vault import Vault

    vault = Vault(args.vault)
    clock = LogicalClock()
    state = clock.state()
    print(f"phase: {state.value}")

    # unease (owner 视角 — 可以读隐藏层)
    try:
        unease = load_unease(vault)
        print(f"unease max: {unease.max_unease():.2f}")
        for dim, val in unease.per_dimension.items():
            if val > 0:
                print(f"  {dim.value}: {val:.2f}")
    except Exception:
        print("unease: (unavailable)")

    # pending reflections
    from mortis.reflect import list_pending_reflections

    pending = list_pending_reflections(vault)
    print(f"pending reflections: {len(pending)}")

    # growth count
    growths = vault.list_growths()
    print(f"growths: {len(growths)}")
    return 0


def cmd_daemon(args: argparse.Namespace) -> int:
    """启动 daemon 模式。

    issue #60: Mortis 作为常驻进程运行，按 clock phase 自动触发
    reflect/dream/erode。阻塞直到 SIGINT/SIGTERM。
    """
    from mortis.cli.daemon import MortisDaemon

    daemon = MortisDaemon(
        vault_path=args.vault,
        provider_kind=args.provider,
        seed_path=args.seed,
    )
    daemon.run()  # 阻塞
    return 0


def cmd_goodnight(args: argparse.Namespace) -> int:
    """owner「晚安」— 执行完整夜间认知周期。

    issue #61: owner 主动触发 REFLECT → DREAM_LIGHT → (可选 DREAM_DEEP) → ERODE。
    """
    from mortis.cli.goodnight import run_goodnight
    results = run_goodnight(
        vault_path=args.vault,
        provider_kind=args.provider,
        seed_path=args.seed,
        deep=args.deep,
    )
    for phase, ok in results.items():
        status = "✓" if ok else "✗"
        print(f"  {phase}: {status}")
    return 0 if all(results.values()) else 1


def cmd_web(args: argparse.Namespace) -> int:
    """启动 Web UI server。

    issue #52: owner 视角的 HTTP 浏览接口 (growth / dream / unease / notifications)。
    阻塞直到 Ctrl-C (KeyboardInterrupt)。
    """
    from mortis.web.server import start_web_server
    server = start_web_server(vault_path=str(args.vault), port=args.port)
    print(f"Web UI: http://localhost:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
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

    # dream (issue #56: 手动触发梦境)
    p_dream = sub.add_parser("dream", help="手动触发梦境")
    p_dream.add_argument(
        "--level", default="light", choices=["light", "medium", "deep"],
        help="梦境级别（default: light）",
    )
    p_dream.add_argument("--k", type=int, default=4, help="Medium dream k 值")
    p_dream.add_argument("--vault", default="vault", help="vault 根目录")
    p_dream.add_argument("--seed", default="seed.md", help="seed 文件路径")
    p_dream.add_argument(
        "--provider", default="auto", choices=["auto", "minimax", "mock"],
        help="LLM provider（default: auto）",
    )

    # reflect (issue #56: 手动触发反思)
    p_reflect = sub.add_parser("reflect", help="手动触发反思")
    p_reflect.add_argument(
        "--sessions", nargs="*", help="session 文件名(默认扫最近)",
    )
    p_reflect.add_argument("--vault", default="vault", help="vault 根目录")
    p_reflect.add_argument("--seed", default="seed.md", help="seed 文件路径")
    p_reflect.add_argument(
        "--provider", default="auto", choices=["auto", "minimax", "mock"],
        help="LLM provider（default: auto）",
    )

    # status (issue #56: 查看当前状态)
    p_status = sub.add_parser("status", help="查看当前状态")
    p_status.add_argument("--vault", default="vault", help="vault 根目录")

    # daemon (issue #60: 常驻进程模式)
    p_daemon = sub.add_parser("daemon", help="启动 daemon 常驻进程")
    p_daemon.add_argument("--vault", default="vault", help="vault 根目录")
    p_daemon.add_argument("--seed", default="seed.md", help="seed 文件路径")
    p_daemon.add_argument(
        "--provider", default="auto", choices=["auto", "minimax", "mock"],
        help="LLM provider（default: auto）",
    )

    # goodnight (issue #61: owner「晚安」触发完整夜间认知周期)
    p_goodnight = sub.add_parser(
        "goodnight", help="owner「晚安」— 执行完整夜间认知周期 (REFLECT→DREAM→ERODE)",
    )
    p_goodnight.add_argument(
        "--deep", action="store_true",
        help="执行深度梦境 (DREAM_DEEP + drift 检查)",
    )
    p_goodnight.add_argument("--vault", default="vault", help="vault 根目录")
    p_goodnight.add_argument("--seed", default="seed.md", help="seed 文件路径")
    p_goodnight.add_argument(
        "--provider", default="auto", choices=["auto", "minimax", "mock"],
        help="LLM provider（default: auto）",
    )

    # web (issue #52: Web UI server)
    p_web = sub.add_parser("web", help="启动 Web UI server (growth/dream/unease 浏览)")
    p_web.add_argument(
        "--port", type=int, default=8765,
        help="监听端口（default: 8765）",
    )
    p_web.add_argument("--vault", default="vault", help="vault 根目录")

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
    "dream": cmd_dream,
    "reflect": cmd_reflect,
    "status": cmd_status,
    "daemon": cmd_daemon,
    "goodnight": cmd_goodnight,
    "web": cmd_web,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    handler = COMMANDS[args.command]
    return handler(args)

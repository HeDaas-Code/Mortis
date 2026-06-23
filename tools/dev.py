#!/usr/bin/env python3
"""Mortis 开发 Harness — 开发自动化工具。

用法:
    python tools/dev.py claim <issue>      # 认领 issue + 建分支
    python tools/dev.py test               # 运行测试 (合并前检查)
    python tools/dev.py pr <issue>         # 创建 PR
    python tools/dev.py issues             # 查看 open issues
    python tools/dev.py cleanup <pr>       # 合并后清理分支
    python tools/dev.py status             # 当前开发状态
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO = "HeDaas-Code/Mortis"
REPO_DIR = Path(__file__).resolve().parent.parent


# ============================================================
# GitHub API
# ============================================================

def _gh_token() -> str:
    """从 ~/.gh_env 读取 GH_TOKEN。"""
    gh_env = Path.home() / ".gh_env"
    if gh_env.exists():
        for line in gh_env.read_text().splitlines():
            line = line.strip()
            if line.startswith("export GH_TOKEN=") or line.startswith("GH_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    # fallback: 环境变量
    return os.environ.get("GH_TOKEN", "")


def _gh_api(method: str, path: str, data: dict | None = None) -> dict:
    """调用 GitHub API。"""
    token = _gh_token()
    if not token:
        print("ERROR: GH_TOKEN not found. 请配置 ~/.gh_env", file=sys.stderr)
        sys.exit(1)
    url = f"https://api.github.com/repos/{REPO}/{path}"
    headers = {
        "Authorization": f"token {token}",
        "Content-Type": "application/json",
        "Accept": "application/vnd.github.v3+json",
    }
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"GitHub API error {e.code}: {e.read().decode()[:200]}", file=sys.stderr)
        sys.exit(1)


# ============================================================
# git 操作
# ============================================================

def _git(args: list[str]) -> str:
    """执行 git 命令, 返回 stdout。"""
    result = subprocess.run(
        ["git"] + args,
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"git {' '.join(args)} failed:", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def _current_branch() -> str:
    return _git(["rev-parse", "--abbrev-ref", "HEAD"])


def _ensure_main() -> None:
    """确保在 main 分支。"""
    branch = _current_branch()
    if branch != "main":
        print(f"ERROR: 当前在 {branch}, 请先切到 main", file=sys.stderr)
        sys.exit(1)


# ============================================================
# 命令: claim — 认领 issue + 建分支
# ============================================================

def cmd_claim(args: argparse.Namespace) -> int:
    """认领 issue + 建分支 + 改 label。"""
    issue_num = args.issue
    issue = _gh_api("GET", f"issues/{issue_num}")

    title = issue["title"]
    labels = [l["name"] for l in issue.get("labels", [])]

    # 检查是否已被认领
    if "status:in-progress" in labels:
        print(f"WARNING: #{issue_num} 已被认领 (status:in-progress)")
        if not args.force:
            print("使用 --force 强制认领")
            return 1

    # 确定分支名
    is_bug = "bug" in labels or "type:bug" in labels
    prefix = "fix" if is_bug else "feature"

    # 从 title 提取模块关键词作为分支后缀
    # 提取括号内的模块名, 如 "bug(toolagent): ..." → "toolagent"
    suffix = ""
    if "(" in title and ")" in title:
        suffix = title.split("(", 1)[1].split(")", 1)[0]
    if not suffix:
        # fallback: 取冒号前的英文词
        before_colon = title.split(":")[0] if ":" in title else title
        suffix = "".join(c for c in before_colon if c.isalpha() or c == "-").lower()
    if not suffix:
        suffix = f"issue-{issue_num}"
    # 限长 + 安全字符
    suffix = suffix[:30].strip("-")
    branch = f"{prefix}/{issue_num}-{suffix}"

    # 建分支
    _ensure_main()
    _git(["pull", "origin", "main"])
    _git(["checkout", "-b", branch])
    print(f"✓ 分支: {branch}")

    # 改 label
    new_labels = [l for l in labels if not l.startswith("status:")]
    new_labels.append("status:in-progress")
    _gh_api("PATCH", f"issues/{issue_num}", {"labels": new_labels})
    print(f"✓ label: status:in-progress")

    print(f"\n下一步:")
    print(f"  开发 → pytest → git push → python tools/dev.py pr {issue_num}")
    return 0


# ============================================================
# 命令: test — 运行测试
# ============================================================

def cmd_test(args: argparse.Namespace) -> int:
    """运行测试套件。"""
    cmd = ["python", "-m", "pytest"]
    if args.verbose:
        cmd.append("-v")
    if args.tb:
        cmd.extend(["--tb", args.tb])
    else:
        cmd.extend(["--tb", "short"])
    if args.module:
        cmd.append(f"tests/test_{args.module}.py")

    result = subprocess.run(cmd, cwd=REPO_DIR)
    if result.returncode == 0:
        print("\n✓ 全部通过")
    else:
        print("\n✗ 有失败", file=sys.stderr)
    return result.returncode


# ============================================================
# 命令: pr — 创建 PR
# ============================================================

def cmd_pr(args: argparse.Namespace) -> int:
    """推送当前分支 + 创建 PR。"""
    issue_num = args.issue
    branch = _current_branch()
    if branch == "main":
        print("ERROR: 在 main 分支, 请先切到工作分支", file=sys.stderr)
        return 1

    # 推送
    _git(["push", "-u", "origin", branch])
    print(f"✓ pushed: {branch}")

    # 获取 issue 信息
    issue = _gh_api("GET", f"issues/{issue_num}")
    issue_title = issue["title"]
    labels = [l["name"] for l in issue.get("labels", [])]
    is_bug = "bug" in labels or "type:bug" in labels
    prefix = "fix" if is_bug else "feat"

    # 构造 PR 标题
    pr_title = args.title or f"{prefix}: {issue_title} (#{issue_num})"

    # 构造 PR body
    pr_body = f"Closes #{issue_num}\n\n{args.body or ''}"

    # 创建 PR
    pr = _gh_api("POST", "pulls", {
        "title": pr_title,
        "body": pr_body,
        "head": branch,
        "base": "main",
    })
    print(f"✓ PR #{pr['number']}: {pr['title']}")
    print(f"  {pr['html_url']}")
    return 0


# ============================================================
# 命令: issues — 查看 open issues
# ============================================================

def cmd_issues(args: argparse.Namespace) -> int:
    """列出 open issues, 按里程碑分组。"""
    data = _gh_api("GET", "issues?state=open&per_page=100")

    # 过滤掉 PR
    issues = [i for i in data if "pull_request" not in i]

    # 按里程碑分组
    by_ms: dict[str, list] = {}
    for i in issues:
        ms = i.get("milestone")
        ms_title = ms["title"] if ms else "(无里程碑)"
        by_ms.setdefault(ms_title, []).append(i)

    for ms_title in sorted(by_ms.keys()):
        print(f"\n=== {ms_title} ===")
        for i in sorted(by_ms[ms_title], key=lambda x: x["number"]):
            labels = ", ".join(
                l["name"] for l in i.get("labels", [])
                if l["name"].startswith("priority:") or l["name"] == "bug"
            )
            state_marker = "🔄" if any(
                l["name"] == "status:in-progress"
                for l in i.get("labels", [])
            ) else "  "
            print(f"  {state_marker} #{i['number']:>2} | {labels:20s} | {i['title'][:60]}")

    return 0


# ============================================================
# 命令: cleanup — 合并后清理
# ============================================================

def cmd_cleanup(args: argparse.Namespace) -> int:
    """合并后: 切回 main + pull + 删分支。"""
    _ensure_main()
    _git(["pull", "origin", "main"])
    print("✓ main 已同步")

    # 删本地分支
    branches = _git(["branch"]).split("\n")
    for b in branches:
        b = b.strip().lstrip("*").strip()
        if b and b != "main":
            _git(["branch", "-D", b])
            print(f"✓ 删除本地分支: {b}")

    # 清理远程
    _git(["remote", "prune", "origin"])
    print("✓ 清理远程分支")
    return 0


# ============================================================
# 命令: status — 当前开发状态
# ============================================================

def cmd_status(args: argparse.Namespace) -> int:
    """显示当前开发状态: 分支 + 测试数 + 最近 commit。"""
    branch = _current_branch()
    print(f"分支: {branch}")

    # 最近 5 个 commit
    log = _git(["log", "--oneline", "-5"])
    print(f"\n最近 commit:")
    for line in log.split("\n"):
        print(f"  {line}")

    # 测试数量
    result = subprocess.run(
        ["python", "-m", "pytest", "--co", "-q"],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        last_line = result.stdout.strip().split("\n")[-1]
        print(f"\n测试: {last_line}")

    # 当前 issue 状态
    if args.issue:
        issue = _gh_api("GET", f"issues/{args.issue}")
        labels = [l["name"] for l in issue.get("labels", [])]
        print(f"\nIssue #{args.issue}: {issue['title']}")
        print(f"  state: {issue['state']}, labels: {labels}")

    return 0


# ============================================================
# main
# ============================================================

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Mortis 开发 Harness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command")

    # claim
    p_claim = sub.add_parser("claim", help="认领 issue + 建分支")
    p_claim.add_argument("issue", type=int, help="issue 编号")
    p_claim.add_argument("--force", action="store_true", help="强制认领 (即使已被认领)")
    p_claim.set_defaults(func=cmd_claim)

    # test
    p_test = sub.add_parser("test", help="运行测试")
    p_test.add_argument("-v", "--verbose", action="store_true")
    p_test.add_argument("--tb", choices=["short", "long", "line", "no"], help="traceback 格式")
    p_test.add_argument("--module", help="只测某个模块 (如 growth_model)")
    p_test.set_defaults(func=cmd_test)

    # pr
    p_pr = sub.add_parser("pr", help="推送分支 + 创建 PR")
    p_pr.add_argument("issue", type=int, help="issue 编号")
    p_pr.add_argument("--title", help="PR 标题 (默认从 issue 生成)")
    p_pr.add_argument("--body", help="PR body 补充")
    p_pr.set_defaults(func=cmd_pr)

    # issues
    p_issues = sub.add_parser("issues", help="查看 open issues")
    p_issues.set_defaults(func=cmd_issues)

    # cleanup
    p_cleanup = sub.add_parser("cleanup", help="合并后清理分支")
    p_cleanup.set_defaults(func=cmd_cleanup)

    # status
    p_status = sub.add_parser("status", help="当前开发状态")
    p_status.add_argument("--issue", type=int, help="查看某个 issue 状态")
    p_status.set_defaults(func=cmd_status)

    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

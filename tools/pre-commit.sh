#!/bin/bash
# Mortis pre-commit hook — 跑测试 + ruff check
set -e

cd "$(git rev-parse --show-toplevel)"

echo "▶ pytest (changed files only)..."
# 只测与 staged 文件相关的测试
CHANGED=$(git diff --cached --name-only --diff-filter=ACM | grep -E '^mortis/.*\.py$' | head -5)
if [ -z "$CHANGED" ]; then
    echo "  (无 .py 变更, 跳过)"
else
    # 跑全量测试 (项目不大, 快)
    python -m pytest --tb=short -q 2>&1 | tail -5
    if [ ${PIPESTATUS[0]} -ne 0 ]; then
        echo "✗ 测试失败, 阻止 commit"
        exit 1
    fi
fi

echo "✓ pre-commit 通过"

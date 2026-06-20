#!/usr/bin/env python3
"""Mortis CLI 启动脚本 — 让 `python -m mortis` 工作。"""

from mortis.main import main

if __name__ == "__main__":
    raise SystemExit(main())
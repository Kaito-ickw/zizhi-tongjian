#!/usr/bin/env python3
"""TASKS.md の最初の未完了タスクを表示する(再開プロトコル用)。

使い方:
  python3 pipeline/task.py next   # 次の未完了 [ ] タスクブロックを表示
  python3 pipeline/task.py list   # 全タスクの状態一覧
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

TASKS = Path(__file__).resolve().parent.parent / "TASKS.md"
HEAD = re.compile(r"^##\s*\[( |x)\]\s*(.+)$")


def blocks():
    lines = TASKS.read_text(encoding="utf-8").splitlines()
    cur = None
    for ln in lines:
        m = HEAD.match(ln)
        if m:
            if cur:
                yield cur
            cur = {"done": m.group(1) == "x", "title": m.group(2).strip(), "lines": [ln]}
        elif cur is not None:
            cur["lines"].append(ln)
    if cur:
        yield cur


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "next"
    bs = list(blocks())
    if cmd == "list":
        for b in bs:
            print(f"[{'x' if b['done'] else ' '}] {b['title']}")
        return 0
    # next
    for b in bs:
        if not b["done"]:
            print("\n".join(b["lines"]).rstrip())
            return 0
    print("全タスク完了。新規タスクは TASKS.md に追記してください。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

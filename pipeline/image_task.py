#!/usr/bin/env python3
"""IMAGES.md の最初の未完了画像タスクを表示する(画像再開プロトコル用)。

使い方:
  python3 pipeline/image_task.py next   # 次の未完了 [ ] タスクブロックを表示
  python3 pipeline/image_task.py list   # 全画像タスクの状態一覧
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

IMAGES = Path(__file__).resolve().parent.parent / "IMAGES.md"
HEAD = re.compile(r"^##\s*\[( |x)\]\s*(.+)$")


def blocks():
    lines = IMAGES.read_text(encoding="utf-8").splitlines()
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
    print("全画像タスク完了。新規タスクは IMAGES.md に追記してください。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""画像再開プロトコル用のタスクと未挿絵 frontier を表示する。

使い方:
  python3 pipeline/image_task.py next   # 次の未完了 [ ] タスクブロックを表示
  python3 pipeline/image_task.py list   # 全画像タスクの状態一覧
  python3 pipeline/image_task.py frontier [--limit N] [--min-chars N]  # 未挿絵の先頭 N 年
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMAGES = ROOT / "IMAGES.md"
KB = ROOT / "data" / "kb"
HEAD = re.compile(r"^##\s*\[( |x)\]\s*(.+)$")
RECORD_PATH = re.compile(r"^卷(\d{3})/j(\d{3})_(y\d{2})\.json$")


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


def frontier(limit: int, min_chars: int) -> int:
    # 数十字しかない年(「秦が魏を伐った」だけ等)に挿絵を割り当てても絵にならないので、
    # 既定では本文が min_chars 未満の年を frontier から外す。--min-chars 0 で無効化。
    records = []
    for path in KB.glob("卷[0-9][0-9][0-9]/j[0-9][0-9][0-9]_y[0-9][0-9].json"):
        relative = path.relative_to(KB)
        match = RECORD_PATH.fullmatch(relative.as_posix())
        if match:
            records.append((int(match.group(1)), int(match.group(3)[1:]), path))
    records.sort(key=lambda item: (item[0], item[1]))

    total = 0
    illustrated = 0
    image_count = 0
    skipped_short = 0
    pending = []
    for juan, _, path in records:
        record = json.loads(path.read_text(encoding="utf-8"))
        illustrations = record.get("illustrations") or []
        total += 1
        if illustrations:
            illustrated += 1
            image_count += len(illustrations)
        elif len(record.get("translation_full") or "") < min_chars:
            skipped_short += 1
        else:
            pending.append((juan, path, record))

    for index, (juan, path, record) in enumerate(pending[:limit]):
        if index:
            print()
        print(f"レコードID: {record.get('id', path.stem)}")
        print(f"ファイルパス: {path.relative_to(ROOT)}")
        print(f"巻: {juan}")
        print(f"年キー: {path.stem.rsplit('_', 1)[-1]}")
        print(f"ruler: {record.get('ruler')}")
        print(f"year_label: {record.get('year_label')}")
        print(f"western_year: {record.get('western_year')}")
        print(f"translation_full文字数: {len(record.get('translation_full') or '')}")

    if not pending:
        print("未挿絵のレコードはありません。")
    print(
        f"カバレッジ: 総レコード数={total} "
        f"挿絵登録済みレコード数={illustrated} 登録画像総枚数={image_count} "
        f"短文スキップ={skipped_short}(本文<{min_chars}字)"
    )
    return 0


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "next"
    if cmd == "frontier":
        parser = argparse.ArgumentParser(prog="image_task.py frontier")
        parser.add_argument("--limit", type=int, default=1)
        parser.add_argument("--min-chars", type=int, default=800)
        args = parser.parse_args(sys.argv[2:])
        if args.limit < 1:
            parser.error("--limit は1以上を指定してください")
        if args.min_chars < 0:
            parser.error("--min-chars は0以上を指定してください")
        return frontier(args.limit, args.min_chars)

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

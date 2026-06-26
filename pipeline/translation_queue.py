#!/usr/bin/env python3
"""Find the next translation batch from staging records and pass KB state.

This is the translation track's source of truth. It intentionally ignores
maintenance tasks in TASKS.md so a Claude translation session can start from a
concrete batch without spending context on triage.

Examples:
  python3 pipeline/translation_queue.py next
  python3 pipeline/translation_queue.py next --json
  python3 pipeline/translation_queue.py list --limit 5
  python3 pipeline/translation_queue.py check
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
STAGING_DIR = ROOT / "data" / "staging" / "kb"
KB_DIR = ROOT / "data" / "kb"

BATCH_CHAR_LIMIT = 3200
BATCH_YEAR_LIMIT = 10
VOLUME_RE = re.compile(r"^卷(\d{3})\.json$")
YEAR_RE = re.compile(r"^j(\d{3})_y(\d{2})$")


class QueueError(Exception):
    """Input or state error shown without a traceback."""


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QueueError(f"failed to read {path}: {exc}") from exc


def pass_record_path(year_id: str) -> Path:
    match = YEAR_RE.fullmatch(year_id)
    if match is None:
        raise QueueError(f"invalid year id: {year_id!r}")
    juan = int(match.group(1))
    return KB_DIR / f"卷{juan:03d}" / f"{year_id}.json"


def is_pass(year_id: str) -> bool:
    path = pass_record_path(year_id)
    if not path.exists():
        return False
    data = load_json(path)
    return isinstance(data, dict) and data.get("status") == "pass"


def year_weight(year: dict[str, Any]) -> int:
    """Approximate translation/review load using source text plus notes."""
    chunk_chars = sum(len(chunk.get("text", "")) for chunk in year.get("chunks", []))
    note_chars = sum(len(note.get("text", "")) for note in year.get("notes", []))
    return chunk_chars + note_chars


def year_summary(year: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": year["id"],
        "year_label": year.get("year_label"),
        "ruler": year.get("ruler"),
        "chunks": len(year.get("chunks", [])),
        "source_note_chars": year_weight(year),
        "first_chunk": year.get("chunks", [{}])[0].get("chunk_id"),
        "target": str(pass_record_path(year["id"]).relative_to(ROOT)),
    }


def iter_volumes() -> list[tuple[int, Path, dict[str, Any]]]:
    volumes: list[tuple[int, Path, dict[str, Any]]] = []
    for path in sorted(STAGING_DIR.glob("卷*.json")):
        match = VOLUME_RE.fullmatch(path.name)
        if match is None:
            continue
        juan = int(match.group(1))
        data = load_json(path)
        if not isinstance(data, dict) or not isinstance(data.get("year_records"), list):
            raise QueueError(f"{path}: missing year_records array")
        volumes.append((juan, path, data))
    return volumes


def first_incomplete_volume() -> dict[str, Any] | None:
    for juan, path, volume in iter_volumes():
        years = volume["year_records"]
        done = [year for year in years if is_pass(year["id"])]
        if len(done) < len(years):
            return {
                "juan": juan,
                "path": path,
                "volume": volume,
                "done_count": len(done),
                "total_count": len(years),
            }
    return None


def build_batch(years: list[dict[str, Any]], start_index: int) -> list[dict[str, Any]]:
    """Greedy batch from start_index using the established T05 split rule."""
    batch: list[dict[str, Any]] = []
    total = 0
    for year in years[start_index:]:
        if is_pass(year["id"]):
            break
        weight = year_weight(year)
        if batch and (len(batch) >= BATCH_YEAR_LIMIT or total + weight > BATCH_CHAR_LIMIT):
            break
        batch.append(year)
        total += weight
        if weight > BATCH_CHAR_LIMIT:
            break
    return batch


def previous_year_id(juan: int, year_index: int) -> str | None:
    """Return the immediate previous staging year id, crossing volume boundary."""
    if year_index > 1:
        return f"j{juan:03d}_y{year_index - 1:02d}"
    prev_path = STAGING_DIR / f"卷{juan - 1:03d}.json"
    if juan <= 1 or not prev_path.exists():
        return None
    prev_volume = load_json(prev_path)
    years = prev_volume.get("year_records", [])
    if not years:
        return None
    return years[-1]["id"]


def next_batch() -> dict[str, Any] | None:
    incomplete = first_incomplete_volume()
    if incomplete is None:
        return None

    juan = incomplete["juan"]
    volume = incomplete["volume"]
    years = volume["year_records"]
    start_index = next(i for i, year in enumerate(years) if not is_pass(year["id"]))
    batch = build_batch(years, start_index)
    previous_id = previous_year_id(juan, start_index + 1)

    return {
        "juan": juan,
        "volume_dir": f"卷{juan:03d}",
        "section": volume.get("section"),
        "western_range": f"{volume.get('western_start')} to {volume.get('western_end')}",
        "done_count": incomplete["done_count"],
        "total_count": incomplete["total_count"],
        "batch_start": batch[0]["id"],
        "batch_end": batch[-1]["id"],
        "batch_years": [year_summary(year) for year in batch],
        "batch_year_count": len(batch),
        "batch_chunk_count": sum(len(year.get("chunks", [])) for year in batch),
        "batch_source_note_chars": sum(year_weight(year) for year in batch),
        "previous_year_id": previous_id,
        "previous_year_path": (
            str(pass_record_path(previous_id).relative_to(ROOT)) if previous_id else None
        ),
    }


def queue_list(limit: int | None = None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for juan, _path, volume in iter_volumes():
        years = volume["year_records"]
        done_count = sum(1 for year in years if is_pass(year["id"]))
        if done_count == len(years):
            continue
        pending = [year for year in years if not is_pass(year["id"])]
        items.append({
            "juan": juan,
            "volume_dir": f"卷{juan:03d}",
            "section": volume.get("section"),
            "done_count": done_count,
            "total_count": len(years),
            "pending_count": len(pending),
            "pending_chunks": sum(len(year.get("chunks", [])) for year in pending),
            "pending_source_note_chars": sum(year_weight(year) for year in pending),
            "first_pending": pending[0]["id"],
            "last_pending": pending[-1]["id"],
        })
        if limit is not None and len(items) >= limit:
            break
    return items


def git_status_short() -> list[str]:
    proc = subprocess.run(
        ["git", "status", "--short"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise QueueError((proc.stderr or proc.stdout).strip() or "git status failed")
    return [line for line in proc.stdout.splitlines() if line.strip()]


def check_next() -> dict[str, Any]:
    batch = next_batch()
    if batch is None:
        return {"ok": True, "checks": [], "batch": None}

    checks: list[dict[str, Any]] = []

    previous = batch["previous_year_id"]
    if previous is None:
        checks.append({"name": "previous_year", "ok": True, "detail": "volume starts at corpus head"})
    else:
        prev_path = pass_record_path(previous)
        checks.append({
            "name": "previous_year",
            "ok": is_pass(previous),
            "detail": str(prev_path.relative_to(ROOT)),
        })

    target_conflicts = [
        year["target"] for year in batch["batch_years"]
        if pass_record_path(year["id"]).exists()
    ]
    checks.append({
        "name": "target_outputs_absent",
        "ok": not target_conflicts,
        "detail": ", ".join(target_conflicts) if target_conflicts else "no target files exist",
    })

    dirty = git_status_short()
    checks.append({
        "name": "worktree_clean_for_translation",
        "ok": not dirty,
        "detail": "clean" if not dirty else "; ".join(dirty),
    })

    return {
        "ok": all(item["ok"] for item in checks),
        "checks": checks,
        "batch": batch,
    }


def print_next(batch: dict[str, Any] | None) -> None:
    if batch is None:
        print("All staging years have pass KB records.")
        return
    print(f"Next translation batch: {batch['volume_dir']} {batch.get('section') or ''}".rstrip())
    print(f"Progress: {batch['done_count']} / {batch['total_count']} years pass")
    print(
        f"Batch: {batch['batch_start']} - {batch['batch_end']} "
        f"({batch['batch_year_count']} years, {batch['batch_chunk_count']} chunks, "
        f"{batch['batch_source_note_chars']} source+note chars)"
    )
    if batch["previous_year_id"]:
        print(f"Continuity source: {batch['previous_year_path']}")
    else:
        print("Continuity source: none")
    print("Years:")
    for year in batch["batch_years"]:
        print(
            f"  - {year['id']} {year.get('ruler') or ''}{year.get('year_label') or ''}: "
            f"{year['chunks']} chunks, {year['source_note_chars']} chars, first={year['first_chunk']}"
        )


def print_list(items: list[dict[str, Any]]) -> None:
    if not items:
        print("All staging years have pass KB records.")
        return
    for item in items:
        print(
            f"{item['volume_dir']} {item.get('section') or ''}: "
            f"{item['done_count']}/{item['total_count']} years pass, "
            f"pending {item['first_pending']}-{item['last_pending']} "
            f"({item['pending_chunks']} chunks, {item['pending_source_note_chars']} chars)"
        )


def print_check(result: dict[str, Any]) -> None:
    print_next(result["batch"])
    print("Checks:")
    for check in result["checks"]:
        mark = "OK" if check["ok"] else "FAIL"
        print(f"  [{mark}] {check['name']}: {check['detail']}")
    if not result["ok"]:
        raise SystemExit(2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd")

    p_next = sub.add_parser("next")
    p_next.add_argument("--json", action="store_true", help="emit JSON")

    p_list = sub.add_parser("list")
    p_list.add_argument("--limit", type=int, default=None)
    p_list.add_argument("--json", action="store_true", help="emit JSON")

    p_check = sub.add_parser("check")
    p_check.add_argument("--json", action="store_true", help="emit JSON")

    args = parser.parse_args()
    cmd = args.cmd or "next"
    try:
        if cmd == "next":
            batch = next_batch()
            if args.json:
                print(json.dumps(batch, ensure_ascii=False, indent=2))
            else:
                print_next(batch)
            return 0
        if cmd == "list":
            items = queue_list(args.limit)
            if args.json:
                print(json.dumps(items, ensure_ascii=False, indent=2))
            else:
                print_list(items)
            return 0
        if cmd == "check":
            result = check_next()
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 0 if result["ok"] else 2
            print_check(result)
            return 0
    except QueueError as exc:
        print(f"translation_queue: {exc}", file=sys.stderr)
        return 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

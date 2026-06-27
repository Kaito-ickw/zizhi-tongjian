#!/usr/bin/env python3
"""Merge translated KB records into volume-level Markdown for NotebookLM."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
KB_DIR = ROOT / "data" / "kb"
OUT_DIR = ROOT / "data" / "notebooklm"
TOTAL_VOLUMES = 294

VOLUME_DIR_RE = re.compile(r"卷(?P<juan>\d{3})$")
RECORD_ID_RE = re.compile(r"j(?P<juan>\d{3})_y(?P<year>\d{2})$")


class ExportError(Exception):
    """An input or CLI error that should be shown without a traceback."""


@dataclass(frozen=True)
class ExportRecord:
    path: Path
    id: str
    juan: int
    section: str
    ruler: str
    year_label: str
    era: str | None
    western_year: str | int | None
    western_volume_range: str
    translation_full: str
    license_note: str
    built_with: dict[str, Any] | None


def eprint(message: str) -> None:
    print(message, file=sys.stderr)


def discover_volumes() -> list[int]:
    volumes: list[int] = []
    for path in sorted(KB_DIR.iterdir()):
        if not path.is_dir():
            continue
        match = VOLUME_DIR_RE.fullmatch(path.name)
        if match:
            volumes.append(int(match.group("juan")))
    return volumes


def parse_selector(selector: str, available: list[int]) -> set[int]:
    if not available:
        raise ExportError(f"no volume directories found under {KB_DIR.relative_to(ROOT)}")

    first_volume = min(available)
    last_volume = max(available)

    if selector.isdecimal():
        volume = int(selector)
        return {volume}

    if "-" in selector:
        start_text, end_text = selector.split("-", 1)
        if "-" in end_text:
            raise ExportError(f"invalid volume selector: {selector!r}")
        if start_text and not start_text.isdecimal():
            raise ExportError(f"invalid volume selector: {selector!r}")
        if end_text and not end_text.isdecimal():
            raise ExportError(f"invalid volume selector: {selector!r}")
        if not start_text and not end_text:
            raise ExportError(f"invalid volume selector: {selector!r}")

        start = int(start_text) if start_text else first_volume
        end = int(end_text) if end_text else last_volume
        if start > end:
            raise ExportError(f"invalid descending volume range: {selector!r}")
        return set(range(start, end + 1))

    raise ExportError(f"invalid volume selector: {selector!r}")


def selected_volumes(selectors: Iterable[str], all_volumes: bool) -> list[int]:
    available = discover_volumes()
    available_set = set(available)

    if all_volumes:
        selected = set(available)
    else:
        selected: set[int] = set()
        for selector in selectors:
            selected.update(parse_selector(selector, available))

    if not selected:
        raise ExportError("specify one or more volumes, ranges, or --all")

    missing = sorted(selected - available_set)
    if missing:
        missing_text = ", ".join(f"卷{volume:03d}" for volume in missing)
        raise ExportError(f"requested volume does not exist: {missing_text}")

    return sorted(selected)


def year_name(record: ExportRecord) -> str:
    return f"{record.ruler}{record.era or ''}{record.year_label}"


def western_label(value: str | int | None) -> str:
    return "未確定" if value is None else str(value)


def as_str(value: Any, key: str, path: Path) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    eprint(f"skip {path.relative_to(ROOT)}: {key} is missing or not a non-empty string")
    return None


def as_optional_era(value: Any, path: Path) -> str | None:
    if value is None or isinstance(value, str):
        return value
    eprint(f"skip {path.relative_to(ROOT)}: era must be string or null")
    return None


def as_western_year(value: Any, path: Path) -> str | int | None:
    if value is None:
        return None
    if isinstance(value, (str, int)) and not isinstance(value, bool):
        return value
    eprint(f"skip {path.relative_to(ROOT)}: western_year must be string, integer, or null")
    return None


def load_record(path: Path, expected_juan: int) -> ExportRecord | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        eprint(f"skip {path.relative_to(ROOT)}: failed to read JSON: {exc}")
        return None

    if not isinstance(raw, dict):
        eprint(f"skip {path.relative_to(ROOT)}: record is not a JSON object")
        return None

    status = raw.get("status")
    if status != "pass":
        halt_reason = raw.get("halt_reason")
        reason = f"status={status!r}"
        if halt_reason:
            reason += f", halt_reason={halt_reason!r}"
        eprint(f"skip {path.relative_to(ROOT)}: {reason}")
        return None

    record_id = as_str(raw.get("id"), "id", path)
    if record_id is None:
        return None
    match = RECORD_ID_RE.fullmatch(record_id)
    if match is None:
        eprint(f"skip {path.relative_to(ROOT)}: invalid id {record_id!r}")
        return None

    juan = raw.get("juan")
    if not isinstance(juan, int) or isinstance(juan, bool):
        eprint(f"skip {path.relative_to(ROOT)}: juan must be an integer")
        return None
    if juan != expected_juan or int(match.group("juan")) != juan:
        eprint(
            f"skip {path.relative_to(ROOT)}: id/path juan mismatch "
            f"(id={record_id!r}, juan={juan}, dir=卷{expected_juan:03d})"
        )
        return None

    section = as_str(raw.get("section"), "section", path)
    ruler = as_str(raw.get("ruler"), "ruler", path)
    year_label = as_str(raw.get("year_label"), "year_label", path)
    western_volume_range = as_str(
        raw.get("western_volume_range"), "western_volume_range", path
    )
    translation_full = as_str(raw.get("translation_full"), "translation_full", path)
    license_note = as_str(raw.get("license_note"), "license_note", path)
    if None in (
        section,
        ruler,
        year_label,
        western_volume_range,
        translation_full,
        license_note,
    ):
        return None

    era = as_optional_era(raw.get("era"), path)
    western_year = as_western_year(raw.get("western_year"), path)
    built_with = raw.get("built_with")
    if built_with is not None and not isinstance(built_with, dict):
        eprint(f"skip {path.relative_to(ROOT)}: built_with must be an object when present")
        return None

    return ExportRecord(
        path=path,
        id=record_id,
        juan=juan,
        section=section,
        ruler=ruler,
        year_label=year_label,
        era=era,
        western_year=western_year,
        western_volume_range=western_volume_range,
        translation_full=translation_full.strip(),
        license_note=license_note,
        built_with=built_with,
    )


def load_volume(juan: int) -> tuple[list[ExportRecord], int]:
    volume_dir = KB_DIR / f"卷{juan:03d}"
    paths = sorted(volume_dir.glob(f"j{juan:03d}_y*.json"))
    records = [
        record
        for path in paths
        if (record := load_record(path, expected_juan=juan)) is not None
    ]
    return sorted(records, key=lambda record: record.id), len(paths) - len(records)


def metadata_lines(record: ExportRecord) -> list[str]:
    lines = [
        f"- ID: {record.id}",
        f"- 巻: 卷{record.juan:03d}",
        f"- 篇: {record.section}",
        f"- 年号: {year_name(record)}",
        f"- 西暦: {western_label(record.western_year)}",
        f"- ライセンス: {record.license_note}",
    ]
    if record.built_with:
        translator = record.built_with.get("translator")
        reviewer = record.built_with.get("reviewer")
        if translator:
            lines.append(f"- 翻訳: {translator}")
        if reviewer:
            lines.append(f"- レビュー: {reviewer}")
    return lines


def render_volume(records: list[ExportRecord]) -> str:
    first = records[0]
    last = records[-1]
    header = (
        f"# 卷{first.juan:03d} {first.section}\n\n"
        "NotebookLM投入用に `data/kb/` の確定訳を巻単位で結合したMarkdown。\n"
        f"対象: {year_name(first)} 〜 {year_name(last)} / {len(records)} 年\n"
        f"西暦(巻範囲): {first.western_volume_range}\n\n"
        "---\n"
    )

    sections: list[str] = [header]
    for record in records:
        sections.append(
            "\n"
            f"## {record.id} {year_name(record)} ({western_label(record.western_year)})\n\n"
            f"{record.translation_full}\n\n"
            "### メタ情報\n\n"
            + "\n".join(metadata_lines(record))
            + "\n\n---\n"
        )
    return "".join(sections)


def output_path(juan: int) -> Path:
    return OUT_DIR / f"zizhi-tongjian-vol{juan:03d}.md"


def write_volume(juan: int) -> tuple[Path | None, int, int]:
    records, skipped = load_volume(juan)
    out_path = output_path(juan)

    if not records:
        if out_path.exists():
            out_path.unlink()
            eprint(f"removed stale output {out_path.relative_to(ROOT)}: no pass records")
        eprint(f"skip 卷{juan:03d}: no pass records to export")
        return None, 0, skipped

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_volume(records), encoding="utf-8")
    return out_path, len(records), skipped


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  python3 pipeline/merge_for_notebooklm.py 1
  python3 pipeline/merge_for_notebooklm.py 1 5 10
  python3 pipeline/merge_for_notebooklm.py 1-5
  python3 pipeline/merge_for_notebooklm.py -5
  python3 pipeline/merge_for_notebooklm.py 5-
  python3 pipeline/merge_for_notebooklm.py --all
""",
    )
    parser.add_argument(
        "selectors",
        nargs="*",
        help="volume selectors: N, N-M, -M, M-; may be combined",
    )
    parser.add_argument("--all", action="store_true", help="export all existing volumes")
    args = parser.parse_args(argv)
    if args.all and args.selectors:
        parser.error("use either --all or explicit selectors, not both")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        volumes = selected_volumes(args.selectors, args.all)
        written = 0
        total_records = 0
        total_skipped = 0
        for juan in volumes:
            path, records, skipped = write_volume(juan)
            total_records += records
            total_skipped += skipped
            if path is not None:
                written += 1
                print(
                    f"wrote {path.relative_to(ROOT)} "
                    f"(records={records}, skipped={skipped})"
                )
        print(f"volumes selected: {len(volumes)}")
        print(f"files written: {written}")
        print(f"records exported: {total_records}")
        print(f"records skipped: {total_skipped}")
        print(f"out -> {OUT_DIR.relative_to(ROOT)}/")
    except (ExportError, OSError) as exc:
        print(f"merge_for_notebooklm.py: error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

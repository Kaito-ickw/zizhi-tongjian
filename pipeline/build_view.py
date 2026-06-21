#!/usr/bin/env python3
"""Generate the disposable Markdown view in docs/ from data/kb/."""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
KB_DIR = ROOT / "data" / "kb"
DOCS_DIR = ROOT / "docs"
TOTAL_VOLUMES = 294

RECORD_ID_RE = re.compile(r"j(?P<juan>\d{3})_y\d{2}")
NOTE_ANCHOR_RE = re.compile(r"⟦[^⟧]*⟧")
LEADING_COLON_RE = re.compile(r"^:+", re.MULTILINE)
CIRCLED_NUMBER_RE = re.compile(r"[①-⑳]")
EXCESS_BLANK_LINES_RE = re.compile(r"\n[ \t]*\n(?:[ \t]*\n)+")


class BuildError(Exception):
    """An input error that should be shown without a traceback."""


def require(record: dict[str, Any], key: str, expected_type: type, path: Path) -> Any:
    value = record.get(key)
    if not isinstance(value, expected_type) or (
        expected_type is int and isinstance(value, bool)
    ):
        raise BuildError(f"{path}: {key!r} must be {expected_type.__name__}")
    return value


def load_records() -> list[dict[str, Any]]:
    """Load and validate pass records in stable source-path order."""
    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for path in sorted(KB_DIR.glob("卷*/j*_y*.json"), key=lambda item: item.as_posix()):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BuildError(f"failed to read {path}: {exc}") from exc

        if not isinstance(raw, dict):
            raise BuildError(f"{path}: record must be a JSON object")
        if raw.get("status") != "pass":
            continue

        record_id = require(raw, "id", str, path)
        match = RECORD_ID_RE.fullmatch(record_id)
        if match is None:
            raise BuildError(f"{path}: invalid pass record id {record_id!r}")
        if record_id in seen_ids:
            raise BuildError(f"{path}: duplicate pass record id {record_id!r}")
        seen_ids.add(record_id)

        juan = require(raw, "juan", int, path)
        if juan < 1 or juan > TOTAL_VOLUMES:
            raise BuildError(f"{path}: juan must be between 1 and {TOTAL_VOLUMES}")
        if int(match.group("juan")) != juan:
            raise BuildError(f"{path}: id {record_id!r} does not match juan {juan}")

        for key in ("section", "ruler", "year_label", "western_volume_range"):
            require(raw, key, str, path)
        require(raw, "translation_full", str, path)
        chunks = require(raw, "chunks", list, path)
        for index, chunk in enumerate(chunks):
            if not isinstance(chunk, dict) or not isinstance(chunk.get("source_text"), str):
                raise BuildError(f"{path}: chunks[{index}].source_text must be str")

        source = require(raw, "source", dict, path)
        require(source, "segment_layer", dict, path)
        require(source, "raw_layer", dict, path)
        require(raw, "license_note", str, path)

        raw["_path"] = path
        records.append(raw)

    return records


def year_name(record: dict[str, Any]) -> str:
    era = record.get("era")
    if era is not None and not isinstance(era, str):
        raise BuildError(f"{record['_path']}: 'era' must be str or null")
    return f"{record['ruler']}{era or ''}{record['year_label']}"


def western_label(record: dict[str, Any]) -> str:
    western_year = record.get("western_year")
    if western_year is None:
        return f"西暦(巻範囲): {record['western_volume_range']}"
    if not isinstance(western_year, (str, int)) or isinstance(western_year, bool):
        raise BuildError(f"{record['_path']}: 'western_year' must be str, int, or null")
    return f"西暦: {western_year}"


def clean_source_text(text: str) -> str:
    """Remove only the source-layer markup specified for the details block."""
    text = NOTE_ANCHOR_RE.sub("", text)
    text = text.replace("'''", "")
    text = LEADING_COLON_RE.sub("", text)
    text = CIRCLED_NUMBER_RE.sub("", text)
    text = EXCESS_BLANK_LINES_RE.sub("\n\n", text)
    return text.strip()


def cleaned_source(record: dict[str, Any]) -> str:
    parts = [clean_source_text(chunk["source_text"]) for chunk in record["chunks"]]
    return "\n\n".join(part for part in parts if part)


def display_license(value: Any, path: Path) -> str:
    if not isinstance(value, str):
        raise BuildError(f"{path}: source.segment_layer.license must be str")
    match = re.fullmatch(r"CC-BY-SA-(\d+(?:\.\d+)?)", value, re.IGNORECASE)
    return f"CC BY-SA {match.group(1)}" if match else value


def result_license_note(value: str) -> str:
    clauses = [part.strip() for part in re.split(r"[;；]", value) if part.strip()]
    result = next((part for part in clauses if part.startswith("成果物")), value.strip())
    return result.rstrip("。. ") + "。"


def source_footer(record: dict[str, Any]) -> str:
    path = record["_path"]
    segment = record["source"]["segment_layer"]
    raw = record["source"]["raw_layer"]
    title = require(segment, "title", str, path)
    revid = segment.get("revid")
    if not isinstance(revid, (str, int)) or isinstance(revid, bool):
        raise BuildError(f"{path}: source.segment_layer.revid must be str or int")
    license_name = display_license(segment.get("license"), path)
    commit = require(raw, "commit", str, path)
    if len(commit) < 7:
        raise BuildError(f"{path}: source.raw_layer.commit must contain at least 7 characters")

    source_id = raw.get("source_id", "kanripo-KR2b0007")
    if not isinstance(source_id, str):
        raise BuildError(f"{path}: source.raw_layer.source_id must be str")
    raw_name = source_id.removeprefix("kanripo-").removeprefix("Kanripo-")

    return (
        f"出典: 維基文庫「{title}」(revid {revid}, {license_name}) / "
        f"原字: Kanripo {raw_name} @{commit[:7]} . "
        f"{result_license_note(record['license_note'])}"
    )


def year_navigation(records: list[dict[str, Any]], index: int) -> str:
    parts: list[str] = []
    if index > 0:
        previous = records[index - 1]
        parts.append(f"[← 前年: {year_name(previous)}]({previous['id']}.md)")
    parts.append("[巻インデックス](README.md)")
    if index + 1 < len(records):
        following = records[index + 1]
        parts.append(f"[次年: {year_name(following)} →]({following['id']}.md)")
    return " ・ ".join(parts)


def render_year(record: dict[str, Any], records: list[dict[str, Any]], index: int) -> str:
    name = year_name(record)
    prefix = (
        f"# 卷{record['juan']:03d} {record['section']} — {name}\n\n"
        f"> 巻 {record['juan']} / {TOTAL_VOLUMES} ・ {record['section']} ・ "
        f"年号: {name} ・ {western_label(record)}\n"
    )
    if record.get("western_year") is None:
        prefix += "> ※年単位の西暦は未確定(別タスク T-year)。原文の年号・干支を正とする。\n"
    prefix += "\n[← 巻インデックス](README.md)\n\n---\n\n"

    # translation_full is intentionally inserted without parsing or normalization.
    return (
        prefix
        + record["translation_full"]
        + "\n\n---\n\n<details>\n<summary>原文を表示</summary>\n\n"
        + cleaned_source(record)
        + "\n\n</details>\n\n---\n\n"
        + source_footer(record)
        + "\n\n"
        + year_navigation(records, index)
        + "\n"
    )


def render_volume(records: list[dict[str, Any]]) -> str:
    first = records[0]
    entries = "\n".join(
        f"- [{year_name(record)}]({record['id']}.md)" for record in records
    )
    return (
        f"# 卷{first['juan']:03d} {first['section']}\n\n"
        f"西暦(巻範囲): {first['western_volume_range']} ・ 確定 {len(records)} 年\n\n"
        f"{entries}\n\n"
        "[← 全巻インデックス](../README.md)\n"
    )


def render_master(volumes: list[list[dict[str, Any]]]) -> str:
    entries = []
    for records in volumes:
        first, last = records[0], records[-1]
        entries.append(
            f"- [卷{first['juan']:03d} {first['section']}]"
            f"(卷{first['juan']:03d}/README.md) — "
            f"{year_name(first)} 〜 {year_name(last)}({len(records)}年確定)"
        )
    listing = "\n".join(entries)
    return (
        "# 資治通鑑 現代日本語訳(超訳)\n\n"
        "司馬光『資治通鑑』全294巻を現代日本語の平易な口語で読むためのナレッジベース。\n"
        "**このディレクトリは `pipeline/build_view.py` が `data/kb/` から自動生成する。直接編集しない。**\n"
        "原文・胡注=CC BY-SA 4.0(原典は public domain)。成果物=CC BY-NC-SA 系。\n\n"
        "## 巻一覧(確定分)\n"
        + (listing + "\n" if listing else "")
    )


def write_view(records: list[dict[str, Any]]) -> tuple[int, int]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[f"卷{record['juan']:03d}"].append(record)

    volumes: list[list[dict[str, Any]]] = []
    rendered: dict[Path, str] = {}
    for volume_name in sorted(grouped):
        volume_records = sorted(grouped[volume_name], key=lambda record: record["id"])
        volumes.append(volume_records)
        volume_dir = DOCS_DIR / volume_name
        rendered[volume_dir / "README.md"] = render_volume(volume_records)
        for index, record in enumerate(volume_records):
            rendered[volume_dir / f"{record['id']}.md"] = render_year(
                record, volume_records, index
            )
    rendered[DOCS_DIR / "README.md"] = render_master(volumes)

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    for volume_dir in sorted(DOCS_DIR.glob("卷[0-9][0-9][0-9]")):
        if volume_dir.is_dir():
            for markdown_file in sorted(volume_dir.glob("*.md")):
                markdown_file.unlink()

    for path in sorted(rendered, key=lambda item: item.as_posix()):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered[path], encoding="utf-8")

    return len(volumes), len(rendered)


def main() -> int:
    try:
        records = load_records()
        volume_count, file_count = write_view(records)
    except (BuildError, OSError) as exc:
        print(f"build_view.py: error: {exc}", file=sys.stderr)
        return 1

    print(f"pass records: {len(records)}")
    print(f"volumes: {volume_count}")
    print(f"generated files: {file_count}")
    print(f"out -> {DOCS_DIR.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

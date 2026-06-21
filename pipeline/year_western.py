#!/usr/bin/env python3
"""年レコードの年頭注から西暦を決定し、検証マニフェストを生成する。"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from western_years import GAN, ZHI, astro_ganzhi, astro_to_disp, cn2int, gz_index


ROOT = Path(__file__).resolve().parent.parent
KB_DIR = ROOT / "data" / "kb"
VOLUME_MANIFEST = ROOT / "pipeline" / "manifests" / "volume_years.json"
OUT = ROOT / "pipeline" / "manifests" / "year_western.json"

POSITIONAL_DIGITS = "〇○零一二三四五六七八九"
POSITIONAL_VALUES = {
    "〇": 0,
    "○": 0,
    "零": 0,
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
YEAR_NOTE_RE = re.compile(
    rf"^（([{GAN}][{ZHI}])、(前)?([{POSITIONAL_DIGITS}]+)）"
)
RECORD_PATH_RE = re.compile(r"卷(\d{3})/j(\d{3})_y(\d{2})\.json$")


def cn_positional2int(s: str) -> int:
    """位取り漢数字を、各文字を十進数字として連結して整数化する。"""
    if not s or any(char not in POSITIONAL_VALUES for char in s):
        raise ValueError(f"invalid positional Chinese number: {s!r}")
    return int("".join(str(POSITIONAL_VALUES[char]) for char in s))


def record_paths() -> list[Path]:
    paths = []
    for path in KB_DIR.glob("卷[0-9][0-9][0-9]/j[0-9][0-9][0-9]_y[0-9][0-9].json"):
        relative = path.relative_to(KB_DIR).as_posix()
        match = RECORD_PATH_RE.fullmatch(relative)
        if match:
            paths.append((tuple(int(value) for value in match.groups()), path))
    return [path for _, path in sorted(paths)]


def first_year_note(record: dict) -> re.Match[str] | None:
    chunks = record.get("chunks") or []
    notes = (chunks[0].get("hu_notes") or []) if chunks else []
    for note in notes:
        match = YEAR_NOTE_RE.match(note.get("text", ""))
        if match:
            return match
    return None


def year_number(year_label: str) -> int:
    value = cn2int(year_label.removesuffix("年"))
    if value is None:
        raise ValueError(f"cannot parse year_label: {year_label!r}")
    return value


def warning(kind: str, **details: object) -> dict:
    return {"type": kind, **details}


def main() -> int:
    volume_data = json.loads(VOLUME_MANIFEST.read_text(encoding="utf-8"))
    volume_ranges = {
        row["juan"]: (row["start_astro"], row["end_astro"])
        for row in volume_data["rows"]
    }

    records = []
    previous_by_juan: dict[int, int] = {}
    warnings = []

    for path in record_paths():
        data = json.loads(path.read_text(encoding="utf-8"))
        juan = data["juan"]
        match = first_year_note(data)
        if match:
            ganzhi, era_flag, digits = match.groups()
            year = cn_positional2int(digits)
            astro = 1 - year if era_flag else year
            interpolated = False
            ganzhi_ok = astro_ganzhi(astro) == gz_index(ganzhi)
        else:
            if juan not in previous_by_juan:
                raise ValueError(
                    f"{path.relative_to(ROOT)}: no year note and no previous record in juan {juan}"
                )
            astro = previous_by_juan[juan] + 1
            ganzhi = None
            interpolated = True
            ganzhi_ok = None

        if juan not in volume_ranges:
            raise ValueError(f"juan {juan} is absent from {VOLUME_MANIFEST.relative_to(ROOT)}")
        start_astro, end_astro = volume_ranges[juan]
        in_range = start_astro <= astro <= end_astro

        item = {
            "path": path,
            "data": data,
            "id": data["id"],
            "juan": juan,
            "ruler": data["ruler"],
            "year_label": data["year_label"],
            "ganzhi": ganzhi,
            "astro": astro,
            "western_year": astro_to_disp(astro),
            "ganzhi_ok": ganzhi_ok,
            "in_range": in_range,
            "interpolated": interpolated,
        }
        records.append(item)
        previous_by_juan[juan] = astro

        if ganzhi_ok is False:
            warnings.append(warning(
                "ganzhi_mismatch", id=item["id"], ganzhi=ganzhi,
                western_year=item["western_year"]
            ))
        if not in_range:
            warnings.append(warning(
                "range_violation", id=item["id"], juan=juan, astro=astro,
                start_astro=start_astro, end_astro=end_astro
            ))

    sequence_violation_count = 0
    records_by_juan: dict[int, list[dict]] = defaultdict(list)
    for item in records:
        records_by_juan[item["juan"]].append(item)
    for juan, items in records_by_juan.items():
        for previous, current in zip(items, items[1:]):
            if current["astro"] != previous["astro"] + 1:
                sequence_violation_count += 1
                warnings.append(warning(
                    "sequence_violation", juan=juan,
                    previous_id=previous["id"], previous_astro=previous["astro"],
                    current_id=current["id"], current_astro=current["astro"]
                ))

    ruler_groups: dict[str, list[dict]] = defaultdict(list)
    for item in records:
        accession_astro = item["astro"] - (year_number(item["year_label"]) - 1)
        item["accession_astro"] = accession_astro
        ruler_groups[item["ruler"]].append(item)

    accession_inconsistency_count = 0
    ruler_accession = []
    for ruler, items in ruler_groups.items():
        accession_values = sorted({item["accession_astro"] for item in items})
        if len(accession_values) > 1:
            accession_inconsistency_count += 1
            warnings.append(warning(
                "accession_inconsistency", ruler=ruler,
                accession_astro_values=accession_values
            ))
        accession_astro = items[0]["accession_astro"]
        ruler_accession.append({
            "ruler": ruler,
            "accession_western": astro_to_disp(accession_astro),
            "accession_astro": accession_astro,
            "years": [{
                "id": item["id"],
                "juan": item["juan"],
                "year_label": item["year_label"],
                "ganzhi": item["ganzhi"],
                "western_year": item["western_year"],
                "ganzhi_ok": item["ganzhi_ok"],
                "in_range": item["in_range"],
                "interpolated": item["interpolated"],
            } for item in items],
        })

    ganzhi_mismatch_count = sum(item["ganzhi_ok"] is False for item in records)
    range_violation_count = sum(not item["in_range"] for item in records)
    interpolated_count = sum(item["interpolated"] for item in records)
    anchor = records[0] if records else None
    manifest = {
        "method": "husanxing 年頭注（干支・西暦）を一次根拠に western_year を決定。干支×astro / 巻範囲 / 連番 / 在位整合 で多重検証(LLM不使用)",
        "anchor": {
            "juan": anchor["juan"] if anchor else None,
            "first_year": anchor["western_year"] if anchor else None,
            "ganzhi": anchor["ganzhi"] if anchor else None,
        },
        "records": len(records),
        "ganzhi_mismatch_count": ganzhi_mismatch_count,
        "range_violation_count": range_violation_count,
        "sequence_violation_count": sequence_violation_count,
        "accession_inconsistency_count": accession_inconsistency_count,
        "interpolated_count": interpolated_count,
        "ruler_accession": ruler_accession,
        "warnings": warnings,
    }

    for item in records:
        item["data"]["western_year"] = item["western_year"]
        item["path"].write_text(
            json.dumps(item["data"], ensure_ascii=False, indent=1), encoding="utf-8"
        )
    OUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"records: {manifest['records']}")
    print(f"ganzhi_mismatch_count: {ganzhi_mismatch_count}")
    print(f"range_violation_count: {range_violation_count}")
    print(f"sequence_violation_count: {sequence_violation_count}")
    print(f"accession_inconsistency_count: {accession_inconsistency_count}")
    print(f"interpolated_count: {interpolated_count}")
    print("ruler_accession:")
    for item in ruler_accession:
        print(f"  {item['ruler']} -> {item['accession_western']}")
    print(f"out -> {OUT.relative_to(ROOT)}")

    failed = any((
        ganzhi_mismatch_count,
        range_violation_count,
        sequence_violation_count,
        accession_inconsistency_count,
    ))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

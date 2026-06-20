#!/usr/bin/env python3
"""staging KB 書き出し: 全294巻 → 年レコード(注解決 + メタデータ + 作業チャンク)。

DESIGN §5/§8 準拠。出力は data/staging/kb/卷NNN.json(gitignore)。
- 各年エントリを 1 レコード化。胡注は ⟦nK⟧ プレースホルダ位置を保持しつつ実テキストを resolve。
- 長い年(>HARD字)は事件マーカー・段落・句点境界で作業チャンクに分割(DESIGN §5: 1,500〜2,500字)。
- 西暦(元号→年)・後世校勘レイヤ判別・Kanripo クロスチェックは後続タスク(TODO)。

使い方: python3 pipeline/build_staging_kb.py
"""
from __future__ import annotations

import glob
import json
import re
from pathlib import Path

from segment import PLACEHOLDER_RE, parse_volume

ROOT = Path(__file__).resolve().parent.parent
WS_DIR = ROOT / "data" / "raw" / "wikisource"
OUT_DIR = ROOT / "data" / "staging" / "kb"
WS_MANIFEST = ROOT / "pipeline" / "manifests" / "wikisource.manifest.json"
KANRIPO_MANIFEST = ROOT / "pipeline" / "manifests" / "kanripo.manifest.json"
WESTERN_MANIFEST = ROOT / "pipeline" / "manifests" / "volume_years.json"

TARGET = 2000  # 作業チャンク目標字数
HARD = 2500    # 上限字数(DESIGN §5)
SENT_END = "。！？"


def vislen(s: str) -> int:
    """プレースホルダを除いた可視文字数。"""
    return len(PLACEHOLDER_RE.sub("", s))


def split_long_block(block: str, hard: int) -> list[str]:
    """単一ブロックが hard 超のとき句点境界で分割(プレースホルダは割らない)。"""
    parts: list[str] = []
    buf = ""
    i = 0
    n = len(block)
    while i < n:
        # プレースホルダはまとめて送る
        m = PLACEHOLDER_RE.match(block, i)
        if m:
            buf += m.group(0)
            i = m.end()
            continue
        ch = block[i]
        buf += ch
        i += 1
        if ch in SENT_END and vislen(buf) >= hard:
            parts.append(buf)
            buf = ""
    if buf:
        parts.append(buf)
    return parts


def chunk_entry(text: str, target: int = TARGET, hard: int = HARD) -> list[str]:
    """年本文を作業チャンクに分割。改行ブロック単位で greedy パック、超大ブロックは句点分割。"""
    blocks = [b for b in text.split("\n") if b.strip()]
    chunks: list[str] = []
    cur = ""
    for b in blocks:
        if vislen(b) > hard:
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.extend(split_long_block(b, hard))
            continue
        if cur and vislen(cur) + vislen(b) > hard:
            chunks.append(cur)
            cur = b
        else:
            cur = (cur + "\n" + b) if cur else b
    if cur:
        chunks.append(cur)
    return chunks


def build_volume(path: Path, ws_meta: dict, kanripo_commit: str, western: dict) -> dict:
    v = parse_volume(path)
    juan = int(re.search(r"(\d+)", path.stem).group(1))
    notes_all = v["_notes"]
    wj = western.get(juan, {})
    w_range = f"{wj.get('start_western','?')} 〜 {wj.get('end_western','?')}" if wj else None

    records = []
    for i, e in enumerate(v["entries"], start=1):
        main = e["main_text"]
        note_ids = e["note_ids"]
        chunks = chunk_entry(main)
        chunk_recs = []
        for ci, ch in enumerate(chunks, start=1):
            cids = [int(x) for x in PLACEHOLDER_RE.findall(ch.replace("⟦n", "⟦n"))] if False else \
                   [int(x) for x in re.findall(r"⟦n(\d+)⟧", ch)]
            chunk_recs.append({
                "chunk_id": f"j{juan:03d}_y{i:02d}_c{ci:02d}",
                "text": ch,
                "char_count": vislen(ch),
                "note_ids": cids,
            })
        records.append({
            "id": f"j{juan:03d}_y{i:02d}",
            "juan": juan,
            "section": v["section"],
            "ruler": e["ruler"],
            "year_label": e["year_label"],
            "era": e.get("era"),
            "western_year": None,          # TODO: 巻内の年単位西暦(要・元号別在位表)
            "western_volume_range": w_range,  # B: 巻レベル西暦(干支決定論)
            "main_text": main,
            "notes": [{"idx": k, "text": notes_all[k]} for k in note_ids],
            "chunks": chunk_recs,
            "has_chenguang": e["has_chenguang"],
            "chars_main": e["chars_main"],
            "note_count": e["note_count"],
            "persons": [],                 # TODO(C): エンティティ辞書
            "places": [],                  # TODO(C)
            "normalization_log": [],
        })

    return {
        "juan": juan,
        "section": v["section"],
        "range_note": v["range_note"],
        "western_start": wj.get("start_western"),
        "western_end": wj.get("end_western"),
        "western_interpolated": wj.get("interpolated"),
        "source": {
            "segment_layer": {
                "source_id": ws_meta["source_id"],
                "title": f"資治通鑒 (胡三省音注)/卷{juan:03d}",
                "revid": next((r["revid"] for r in ws_meta["juan"] if r["juan"] == juan), None),
                "retrieved_at": ws_meta["retrieved_at"],
                "license": ws_meta["license"],
            },
            "raw_layer": {"source_id": "kanripo-KR2b0007", "commit": kanripo_commit},
        },
        "license_note": "本文/注=CC BY-SA 4.0(原典は public domain); 成果物=CC BY-NC-SA 系",
        "year_records": records,
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ws_meta = json.loads(WS_MANIFEST.read_text(encoding="utf-8"))
    kanripo_commit = json.loads(KANRIPO_MANIFEST.read_text(encoding="utf-8"))["commit"]
    western = {r["juan"]: r for r in json.loads(WESTERN_MANIFEST.read_text(encoding="utf-8"))["rows"]}

    files = sorted(glob.glob(str(WS_DIR / "卷*.wikitext")))
    tot_years = tot_chunks = 0
    chunk_sizes: list[int] = []
    over_hard = 0
    index = []
    for f in files:
        vol = build_volume(Path(f), ws_meta, kanripo_commit, western)
        out = OUT_DIR / f"卷{vol['juan']:03d}.json"
        out.write_text(json.dumps(vol, ensure_ascii=False, indent=1), encoding="utf-8")
        ny = len(vol["year_records"])
        nc = sum(len(r["chunks"]) for r in vol["year_records"])
        tot_years += ny
        tot_chunks += nc
        for r in vol["year_records"]:
            for c in r["chunks"]:
                chunk_sizes.append(c["char_count"])
                if c["char_count"] > HARD:
                    over_hard += 1
        index.append({"juan": vol["juan"], "section": vol["section"], "year_records": ny, "chunks": nc})

    manifest = {
        "built_at": __import__("time").strftime("%Y-%m-%d"),
        "volumes": len(files),
        "total_year_records": tot_years,
        "total_chunks": tot_chunks,
        "chunk_char": {
            "min": min(chunk_sizes),
            "max": max(chunk_sizes),
            "mean": round(sum(chunk_sizes) / len(chunk_sizes), 1),
            "over_hard_limit": over_hard,
        },
        "index": index,
    }
    (OUT_DIR / "_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"volumes: {len(files)}")
    print(f"total year-records: {tot_years}")
    print(f"total work-chunks: {tot_chunks}")
    print(f"chunk chars: min {manifest['chunk_char']['min']} mean {manifest['chunk_char']['mean']} max {manifest['chunk_char']['max']}")
    print(f"chunks over HARD({HARD}): {over_hard}")
    print(f"out -> {OUT_DIR.relative_to(ROOT)}/卷NNN.json (+ _manifest.json)")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

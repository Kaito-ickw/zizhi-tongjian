#!/usr/bin/env python3
"""エンティティ辞書 seed ビルダ(C)。DESIGN §6 / research/03 のスキーマに準拠。

- 人物: CBDB BIOG_MAIN + ALTNAME_DATA(対象時代窓の人物 + 異名)。繁体字=本文と一致。
- 官職: CBDB OFFICE_CODES(統制語彙。王朝でコード再利用のため全件を語彙として採用)。
- 地名: TGAZ CHGIS CSV(対象時代に重なるレコード)。※簡体字なので照合時に s2t 変換が要る。
- name_index: 表記 → 候補 entity_id 群(同名異人/異地を候補集合で返す)。

出力: dict/*.jsonl(gitignore)+ dict/_manifest.json(counts/provenance, tracked)。
同定は候補集合。単一正規名に潰さない(DESIGN §6)。
"""
from __future__ import annotations

import csv
import json
import re
import sqlite3
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CBDB = ROOT / "data" / "raw" / "cbdb" / "cbdb_20260613.sqlite3"
TGAZ = ROOT / "data" / "raw" / "tgaz" / "tgaz_chgis_2016-07-06.csv"
OUT = ROOT / "dict"
ERA_LO, ERA_HI = -450, 980  # 前403〜後959 + マージン

CBDB_VERSION = "2026-06-13"
CBDB_LICENSE = "CC-BY-NC-SA-4.0"
TGAZ_VERSION = "2016-07-06"
TGAZ_LICENSE = "CHGIS-EULA/CC-BY-NC(要確認・内部利用)"


def yr(v):
    return v if v not in (0, None) else None


def build_persons(cur, name_index) -> tuple[int, int, Path]:
    # 異名: personid -> [(surface, type_code)]
    alts = defaultdict(list)
    for pid, nm, tc in cur.execute(
        "select c_personid, c_alt_name_chn, c_alt_name_type_code from ALTNAME_DATA where c_alt_name_chn is not null and c_alt_name_chn<>''"
    ):
        alts[pid].append((nm, tc))

    q = f"""select c_personid, c_name_chn, c_birthyear, c_deathyear,
                    c_fl_earliest_year, c_fl_latest_year, c_index_year, c_dy
             from BIOG_MAIN where
               (c_birthyear between {ERA_LO} and {ERA_HI}) or (c_deathyear between {ERA_LO} and {ERA_HI})
               or (c_fl_earliest_year between {ERA_LO} and {ERA_HI}) or (c_fl_latest_year between {ERA_LO} and {ERA_HI})
               or (c_index_year between {ERA_LO} and {ERA_HI})"""
    out = OUT / "persons.jsonl"
    n = nalt = 0
    with out.open("w", encoding="utf-8") as f:
        for pid, nm, by, dy_, fle, fll, iy, dyc in cur.execute(q):
            if not nm:
                continue
            eid = f"person:cbdb:{pid}"
            names = [{"surface": nm, "name_type": "primary"}]
            for s, tc in alts.get(pid, []):
                names.append({"surface": s, "name_type": f"code:{tc}"})
                nalt += 1
            rec = {
                "entity_id": eid,
                "entity_type": "person",
                "canonical_name_zh": nm,
                "valid_from": yr(by),
                "valid_to": yr(dy_),
                "fl_years": [yr(fle), yr(fll)],
                "index_year": yr(iy),
                "dynasty_code": dyc,
                "status": "seed",
                "names": names,
                "authority_ids": [{"authority": "CBDB", "id": pid, "same_as_status": "exact"}],
                "source_assertions": [{"source": "CBDB", "source_version": CBDB_VERSION,
                                        "license": CBDB_LICENSE, "source_record_id": pid}],
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            for nm2 in {x["surface"] for x in names}:
                name_index[nm2].append({"id": eid, "t": "person", "vf": yr(by), "vt": yr(dy_)})
            n += 1
    return n, nalt, out


def build_offices(cur, name_index) -> tuple[int, Path]:
    out = OUT / "offices.jsonl"
    n = 0
    with out.open("w", encoding="utf-8") as f:
        for oid, dyc, chn, chn_alt, trans in cur.execute(
            "select c_office_id, c_dy, c_office_chn, c_office_chn_alt, c_office_trans from OFFICE_CODES where c_office_chn is not null and c_office_chn<>''"
        ):
            eid = f"office:cbdb:{oid}"
            surfaces = [chn] + [s for s in re.split(r"[;；/]", chn_alt or "") if s.strip()]
            rec = {
                "entity_id": eid,
                "entity_type": "office_name_instance",
                "canonical_name_zh": chn,
                "alt_names": [s for s in surfaces[1:]],
                "translation_en": trans,
                "dynasty_code": dyc,
                "status": "seed",
                "authority_ids": [{"authority": "CBDB", "id": oid}],
                "source_assertions": [{"source": "CBDB", "source_version": CBDB_VERSION,
                                        "license": CBDB_LICENSE, "source_record_id": oid}],
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            for s in {x.strip() for x in surfaces if x.strip()}:
                name_index[s].append({"id": eid, "t": "office"})
            n += 1
    return n, out


def build_places(name_index, cc) -> tuple[int, Path]:
    out = OUT / "places.jsonl"
    n = 0
    with TGAZ.open(encoding="utf-8-sig") as fin, out.open("w", encoding="utf-8") as f:
        for row in csv.DictReader(fin):
            try:
                beg, end = int(row["BEG"]), int(row["END"])
            except ValueError:
                continue
            if not (beg <= 959 and end >= -403):  # 対象時代に重なる
                continue
            nm = (row["NAME_SIM"] or "").strip()
            if not nm:
                continue
            eid = f"place:tgaz:{row['TGAZ_ID']}"
            # 照合用 surface 群: 原表記 + 型接尾辞除去 +(opencc があれば)繁体字変換
            typ = (row.get("TYPE_SIM") or "").strip()
            surfaces = {nm}
            if typ and nm.endswith(typ) and len(nm) > len(typ):
                surfaces.add(nm[:-len(typ)])
            if cc:
                for s in list(surfaces):
                    surfaces.add(cc.convert(s))
            rec = {
                "entity_id": eid,
                "entity_type": "place",
                "canonical_name_zh_sim": nm,   # 簡体字(照合時 s2t 必要)
                "name_en": row.get("NAME_ENG"),
                "valid_from": beg,
                "valid_to": end,
                "feature_type": row.get("TYPE_SIM"),
                "longitude": row.get("X"),
                "latitude": row.get("Y"),
                "partof": {"id": row.get("PARTOF_ID"), "name_sim": row.get("PARTOF_SIM")},
                "status": "seed",
                "authority_ids": [{"authority": "TGAZ", "id": row["TGAZ_ID"]}],
                "source_assertions": [{"source": "TGAZ-CHGIS", "source_version": TGAZ_VERSION,
                                        "license": TGAZ_LICENSE, "source_record_id": row["TGAZ_ID"]}],
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            for s in surfaces:
                name_index[s].append({"id": eid, "t": "place", "vf": beg, "vt": end})
            n += 1
    return n, out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(CBDB)
    cur = c.cursor()
    name_index: dict[str, list] = defaultdict(list)

    cc = None
    try:
        from opencc import OpenCC
        cc = OpenCC("s2t")  # 簡体(TGAZ)→繁体(本文)
    except Exception:
        print("WARN: opencc 未導入 → 地名の繁体字索引は未生成(TODO)。型接尾辞除去のみ適用。")

    np, nalt, _ = build_persons(cur, name_index)
    no, _ = build_offices(cur, name_index)
    npl, _ = build_places(name_index, cc)

    # name_index 書き出し
    idx_path = OUT / "name_index.jsonl"
    ambiguous = 0
    with idx_path.open("w", encoding="utf-8") as f:
        for surface, cands in name_index.items():
            if len(cands) > 1:
                ambiguous += 1
            f.write(json.dumps({"surface": surface, "candidates": cands}, ensure_ascii=False) + "\n")

    manifest = {
        "built_at": time.strftime("%Y-%m-%d"),
        "era_window": [ERA_LO, ERA_HI],
        "persons": np, "person_aliases": nalt,
        "offices": no,
        "places_in_era": npl,
        "name_index_surfaces": len(name_index),
        "ambiguous_surfaces": ambiguous,
        "place_s2t_applied": cc is not None,
        "sources": {
            "cbdb": {"version": CBDB_VERSION, "license": CBDB_LICENSE, "file": "cbdb_20260613.sqlite3"},
            "tgaz": {"version": TGAZ_VERSION, "license": TGAZ_LICENSE, "note": "簡体字。本文(繁体字)照合は opencc s2t 要(未導入なら型接尾辞除去のみ)"},
        },
        "notes": [
            "同定は候補集合(name_index は複数候補を返す)。単一正規名に潰さない。",
            "人物は対象時代窓の年情報で抽出。年情報の無い人物は本文 NER で provisional 化(TODO)。",
            "官職は王朝コード再利用のため全件を統制語彙として採用。",
        ],
    }
    (OUT / "_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"persons: {np} (aliases {nalt})")
    print(f"offices: {no}")
    print(f"places(in era): {npl}")
    print(f"name_index surfaces: {len(name_index)} (ambiguous {ambiguous})")
    print(f"out -> dict/*.jsonl + dict/_manifest.json")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

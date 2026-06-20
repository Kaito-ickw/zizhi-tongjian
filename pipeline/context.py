#!/usr/bin/env python3
"""コンテキストパケット組立: chunk_id → 翻訳用コンテキスト JSON。

DESIGN §5(コンテキストパケット)/§6(エンティティ候補集合)/§8 準拠。
出力する内容:
- 位置づけ: 巻 / section / ruler / 年ラベル / 元号 / 巻レベル西暦レンジ / chunk の位置(何分割中の何番目か)
- 当該チャンク本文(⟦nK⟧ 付き)と、対応する胡三省注(note_ids を解決)
- 本文中に出現する人物/官職/地名の **候補集合**:
  dict/name_index.jsonl を最長一致でスキャン → persons/offices/places で正規名を解決(DESIGN §6: 単一正規名に潰さない)。
- 直前チャンクの確定訳(data/kb/ に pass 済みがあれば)。無ければ previous_chunk_id のみ。

注意(DESIGN §6): CBDB は戦国〜三国が疎なので前漢以前の人物ヒットは少ない(本文 NER 補完は別タスク)。
            地名(TGAZ)は簡体字で s2t 未適用のため繁体字本文との一致は限定的(別タスク)。

使い方:
  python3 pipeline/context.py j001_y01_c01
  python3 pipeline/context.py j001_y01_c01 --no-entities   # 辞書照合を省略(高速)
  python3 pipeline/context.py j001_y01_c01 --compact       # 本文/注を省いた要約のみ
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from segment import PLACEHOLDER_RE

ROOT = Path(__file__).resolve().parent.parent
STAGING_DIR = ROOT / "data" / "staging" / "kb"
DICT_DIR = ROOT / "dict"
KB_DIR = ROOT / "data" / "kb"

CHUNK_RE = re.compile(r"^j(\d+)_y(\d+)_c(\d+)$")
# マッチ用に本文から除去するノイズ: 胡注プレースホルダ / 太字記号 / 丸数字(事件マーカー)
BOLD_RE = re.compile(r"'''")
CIRCLED_RE = re.compile(r"[①-⓿㉑-㊿]")
WESTERN_RE = re.compile(r"(\d+)\s*(BCE|CE)")

DEFAULT_MIN_LEN = 2   # 単字表記は CBDB 異名との誤マッチが大量に出るため既定で除外(--min-len 1 で解除)
DEFAULT_MARGIN = 80   # 巻レベル西暦窓に対する生没/存続年の許容マージン(年)


def parse_western(s: str | None) -> int | None:
    """'403 BCE' → -403 / '12 CE' → 12(歴史年; 0年なし)。CBDB の BCE 負値表記と整合。"""
    if not s:
        return None
    m = WESTERN_RE.search(s)
    if not m:
        return None
    y = int(m.group(1))
    return -y if m.group(2) == "BCE" else y


def _overlaps(vf, vt, lo: int, hi: int) -> bool:
    """候補の [valid_from, valid_to] が窓 [lo, hi] と交差するか(片側欠損は他端で判定)。"""
    a = vf if isinstance(vf, int) else (vt if isinstance(vt, int) else None)
    b = vt if isinstance(vt, int) else (vf if isinstance(vf, int) else None)
    if a is None and b is None:
        return True  # 年情報なし → 反証不能なので残す(provisional)
    a = a if a is not None else b
    b = b if b is not None else a
    return not (b < lo or a > hi)

# ---- 遅延ロード・キャッシュ(プロセス内) ---------------------------------
_NAME_INDEX: dict | None = None
_NAME_MAXLEN = 0
_PERSON_IDX: dict | None = None
_OFFICE_IDX: dict | None = None
_PLACE_IDX: dict | None = None


def load_name_index() -> tuple[dict, int]:
    """name_index.jsonl を {surface: [candidates]} にロード(最長一致用に最大長も返す)。"""
    global _NAME_INDEX, _NAME_MAXLEN
    if _NAME_INDEX is not None:
        return _NAME_INDEX, _NAME_MAXLEN
    idx: dict[str, list] = {}
    maxlen = 1
    path = DICT_DIR / "name_index.jsonl"
    if not path.exists():
        raise SystemExit(f"name_index 不在: {path} (pipeline/build_dict.py を実行)")
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            rec = json.loads(line)
            s = rec["surface"]
            idx[s] = rec["candidates"]
            if len(s) > maxlen:
                maxlen = len(s)
    _NAME_INDEX, _NAME_MAXLEN = idx, maxlen
    return idx, maxlen


def _load_entity_index(kind: str) -> dict:
    """persons/offices/places.jsonl を {entity_id: slim} にロード(必要になった型のみ)。"""
    global _PERSON_IDX, _OFFICE_IDX, _PLACE_IDX
    cached = {"person": _PERSON_IDX, "office": _OFFICE_IDX, "place": _PLACE_IDX}[kind]
    if cached is not None:
        return cached
    fname = {"person": "persons.jsonl", "office": "offices.jsonl", "place": "places.jsonl"}[kind]
    path = DICT_DIR / fname
    out: dict[str, dict] = {}
    if path.exists():
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                r = json.loads(line)
                eid = r["entity_id"]
                if kind == "person":
                    out[eid] = {
                        "canonical": r.get("canonical_name_zh"),
                        "valid_from": r.get("valid_from"),
                        "valid_to": r.get("valid_to"),
                        "dynasty_code": r.get("dynasty_code"),
                    }
                elif kind == "office":
                    out[eid] = {
                        "canonical": r.get("canonical_name_zh"),
                        "translation_en": r.get("translation_en"),
                        "dynasty_code": r.get("dynasty_code"),
                    }
                else:  # place
                    out[eid] = {
                        "canonical": r.get("canonical_name_zh_sim"),
                        "name_en": r.get("name_en"),
                        "valid_from": r.get("valid_from"),
                        "valid_to": r.get("valid_to"),
                        "feature_type": r.get("feature_type"),
                    }
    if kind == "person":
        _PERSON_IDX = out
    elif kind == "office":
        _OFFICE_IDX = out
    else:
        _PLACE_IDX = out
    return out


# ---- staging KB アクセス ---------------------------------------------------
def load_volume(juan: int) -> dict:
    path = STAGING_DIR / f"卷{juan:03d}.json"
    if not path.exists():
        raise SystemExit(f"staging 巻不在: {path} (pipeline/build_staging_kb.py を実行)")
    return json.loads(path.read_text(encoding="utf-8"))


def find_chunk(chunk_id: str):
    """chunk_id → (volume, year_record, chunk_record, year_idx)。"""
    m = CHUNK_RE.match(chunk_id)
    if not m:
        raise SystemExit(f"chunk_id 形式不正: {chunk_id} (例: j001_y01_c01)")
    juan, yi, ci = int(m.group(1)), int(m.group(2)), int(m.group(3))
    vol = load_volume(juan)
    yrs = vol["year_records"]
    if not (1 <= yi <= len(yrs)):
        raise SystemExit(f"年インデックス範囲外: y{yi:02d} (巻{juan} は {len(yrs)} 年)")
    yr = yrs[yi - 1]
    chunk = next((c for c in yr["chunks"] if c["chunk_id"] == chunk_id), None)
    if chunk is None:
        raise SystemExit(f"chunk 不在: {chunk_id} (年 {yr['id']} は {len(yr['chunks'])} chunk)")
    return vol, yr, chunk, yi


# ---- エンティティ照合 ------------------------------------------------------
def clean_for_match(text: str) -> str:
    text = PLACEHOLDER_RE.sub("", text)
    text = BOLD_RE.sub("", text)
    text = CIRCLED_RE.sub("", text)
    return text


def scan_surfaces(text: str) -> list[tuple[str, int]]:
    """最長一致(非重複)スキャンで name_index にある表記を抽出。(surface, 出現回数) を初出順で返す。"""
    idx, maxlen = load_name_index()
    cleaned = clean_for_match(text)
    counts: dict[str, int] = {}
    order: list[str] = []
    i, n = 0, len(cleaned)
    while i < n:
        hit = None
        hi = min(maxlen, n - i)
        for L in range(hi, 0, -1):
            sub = cleaned[i:i + L]
            if sub in idx:
                hit = sub
                break
        if hit is not None:
            if hit not in counts:
                counts[hit] = 0
                order.append(hit)
            counts[hit] += 1
            i += len(hit)
        else:
            i += 1
    return [(s, counts[s]) for s in order]


def resolve_candidates(surfaces: list[tuple[str, int]], era_window: tuple[int, int] | None = None,
                       margin: int = DEFAULT_MARGIN, min_len: int = DEFAULT_MIN_LEN,
                       cand_cap: int = 12) -> list[dict]:
    """表記 → 候補集合(型 + 正規名解決)。DESIGN §6: 単一正規名に潰さず、王朝/生没年で絞る。

    - min_len 未満の表記は除外(単字の CBDB 異名誤マッチを抑制)。
    - era_window=(lo,hi) があれば person/place 候補を [lo-margin, hi+margin] と交差するものに限定。
      年情報なし候補は反証不能のため残す(provisional)。office は王朝コード再利用のため年フィルタ非適用。
    """
    idx, _ = load_name_index()
    surfaces = [(s, c) for s, c in surfaces if len(s) >= min_len]
    kinds_needed = set()
    for s, _c in surfaces:
        for cand in idx.get(s, []):
            kinds_needed.add(cand.get("t"))
    resolvers = {k: _load_entity_index(k) for k in kinds_needed if k in ("person", "office", "place")}

    lo = hi = None
    if era_window:
        lo, hi = era_window[0] - margin, era_window[1] + margin

    items = []
    for s, cnt in surfaces:
        raw_cands = idx.get(s, [])
        out_cands = []
        for cand in raw_cands:
            t = cand.get("t")
            cid = cand.get("id")
            entry = {"id": cid, "type": t}
            slim = resolvers.get(t, {}).get(cid, {}) if t in resolvers else {}
            if slim:
                entry["canonical"] = slim.get("canonical")
                for k in ("valid_from", "valid_to", "translation_en", "feature_type"):
                    if slim.get(k) is not None:
                        entry[k] = slim[k]
            elif cand.get("vf") is not None or cand.get("vt") is not None:
                entry["valid_from"] = cand.get("vf")
                entry["valid_to"] = cand.get("vt")
            # 西暦窓フィルタ(person / place のみ)
            if lo is not None and t in ("person", "place"):
                if not _overlaps(entry.get("valid_from"), entry.get("valid_to"), lo, hi):
                    continue
            out_cands.append(entry)
            if len(out_cands) >= cand_cap:
                break
        if not out_cands:
            continue
        # 確度: 年確定(person/place で生没年あり) > office(統制語彙) > provisional(年なし人物のみ)
        has_dated = any(c["type"] in ("person", "place") and
                        (isinstance(c.get("valid_from"), int) or isinstance(c.get("valid_to"), int))
                        for c in out_cands)
        has_office = any(c["type"] == "office" for c in out_cands)
        confidence = "dated" if has_dated else ("office" if has_office else "provisional")
        items.append({
            "surface": s,
            "occurrences": cnt,
            "confidence": confidence,
            "candidates": out_cands,
            **({"candidates_truncated": True, "candidate_total": len(raw_cands)}
               if len(raw_cands) > len(out_cands) else {}),
        })
    return items


# ---- 直前チャンクの確定訳(data/kb/)--------------------------------------
def prev_chunk_id(chunk_id: str) -> str | None:
    """直前の作業チャンク id(同年→同巻前年→前巻末尾の順)。先頭なら None。"""
    m = CHUNK_RE.match(chunk_id)
    juan, yi, ci = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if ci > 1:
        return f"j{juan:03d}_y{yi:02d}_c{ci - 1:02d}"
    # 前年(同巻)の末尾チャンク
    if yi > 1:
        vol = load_volume(juan)
        prev_yr = vol["year_records"][yi - 2]
        if prev_yr["chunks"]:
            return prev_yr["chunks"][-1]["chunk_id"]
        return None
    # 前巻の末尾チャンク
    if juan > 1:
        try:
            pv = load_volume(juan - 1)
        except SystemExit:
            return None
        for yr in reversed(pv["year_records"]):
            if yr["chunks"]:
                return yr["chunks"][-1]["chunk_id"]
    return None


def read_kb_translation(cid: str) -> dict | None:
    """data/kb/卷NNN/jNNN_yMM.json から確定訳(status=pass)を引く。無ければ None。"""
    if cid is None:
        return None
    m = CHUNK_RE.match(cid)
    if not m:
        return None
    juan, yi = int(m.group(1)), int(m.group(2))
    path = KB_DIR / f"卷{juan:03d}" / f"j{juan:03d}_y{yi:02d}.json"
    if not path.exists():
        return None
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    for ch in rec.get("chunks", []):
        if ch.get("chunk_id") == cid and ch.get("status") == "pass" and ch.get("translation"):
            return {"chunk_id": cid, "translation": ch["translation"]}
    return None


# ---- コンテキスト組立 ------------------------------------------------------
def build_context(chunk_id: str, with_entities: bool = True, compact: bool = False,
                  min_len: int = DEFAULT_MIN_LEN, margin: int = DEFAULT_MARGIN,
                  era_filter: bool = True) -> dict:
    vol, yr, chunk, yi = find_chunk(chunk_id)
    note_by_idx = {n["idx"]: n["text"] for n in yr.get("notes", [])}
    notes = [{"idx": k, "text": note_by_idx.get(k)} for k in chunk.get("note_ids", [])]

    ctx: dict = {
        "chunk_id": chunk_id,
        "position": {
            "juan": vol["juan"],
            "section": vol["section"],
            "ruler": yr.get("ruler"),
            "year_label": yr.get("year_label"),
            "era": yr.get("era"),
            "western_year": yr.get("western_year"),
            "western_volume_range": yr.get("western_volume_range"),
            "year_id": yr["id"],
            "chunk_index": [c["chunk_id"] for c in yr["chunks"]].index(chunk_id) + 1,
            "chunk_count": len(yr["chunks"]),
            "has_chenguang": yr.get("has_chenguang"),
        },
        "char_count": chunk.get("char_count"),
        "source": vol.get("source"),
        "license_note": vol.get("license_note"),
    }

    pid = prev_chunk_id(chunk_id)
    ctx["previous_chunk_id"] = pid
    ctx["previous_translation"] = read_kb_translation(pid)

    if not compact:
        ctx["text"] = chunk.get("text")
        ctx["notes"] = notes
    else:
        ctx["note_count"] = len(notes)

    if with_entities:
        era_window = None
        if era_filter:
            lo = parse_western(vol.get("western_start"))
            hi = parse_western(vol.get("western_end"))
            if lo is not None and hi is not None:
                era_window = (min(lo, hi), max(lo, hi))
        surfaces = scan_surfaces(chunk.get("text", ""))
        items = resolve_candidates(surfaces, era_window=era_window, margin=margin, min_len=min_len)
        types: dict[str, int] = {}
        conf: dict[str, int] = {}
        for it in items:
            conf[it["confidence"]] = conf.get(it["confidence"], 0) + 1
            for c in it["candidates"]:
                types[c["type"]] = types.get(c["type"], 0) + 1
        ctx["entities"] = {
            "matched_surfaces": len(items),
            "era_window": list(era_window) if era_window else None,
            "by_type": types,
            "by_confidence": conf,
            "items": items,
        }
    return ctx


def main() -> int:
    ap = argparse.ArgumentParser(description="翻訳用コンテキストパケットを組み立てる")
    ap.add_argument("chunk_id", help="例: j001_y01_c01")
    ap.add_argument("--no-entities", action="store_true", help="name_index 照合を省略(高速)")
    ap.add_argument("--compact", action="store_true", help="本文/注本体を省き要約のみ")
    ap.add_argument("--min-len", type=int, default=DEFAULT_MIN_LEN, help=f"候補とする表記の最小字数(既定 {DEFAULT_MIN_LEN}; 1 で単字も含む)")
    ap.add_argument("--margin", type=int, default=DEFAULT_MARGIN, help=f"西暦窓フィルタの許容マージン年(既定 {DEFAULT_MARGIN})")
    ap.add_argument("--no-era-filter", action="store_true", help="生没/存続年による候補フィルタを無効化")
    args = ap.parse_args()
    ctx = build_context(args.chunk_id, with_entities=not args.no_entities, compact=args.compact,
                        min_len=args.min_len, margin=args.margin, era_filter=not args.no_era_filter)
    print(json.dumps(ctx, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

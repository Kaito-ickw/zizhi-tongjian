#!/usr/bin/env python3
"""維基文庫 wikitext を巻 → 年エントリ → レイヤ分離する正規化セグメンタ(v1)。

DESIGN §5(チャンク=年)・§7(胡注)・§8(内容レイヤ 4 分類)に対応。
- 胡注: {{*|...}} を抽出し本文中に ⟦nK⟧ プレースホルダで位置保持(note_anchor_offset)。
- 年境界: ルーラー '''王名''' と年行(例 二十三年/元年)で編年エントリに分割。
- 臣光曰: 論賛レイヤとしてタグ。
- 校勘: TODO(本文/胡注内の後世校勘の判別。要追加調査)。

使い方: python3 pipeline/segment.py [data/raw/wikisource/卷001.wikitext]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 年行: 元年 / 二十三年 / 十一年 など(漢数字のみ + 年)
RULER_RE = re.compile(r"^'''(.+?)'''$")
PLACEHOLDER_RE = re.compile(r"⟦n\d+⟧")  # 胡注プレースホルダ
# 年マーカー: 元号(任意・最大6字)+ 漢数字 + 年/載。例 二十三年 / 隆安元年 / 武德元年 / 天寶六載。
# (天寶年間は「年」を「載」と表記。見出し ==...== と胡注は呼び出し側で除去してから判定。)
YEAR_RE = re.compile(r"^(.{0,6}?)([元一二三四五六七八九十百]+)[年載]$")
HEADER_SECTION_RE = re.compile(r"section=([^|{]+)")
RANGE_NOTE_RE = re.compile(r"起.+?凡.+?年")


def find_close(s: str, i: int) -> int:
    """s[i:i+2]=='{{' のとき、対応する '}}' の直後 index を返す(深さ考慮)。"""
    depth = 0
    j = i
    while j < len(s):
        if s[j:j + 2] == "{{":
            depth += 1
            j += 2
        elif s[j:j + 2] == "}}":
            depth -= 1
            j += 2
            if depth == 0:
                return j
        else:
            j += 1
    return len(s)


def split_templates(text: str) -> tuple[str, list[str]]:
    """{{*|...}} は胡注として ⟦nK⟧ に置換しつつ抽出。他テンプレ({{Header}} 等)は除去。"""
    out: list[str] = []
    notes: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i:i + 2] == "{{":
            j = find_close(text, i)
            group = text[i:j]
            if group.startswith("{{*"):
                inner = group[2:-2]            # 先頭 '*|' を含む
                inner = inner.split("|", 1)[1] if "|" in inner else ""
                out.append(f"⟦n{len(notes)}⟧")
                notes.append(inner)
            # 非注テンプレ(Header/footer/PD-old 等)は丸ごと捨てる
            i = j
        else:
            out.append(text[i])
            i += 1
    return "".join(out), notes


def parse_volume(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")

    m = HEADER_SECTION_RE.search(raw)
    section = m.group(1).strip() if m else None
    rm = RANGE_NOTE_RE.search(raw)
    range_note = rm.group(0) if rm else None

    body, notes = split_templates(raw)

    # 行単位に。空行/インデント記号を整える。
    lines = [ln.rstrip() for ln in body.splitlines()]

    entries: list[dict] = []
    cur_ruler: str | None = None
    cur: dict | None = None
    pending: list[str] = []  # ルーラー行(注付き)を次の年エントリ先頭へ繰り越す
    for ln in lines:
        raw_core = ln.lstrip(":").strip()
        if not raw_core:
            continue
        # 判定用: 胡注プレースホルダと見出し記号 == を除去
        core_match = PLACEHOLDER_RE.sub("", raw_core).strip().strip("=").strip()
        m_r = RULER_RE.match(core_match)
        if m_r:
            cur_ruler = m_r.group(1)
            pending.append(raw_core)  # ルーラー名 + その胡注を保持
            continue
        m_y = YEAR_RE.match(core_match)
        if m_y and len(core_match) <= 8:  # 年ラベルは短い(誤検出抑制)
            cur = {
                "ruler": cur_ruler,
                "year_label": core_match,
                "era": m_y.group(1) or None,
                "lines": pending + [raw_core],  # ルーラー文脈 + 年行(干支注込み)
            }
            pending = []
            entries.append(cur)
            continue
        if cur is not None:
            cur["lines"].append(ln.strip())

    # レイヤ分類 + note 参照付け
    for e in entries:
        text = "\n".join(e.pop("lines"))
        note_ids = [int(x) for x in re.findall(r"⟦n(\d+)⟧", text)]
        e["main_text"] = text
        e["note_ids"] = note_ids
        e["note_count"] = len(note_ids)
        e["has_chenguang"] = "臣光曰" in text
        e["chars_main"] = len(re.sub(r"⟦n\d+⟧", "", text))

    return {
        "source_file": path.name,
        "section": section,
        "range_note": range_note,
        "total_notes": len(notes),
        "year_entries": len(entries),
        "entries": entries,
        "_notes": notes,
    }


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data/raw/wikisource/卷001.wikitext"
    v = parse_volume(path)
    print(f"file: {v['source_file']}")
    print(f"section: {v['section']}")
    print(f"range_note: {v['range_note']}")
    print(f"total 胡注: {v['total_notes']}")
    print(f"year_entries: {v['year_entries']}")
    cg = sum(1 for e in v["entries"] if e["has_chenguang"])
    print(f"臣光曰 を含む年: {cg}")
    print("--- 年エントリ一覧(ruler / year / 本文字数 / 注数) ---")
    for e in v["entries"]:
        print(f"  {e['ruler'] or '-'} {e['year_label']:>5}  chars={e['chars_main']:>5}  notes={e['note_count']:>3}  {'[臣光曰]' if e['has_chenguang'] else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""巻レベルの西暦レンジを決定論的に算出する(元号→西暦の LLM 生成を使わない)。

方法(DESIGN §8: 西暦は年単位メタデータ。細密変換はスコープ外):
- 各巻ヘッダの section 注 `起<歲陽歲名|干支>…盡…，凡N年` を抽出。
- 歲陽歲名(爾雅; 卷001 注に実在)→ 干支 へ変換。
- anchor: 卷001 起「著雍攝提格」= 戊寅 = 前403年。
- 連続編年なので、前巻の末年+1 近傍で起干支に一致する年へスナップしつつチェーン。
- 盡干支と凡N年でクロスチェック。抽出不能な巻は前巻末+1で補間し flag。

出力: pipeline/manifests/volume_years.json(検証可能な正本テーブル)。
"""
from __future__ import annotations

import glob
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WS_DIR = ROOT / "data" / "raw" / "wikisource"
OUT = ROOT / "pipeline" / "manifests" / "volume_years.json"

GAN = "甲乙丙丁戊己庚辛壬癸"
ZHI = "子丑寅卯辰巳午未申酉戌亥"
# 爾雅 歲陽(→天干) / 歲名(→地支)
SUI_YANG = {"閼逢": "甲", "旃蒙": "乙", "柔兆": "丙", "強圉": "丁", "著雍": "戊",
            "屠維": "己", "上章": "庚", "重光": "辛", "玄黓": "壬", "昭陽": "癸"}
SUI_MING = {"攝提格": "寅", "單閼": "卯", "執徐": "辰", "大荒落": "巳", "敦牂": "午",
            "協洽": "未", "涒灘": "申", "作噩": "酉", "閹茂": "戌", "大淵獻": "亥",
            "困敦": "子", "赤奮若": "丑"}
GANZHI_RE = re.compile(f"[{GAN}][{ZHI}]")

UNITS = "零一二三四五六七八九"


def cn2int(s: str) -> int | None:
    s = s.strip().replace("有", "").replace("餘", "")  # 二十有三=23, N餘=約N
    if not s:
        return None
    if s == "元":
        return 1
    if "百" in s:  # 念のため(通常は不要)
        h, _, rest = s.partition("百")
        hv = 1 if h == "" else UNITS.index(h)
        return hv * 100 + (cn2int(rest) or 0)
    if "十" not in s:
        return UNITS.index(s) if s in UNITS else None
    a, _, b = s.partition("十")
    tens = 1 if a == "" else UNITS.index(a)
    ones = 0 if b == "" else UNITS.index(b)
    return tens * 10 + ones


def gz_index(token: str) -> int | None:
    """干支(甲子=0) のインデックス。歲陽歲名 / 干支 どちらの表記でも解決。"""
    m = GANZHI_RE.search(token)
    if m:
        g, z = m.group(0)[0], m.group(0)[1]
        return _idx(g, z)
    for yang, g in SUI_YANG.items():  # 歲陽歲名(著雍攝提格 等)
        if token.startswith(yang):
            rest = token[len(yang):]
            for ming, z in SUI_MING.items():
                if rest.startswith(ming):
                    return _idx(g, z)
    return None


def _idx(g: str, z: str) -> int:
    gi, zi = GAN.index(g), ZHI.index(z)
    # 甲子=0 となる干支番号(0..59): gi≡idx mod10, zi≡idx mod12
    for k in range(60):
        if k % 10 == gi and k % 12 == zi:
            return k
    raise ValueError(g + z)


def astro_ganzhi(astro: int) -> int:
    return (astro - 4) % 60  # 前403年(astro -402)=14=戊寅 を満たす


def astro_to_disp(astro: int) -> str:
    return f"{1 - astro} BCE" if astro <= 0 else f"{astro} CE"


HEADER_RANGE_RE = re.compile(r"section=[^|{]*\{\{\*\|([^}]*?凡[^}]*?年)")
START_TOKEN_RE = re.compile(r"起[，]?\s*([^（），,]+)")
END_TOKEN_RE = re.compile(r"盡\s*([^（），,]+)")
FAN_RE = re.compile(r"凡([元零一二三四五六七八九十百有餘]+)年")


def parse_header(raw: str) -> dict:
    m = HEADER_RANGE_RE.search(raw)
    note = m.group(1) if m else ""
    start = gz_index(START_TOKEN_RE.search(note).group(1)) if START_TOKEN_RE.search(note) else None
    end = gz_index(END_TOKEN_RE.search(note).group(1)) if END_TOKEN_RE.search(note) else None
    fm = FAN_RE.search(note)
    fan = cn2int(fm.group(1)) if fm else None
    return {"note": note, "start_gz": start, "end_gz": end, "fan": fan}


def main() -> int:
    files = sorted(glob.glob(str(WS_DIR / "卷*.wikitext")))
    rows = []
    prev_end = None  # 前巻の末年 astro
    warnings = []
    for f in files:
        juan = int(re.search(r"(\d+)", Path(f).stem).group(1))
        h = parse_header(Path(f).read_text(encoding="utf-8"))
        sg, eg, fan = h["start_gz"], h["end_gz"], h["fan"]

        if juan == 1:
            start_astro = -402  # 前403年
            interp = False
        elif sg is not None:
            # 干支は60年周期で一意。前巻末+1 近傍±30で一致年へスナップ(誤差を自己補正)
            base = (prev_end + 1) if prev_end is not None else -402
            matches = [base + d for d in range(-30, 31) if astro_ganzhi(base + d) == sg]
            if matches:
                start_astro = min(matches, key=lambda y: abs(y - base))
                interp = False
            else:
                start_astro = base
                interp = True
        else:
            start_astro = (prev_end + 1) if prev_end is not None else -402
            interp = True

        # 末年: start+fan-1 を起点に、盡干支(権威)があれば±3でスナップ(月途中始まり等の±1を補正)
        base_end = start_astro + (fan - 1 if fan else 0)
        if eg is not None:
            ecand = [base_end + d for d in range(-3, 4) if astro_ganzhi(base_end + d) == eg]
            end_astro = min(ecand, key=lambda y: abs(y - base_end)) if ecand else base_end
        else:
            end_astro = base_end
        gz_ok = (eg is None) or (astro_ganzhi(end_astro) == eg)
        sg_ok = (sg is None) or (astro_ganzhi(start_astro) == sg)
        if not gz_ok or interp:
            warnings.append({"juan": juan, "interp": interp, "gz_end_match": gz_ok,
                             "start": astro_to_disp(start_astro), "end": astro_to_disp(end_astro)})

        rows.append({
            "juan": juan,
            "start_astro": start_astro,
            "end_astro": end_astro,
            "start_western": astro_to_disp(start_astro),
            "end_western": astro_to_disp(end_astro),
            "fan_years": fan,
            "start_gz_matched": sg_ok,
            "end_gz_matched": gz_ok,
            "interpolated": interp,
        })
        prev_end = end_astro

    manifest = {
        "method": "歲陽歲名/干支 → 西暦(anchor 前403=戊寅, 凡N年チェーン+干支スナップ)",
        "anchor": {"juan": 1, "start": "403 BCE", "ganzhi": "戊寅"},
        "volumes": len(rows),
        "first": rows[0]["start_western"],
        "last": rows[-1]["end_western"],
        "interpolated_count": sum(1 for r in rows if r["interpolated"]),
        "gz_end_mismatch_count": sum(1 for r in rows if not r["end_gz_matched"]),
        "warnings": warnings,
        "rows": rows,
    }
    OUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"volumes: {len(rows)}")
    print(f"first volume start: {rows[0]['start_western']}  (期待 403 BCE)")
    print(f"last  volume end:   {rows[-1]['end_western']}  (期待 959 CE)")
    print(f"interpolated(干支欠落で補間): {manifest['interpolated_count']}")
    print(f"盡干支ミスマッチ: {manifest['gz_end_mismatch_count']}")
    print(f"out -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

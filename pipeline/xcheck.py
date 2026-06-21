#!/usr/bin/env python3
"""Kanripo と維基文庫を巻単位で照合し、欠落・異読レポートを生成する。

使い方:
  python3 pipeline/xcheck.py --juan 1
  python3 pipeline/xcheck.py --all --date 2026-06-21

比較は OpenCC(t2s) で畳み込んだ CJK 文字列に対して行い、出力には畳み込み前の
原字を残す。外部 API や LLM は使用しない。
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from datetime import date
from pathlib import Path

from opencc import OpenCC

from segment import split_templates

ROOT = Path(__file__).resolve().parent.parent
KANRIPO_DIR = ROOT / "data" / "raw" / "kanripo"
WIKISOURCE_DIR = ROOT / "data" / "raw" / "wikisource"
DETAIL_DIR = ROOT / "data" / "staging" / "xcheck"
MANIFEST_PATH = ROOT / "pipeline" / "manifests" / "xcheck.json"
REPORT_PATH = ROOT / "research" / "T-xcheck-report.md"

KANRIPO_COMMIT = "80174f61e491db29f9921d0d3e54a59649419aa9"
WIKISOURCE_SOURCE = "資治通鑑(胡三省音注)"
JUAN_RANGE = range(1, 295)
OMISSION_MIN = 6
SNIPPET_MAX = 40

CC = OpenCC("t2s")
CJK = re.compile(r"[㐀-鿿\U00020000-\U0002ffff]")
# Kanripo 各巻の巻頭ボイラープレート(四庫提要見出し/巻タイトル/撰者・音注の奥付)。
# 巻頭以外でも delete op として現れるため、内容パターンで front_matter に分類する。
BOILERPLATE_RE = re.compile(r"欽定四庫全書|資治通鑑[卷巻]|司馬光撰|胡三省音[註注]")
KAN_NOTE_RE = re.compile(r"（[^（）]*）|\([^()]*\)")
PAGE_RE = re.compile(r"<pb:[^>]*>")
PLACEHOLDER_RE = re.compile(r"⟦n\d+⟧")
WIKI_LINK_LABEL_RE = re.compile(r"\[\[[^\]]*\|([^\]]*)\]\]")
WIKI_LINK_RE = re.compile(r"\[\[([^\]]*)\]\]")


def cjk(s: str) -> str:
    """CJK 統合漢字だけを入力順に返す。"""
    return "".join(CJK.findall(s))


def fold(s: str) -> str:
    """照合用に CJK 文字を抽出し、繁体字を簡体字へ畳み込む。"""
    return CC.convert(cjk(s))


def resolve_wiki_links(s: str) -> str:
    """CJK 抽出前に wiki link の表示ラベルだけを残す。"""
    s = WIKI_LINK_LABEL_RE.sub(r"\1", s)
    return WIKI_LINK_RE.sub(r"\1", s)


def extract_wikisource(path: Path) -> tuple[str, str]:
    """維基文庫から本文系列と胡注系列を抽出する。"""
    raw = path.read_text(encoding="utf-8")
    body_ph, notes = split_templates(raw)
    body = PLACEHOLDER_RE.sub("", body_ph)
    return cjk(resolve_wiki_links(body)), cjk(resolve_wiki_links("".join(notes)))


def extract_kanripo(path: Path) -> tuple[str, str]:
    """Kanripo から本文系列と双行夾注系列を抽出する。"""
    raw = path.read_text(encoding="utf-8")
    lines = [line for line in raw.splitlines() if not line.startswith("#")]
    text = PAGE_RE.sub("", "\n".join(lines).replace("¶", ""))

    parts: list[str] = []
    for group in KAN_NOTE_RE.findall(text):
        inner = group[1:-1]
        right, left = inner.split("/", 1) if "/" in inner else (inner, "")
        parts.append(right + left)

    notes = cjk("".join(parts))
    body = cjk(KAN_NOTE_RE.sub("", text))
    return body, notes


def classify_op(
    tag: str,
    i1: int,
    i2: int,
    j1: int,
    j2: int,
    *,
    first_difference: bool,
    kan_segment: str,
) -> str:
    """SequenceMatcher opcode をレポート分類へ変換する。"""
    if first_difference and tag == "delete" and i1 == 0:
        return "front_matter"
    # 巻タイトル等のボイラープレートが Kanripo にのみ存在する場合(巻頭以外の位置でも)。
    if tag == "delete" and BOILERPLATE_RE.search(kan_segment):
        return "front_matter"
    if tag == "delete" and i2 - i1 >= OMISSION_MIN:
        return "omission_wiki"
    if tag == "insert" and j2 - j1 >= OMISSION_MIN:
        return "omission_kanripo"
    if tag == "replace" and i2 - i1 == 1 and j2 - j1 == 1:
        return "variant_single"
    return "variant_multi"


def compare_series(kan: str, wiki: str) -> dict:
    """1 系列を fold 後に照合し、原字による差分詳細を返す。"""
    kan_folded = fold(kan)
    wiki_folded = fold(wiki)
    matcher = difflib.SequenceMatcher(None, kan_folded, wiki_folded, autojunk=False)
    opcodes = matcher.get_opcodes()
    first_difference_index = next(
        (index for index, opcode in enumerate(opcodes) if opcode[0] != "equal"),
        None,
    )

    ops: list[dict] = []
    counts = {
        "front_matter": 0,
        "omission_wiki": 0,
        "omission_kanripo": 0,
        "variant_single": 0,
        "variant_multi": 0,
        "variant": 0,
    }
    for index, (tag, i1, i2, j1, j2) in enumerate(opcodes):
        if tag == "equal":
            continue
        kind = classify_op(
            tag,
            i1,
            i2,
            j1,
            j2,
            first_difference=index == first_difference_index,
            kan_segment=kan[i1:i2],
        )
        counts[kind] += 1
        if kind.startswith("variant_"):
            counts["variant"] += 1
        ops.append({
            "kind": kind,
            "kan": kan[i1:i2][:SNIPPET_MAX],
            "wiki": wiki[j1:j2][:SNIPPET_MAX],
            "kan_pos": i1,
            "wiki_pos": j1,
        })

    return {
        "ratio": matcher.ratio(),
        "ops": ops,
        "counts": counts,
    }


def detail_path(juan: int) -> Path:
    return DETAIL_DIR / f"卷{juan:03d}.json"


def input_paths(juan: int) -> tuple[Path, Path]:
    return (
        KANRIPO_DIR / f"KR2b0007_{juan:03d}.txt",
        WIKISOURCE_DIR / f"卷{juan:03d}.wikitext",
    )


def write_json(path: Path, value: dict) -> None:
    """JSON を決定論的な書式で書き出す。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    path.write_text(rendered + "\n", encoding="utf-8")


def process_juan(juan: int) -> tuple[dict | None, list[str]]:
    """1 巻を処理する。入力欠損時は理由を返し、例外にしない。"""
    kan_path, wiki_path = input_paths(juan)
    missing: list[str] = []
    if not kan_path.is_file():
        missing.append("kanripo")
    if not wiki_path.is_file():
        missing.append("wikisource")
    if missing:
        return None, missing

    kan_body, kan_notes = extract_kanripo(kan_path)
    wiki_body, wiki_notes = extract_wikisource(wiki_path)
    detail = {
        "juan": juan,
        "body": compare_series(kan_body, wiki_body),
        "notes": compare_series(kan_notes, wiki_notes),
    }
    write_json(detail_path(juan), detail)
    return detail, []


def flag_for(detail: dict | None, missing: list[str]) -> str:
    """巻サマリ用の要レビュー印を構成する。"""
    flags: list[str] = []
    if "kanripo" in missing:
        flags.append("MISSING_KANRIPO")
    if "wikisource" in missing:
        flags.append("MISSING_WIKISOURCE")
    if detail is not None:
        if detail["body"]["ratio"] < 0.95:
            flags.append("LOW_BODY")
        if detail["notes"]["ratio"] < 0.90:
            flags.append("LOW_NOTES")
    return "|".join(flags)


def summarize_juan(juan: int, detail: dict | None, missing: list[str]) -> dict:
    """巻別詳細を manifest の固定スキーマへ縮約する。"""
    summary = {
        "juan": juan,
        "body_ratio": None,
        "body_omission_wiki": 0,
        "body_omission_kanripo": 0,
        "body_variant": 0,
        "notes_ratio": None,
        "notes_omission_wiki": 0,
        "notes_omission_kanripo": 0,
        "notes_variant": 0,
        "flag": flag_for(detail, missing),
    }
    if detail is None:
        return summary

    for layer in ("body", "notes"):
        counts = detail[layer]["counts"]
        summary[f"{layer}_ratio"] = detail[layer]["ratio"]
        summary[f"{layer}_omission_wiki"] = counts["omission_wiki"]
        summary[f"{layer}_omission_kanripo"] = counts["omission_kanripo"]
        summary[f"{layer}_variant"] = counts["variant"]
    return summary


def build_totals(per_juan: list[dict]) -> dict:
    """処理済み巻の比率平均と opcode 件数を全巻集計する。"""
    completed = [row for row in per_juan if row["body_ratio"] is not None]
    body_ratios = [row["body_ratio"] for row in completed]
    notes_ratios = [row["notes_ratio"] for row in completed]
    return {
        "juan": 294,
        "processed": len(completed),
        "skipped": 294 - len(completed),
        "flagged": sum(bool(row["flag"]) for row in per_juan),
        "body_ratio_mean": sum(body_ratios) / len(body_ratios) if body_ratios else None,
        "body_omission_wiki": sum(row["body_omission_wiki"] for row in completed),
        "body_omission_kanripo": sum(row["body_omission_kanripo"] for row in completed),
        "body_variant": sum(row["body_variant"] for row in completed),
        "notes_ratio_mean": sum(notes_ratios) / len(notes_ratios) if notes_ratios else None,
        "notes_omission_wiki": sum(row["notes_omission_wiki"] for row in completed),
        "notes_omission_kanripo": sum(row["notes_omission_kanripo"] for row in completed),
        "notes_variant": sum(row["notes_variant"] for row in completed),
    }


def build_manifest(generated_at: str, per_juan: list[dict]) -> dict:
    """全巻 manifest を構成する。"""
    return {
        "generated_at": generated_at,
        "source": {
            "kanripo_commit": KANRIPO_COMMIT,
            "wikisource": WIKISOURCE_SOURCE,
        },
        "method": {
            "description": "CJK抽出後にOpenCC t2sでfoldし、SequenceMatcher(autojunk=False)で本文・胡注を別々に照合する。",
        },
        "totals": build_totals(per_juan),
        "per_juan": per_juan,
    }


def markdown_text(value: str) -> str:
    """Markdown 表内で差分文字列を安全かつ可視にする。"""
    if not value:
        return "（空）"
    return value.replace("|", "\\|").replace("\n", " ")


def sample_rows(
    details: dict[int, dict],
    per_juan: list[dict],
    *,
    per_kind: int = 3,
) -> list[tuple[int, str, dict]]:
    """欠落・異読の各分類から代表サンプルを決定論的に選ぶ。

    1 分類が表を占有しないよう、本文/胡注の欠落・異読を分類ごとにバケットし、
    巻番号・系列順で先頭から `per_kind` 件ずつ採る。
    """
    buckets: dict[str, list[tuple[int, str, dict]]] = {}
    for juan in sorted(details):
        for layer in ("body", "notes"):
            for op in details[juan][layer]["ops"]:
                if op["kind"] == "front_matter":
                    continue
                buckets.setdefault(op["kind"], []).append((juan, layer, op))

    order = [
        "omission_wiki",
        "omission_kanripo",
        "variant_multi",
        "variant_single",
    ]
    samples: list[tuple[int, str, dict]] = []
    for kind in order:
        samples.extend(buckets.get(kind, [])[:per_kind])
    return samples


def juan_one_samples(detail: dict | None, limit: int = 4) -> list[dict]:
    """巻1注から指定例を優先して代表的な異読を選ぶ。"""
    if detail is None:
        return []
    variants = [
        op for op in detail["notes"]["ops"]
        if op["kind"].startswith("variant_")
    ]
    chosen: list[dict] = []
    for kan_char, wiki_char in (("窟", "窋"), ("安", "其")):
        match = next(
            (
                op for op in variants
                if kan_char in op["kan"] and wiki_char in op["wiki"]
            ),
            None,
        )
        if match is not None and match not in chosen:
            chosen.append(match)
    for op in variants:
        if op not in chosen:
            chosen.append(op)
        if len(chosen) == limit:
            break
    return chosen[:limit]


def build_report(manifest: dict, details: dict[int, dict]) -> str:
    """manifest と巻別詳細から人間向け Markdown レポートを生成する。"""
    totals = manifest["totals"]
    per_juan = manifest["per_juan"]
    flagged = [row for row in per_juan if row["flag"]]
    lines = [
        "# T-xcheck: Wikisource × Kanripo クロスチェック",
        "",
        f"生成日: {manifest['generated_at']}",
        "",
        "## 方法",
        "",
        "Kanripo を原文層(source of record)、維基文庫『資治通鑑(胡三省音注)』をセグメント層として、本文と胡三省注を別系列で照合した。標点・空白・markup を除いて CJK 統合漢字だけを抽出し、整合判定時のみ OpenCC `t2s` で fold した文字列を `SequenceMatcher(autojunk=False)` に渡した。レポートの差分は fold 前の原字である。",
        "",
        "Kanripo の双行夾注は、括弧グループごとに `右半 + 左半` とする de-interleave 案Bで復元した。先頭 delete は `front_matter`、6字以上の delete/insert は欠落、それ以外は異読として分類した。`front_matter` は欠落集計から除外した。",
        "",
        "## 既知の限界",
        "",
        "長い多行注では局所的な列順転倒により偽の異読が生じうる。また、Kanripo の巻頭ボイラープレートと、維基文庫 Header 内の巻頭干支レンジ注は底本間の既知の構造差であり、先頭の差分を `front_matter` として扱う。",
        "",
        "## 全巻集計",
        "",
        f"- 対象: {totals['juan']}巻（処理 {totals['processed']}、skip {totals['skipped']}）",
        f"- 平均 body ratio: {totals['body_ratio_mean']:.6f}" if totals["body_ratio_mean"] is not None else "- 平均 body ratio: N/A",
        f"- 平均 notes ratio: {totals['notes_ratio_mean']:.6f}" if totals["notes_ratio_mean"] is not None else "- 平均 notes ratio: N/A",
        f"- 本文: Wikisource 欠落 {totals['body_omission_wiki']}、Kanripo 欠落 {totals['body_omission_kanripo']}、異読 {totals['body_variant']}",
        f"- 注: Wikisource 欠落 {totals['notes_omission_wiki']}、Kanripo 欠落 {totals['notes_omission_kanripo']}、異読 {totals['notes_variant']}",
        "",
        "### 要レビュー巻",
        "",
    ]
    if flagged:
        lines.extend([
            "| 巻 | flag | body ratio | notes ratio |",
            "|---:|---|---:|---:|",
        ])
        for row in flagged:
            body_ratio = f"{row['body_ratio']:.6f}" if row["body_ratio"] is not None else "N/A"
            notes_ratio = f"{row['notes_ratio']:.6f}" if row["notes_ratio"] is not None else "N/A"
            lines.append(
                f"| {row['juan']} | {row['flag']} | {body_ratio} | {notes_ratio} |"
            )
    else:
        lines.append("該当なし。")

    lines.extend([
        "",
        "### 欠落・異読サンプル",
        "",
        "| 巻 | 系列 | 分類 | Kanripo | Wikisource |",
        "|---:|---|---|---|---|",
    ])
    samples = sample_rows(details, per_juan)
    if samples:
        for juan, layer, op in samples:
            lines.append(
                f"| {juan} | {layer} | {op['kind']} | "
                f"{markdown_text(op['kan'])} | {markdown_text(op['wiki'])} |"
            )
    else:
        lines.append("| - | - | - | 差分なし | 差分なし |")

    lines.extend([
        "",
        "## 巻1の代表的な検出例",
        "",
    ])
    volume_one = juan_one_samples(details.get(1))
    if volume_one:
        for op in volume_one:
            lines.append(
                f"- 注 `{markdown_text(op['kan'])}` → `{markdown_text(op['wiki'])}` "
                f"（{op['kind']}、Kanripo位置 {op['kan_pos']} / Wikisource位置 {op['wiki_pos']}）"
            )
    else:
        lines.append("巻1は未処理、または注の異読を検出しなかった。")
    return "\n".join(lines) + "\n"


def parse_date(value: str) -> str:
    """YYYY-MM-DD を検証し、そのまま manifest 用に返す。"""
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must be YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise argparse.ArgumentTypeError("date must be YYYY-MM-DD")
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Kanripo と Wikisource の本文・胡注を決定論的に照合する。",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--juan", type=int, choices=JUAN_RANGE, help="指定した1巻だけ処理")
    mode.add_argument("--all", action="store_true", help="全294巻を処理（既定）")
    parser.add_argument(
        "--date",
        type=parse_date,
        default=date.today().isoformat(),
        help="manifest の generated_at（YYYY-MM-DD、既定: today）",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.juan is not None:
        detail, missing = process_juan(args.juan)
        if detail is None:
            print(json.dumps({"juan": args.juan, "skipped": missing}, ensure_ascii=False, sort_keys=True))
        else:
            print(json.dumps(detail, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    details: dict[int, dict] = {}
    per_juan: list[dict] = []
    for juan in JUAN_RANGE:
        detail, missing = process_juan(juan)
        if detail is not None:
            details[juan] = detail
        per_juan.append(summarize_juan(juan, detail, missing))

    manifest = build_manifest(args.date, per_juan)
    write_json(MANIFEST_PATH, manifest)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(build_report(manifest, details), encoding="utf-8")

    totals = manifest["totals"]
    print(
        f"processed={totals['processed']}/294 skipped={totals['skipped']} "
        f"flagged={totals['flagged']}"
    )
    print(f"manifest -> {MANIFEST_PATH.relative_to(ROOT)}")
    print(f"report -> {REPORT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

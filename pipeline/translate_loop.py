#!/usr/bin/env python3
"""翻訳ループ雛形 + 確定 KB レコードスキーマ。

DESIGN §4(レビューループ)/§5(チャンク=年)/§8(KB スキーマ)準拠。

役割分担:
- 翻訳 = Claude(セッション内)。本モジュールの translate_fn 注入点に接続する(雛形では未接続)。
- レビュー = Codex(pipeline/review.py、独立セッション、別ベンダー)。
- オーケストレーション = 本モジュール: コンテキスト組立(context.py)→ 翻訳 → レビュー →
  指摘を翻訳へ FB → 修正 → 再レビュー(別独立セッション)。

ループ規約(DESIGN §4):
- 合格条件 = 「誤りがある前提」でチェックしてなお誤りが見つからない(verdict=pass)。
- 最大反復 = 3。未収束 → status=halt(halt_reason=max_iter_unconverged)。
- ラウンド間でレビュー指摘が矛盾 → status=halt(halt_reason=review_contradiction)。
- halt はユーザーへのアラート対象(自動確定しない)。

使い方:
  python3 pipeline/translate_loop.py --schema             # KB レコードスキーマ(空骨格)を表示
  python3 pipeline/translate_loop.py --init-sample        # data/kb/ に空レコード雛形 + 手順書を書く
  python3 pipeline/translate_loop.py --selftest           # ループ制御(pass/未収束/矛盾)を Codex 無しで検証
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import context
import review

ROOT = Path(__file__).resolve().parent.parent
KB_DIR = ROOT / "data" / "kb"
YEAR_RE = re.compile(r"^j(\d+)_y(\d+)$")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


# ---- KB パス規約(DESIGN §5: ファイル=年 / 巻ごとにディレクトリ)----------
def kb_year_path(juan: int, year_id: str) -> Path:
    return KB_DIR / f"卷{juan:03d}" / f"{year_id}.json"


# ---- 空レコード組立 --------------------------------------------------------
def empty_chunk_record(chunk: dict, notes_by_idx: dict[int, str]) -> dict:
    """作業チャンクの確定レコード骨格(翻訳前)。"""
    return {
        "chunk_id": chunk["chunk_id"],
        "source_text": chunk["text"],                 # ⟦nK⟧ 付き原文(胡注位置を保持)
        "hu_notes": [{"idx": k, "text": notes_by_idx.get(k)} for k in chunk.get("note_ids", [])],
        "translation": None,                          # 確定訳(現代日本語; 注挿入は〔注:…〕)
        "status": "pending",                          # pending | pass | halt
        "halt_reason": None,                          # max_iter_unconverged | review_contradiction | null
        "iterations": 0,                              # レビュー反復回数
        "review_history": [],                         # [{round, reviewer, verdict, findings, ts}]
    }


def empty_year_record(year_id: str) -> dict:
    """年(=ファイル)単位の確定 KB レコード骨格(翻訳前)。DESIGN §8。"""
    m = YEAR_RE.match(year_id)
    if not m:
        raise SystemExit(f"year_id 形式不正: {year_id} (例: j001_y01)")
    juan = int(m.group(1))
    vol = context.load_volume(juan)
    yi = int(m.group(2))
    yrs = vol["year_records"]
    if not (1 <= yi <= len(yrs)):
        raise SystemExit(f"年インデックス範囲外: {year_id}")
    yr = yrs[yi - 1]
    notes_by_idx = {n["idx"]: n["text"] for n in yr.get("notes", [])}
    return {
        "id": yr["id"],
        "juan": juan,
        "section": vol["section"],
        "ruler": yr.get("ruler"),
        "year_label": yr.get("year_label"),
        "era": yr.get("era"),
        "western_year": yr.get("western_year"),                  # 巻内年単位(別タスク)
        "western_volume_range": yr.get("western_volume_range"),  # 巻レベル(確定)
        "status": "pending",
        "halt_reason": None,
        "persons": [],                                           # 確定登場人物(候補集合は context 側)
        "places": [],                                            # 確定地名
        "source": vol.get("source"),                             # provenance(層別 source_id/revid/commit)
        "license_note": vol.get("license_note"),
        "chunks": [empty_chunk_record(c, notes_by_idx) for c in yr["chunks"]],
        "translation_full": None,                                # 確定チャンク訳の結合(年単位の読み物)
        "built_with": {"translator": "claude-opus-4-x", "reviewer": "codex(gpt)"},
        "updated_at": None,
    }


# ---- 矛盾検出(DESIGN §4: ラウンド間でレビュー指摘が矛盾)------------------
def _norm(s: str | None) -> str:
    return re.sub(r"\s+", "", (s or ""))


def detect_contradiction(prev_findings: list[dict], cur_findings: list[dict]) -> bool:
    """独立セッション間の指摘矛盾をヒューリスティック検出。

    シグナル: 直前ラウンドと今ラウンドが **重なる source_span** に対し、ともに forbidden 指摘を出し、
    かつ suggestion が食い違う(= 別セッションのレビュアーが同一箇所で逆の判断)。
    これは「未収束」とは別の停止理由(reviewer 同士の不一致)。最終判断は人間(halt→アラート)。
    """
    prev = [(_norm(f.get("source_span")), _norm(f.get("suggestion")))
            for f in prev_findings if f.get("severity") == "forbidden"]
    for f in cur_findings:
        if f.get("severity") != "forbidden":
            continue
        cs, cg = _norm(f.get("source_span")), _norm(f.get("suggestion"))
        if not cs:
            continue
        for ps, pg in prev:
            if not ps:
                continue
            overlaps = ps in cs or cs in ps          # 同一箇所(包含)
            if overlaps and pg and cg and pg != cg:  # 指示が食い違う
                return True
    return False


# ---- レビューループ本体(雛形)---------------------------------------------
def run_loop(chunk_id: str, translate_fn, review_fn=None, *, max_iter: int = 3,
             **review_kwargs) -> dict:
    """1 作業チャンクを 翻訳→レビュー→修正→再レビュー で確定/停止させる。

    - translate_fn(ctx, prev_findings, prev_translation) -> str: 翻訳本体(Claude が注入)。
    - review_fn(source_text, hu_notes, translation) -> {verdict, findings, _meta}:
      省略時は review.run_review(**review_kwargs) を独立セッションで呼ぶ。
    返り値 = 確定チャンクレコード(empty_chunk_record と同形 + 確定 translation/status)。
    """
    if translate_fn is None:
        raise NotImplementedError(
            "translate_fn 未注入。翻訳本体は Claude がセッション内で供給する(本モジュールは雛形)。")
    if review_fn is None:
        def review_fn(src, notes, tr):
            return review.run_review(src, notes, tr, **review_kwargs)

    ctx = context.build_context(chunk_id)
    chunk = {"chunk_id": chunk_id, "text": ctx["text"], "note_ids": [n["idx"] for n in ctx["notes"]]}
    notes_by_idx = {n["idx"]: n["text"] for n in ctx["notes"]}
    rec = empty_chunk_record(chunk, notes_by_idx)
    rec["status"] = "in_progress"

    source_text = context.PLACEHOLDER_RE.sub("", ctx["text"])  # レビュアーへの本文原文(注は別供給)
    hu_notes = [n["text"] for n in ctx["notes"] if n.get("text")]

    prev_findings = None
    translation = None
    for rnd in range(1, max_iter + 1):
        translation = translate_fn(ctx, prev_findings, translation)
        rv = review_fn(source_text, hu_notes, translation)
        rec["iterations"] = rnd
        rec["review_history"].append({
            "round": rnd,
            "reviewer": rv.get("_meta", {}).get("reviewer"),
            "verdict": rv["verdict"],
            "findings": rv["findings"],
            "ts": _now(),
        })
        if rv["verdict"] == "pass":
            rec["status"], rec["translation"] = "pass", translation
            return rec
        if prev_findings is not None and detect_contradiction(prev_findings, rv["findings"]):
            rec["status"], rec["halt_reason"] = "halt", "review_contradiction"
            rec["translation"] = translation
            return rec
        prev_findings = rv["findings"]

    rec["status"], rec["halt_reason"] = "halt", "max_iter_unconverged"
    rec["translation"] = translation
    return rec


# ---- 雛形成果物: 空レコード + 手順書 --------------------------------------
LOOP_DOC = """\
# 翻訳ループ手順書(KB レコード生成)

DESIGN §4(レビューループ)/§5(チャンク=年)/§8(KB スキーマ)の運用版。
実装: `pipeline/context.py`(コンテキスト)→ Claude(翻訳)→ `pipeline/review.py`(Codex レビュー)
→ `pipeline/translate_loop.py`(オーケストレーション)。

## ファイル規約
- 確定レコード = **年単位**。`data/kb/卷NNN/jNNN_yMM.json`(巻ごとにディレクトリ)。
- 翻訳の作業単位 = **チャンク**(原文 1,500〜2,500 字、`*_cKK`)。年レコードの `chunks[]` に格納。
- 本ファイル(`_LOOP.md`)と `_sample_record.json` は雛形(`_` 始まりは巻でない=メタ)。

## チャンクごとのループ(最大 3 反復)
1. **コンテキスト組立**: `context.build_context(chunk_id)` —
   位置 / 本文 / 胡三省注 / 人物・官職・地名の候補集合 / 直前チャンクの確定訳。
2. **翻訳(Claude / セッション内)**: 平易な現代日本語の口語超訳。
   - 許される脚色 = 主語補完・語順整理・比喩言換え・段落分け(DESIGN §2)。
   - 胡注由来の挿入は **`〔注:…〕`** でマーキング(DESIGN §4/§7)。
3. **レビュー(Codex / 独立セッション・別ベンダー)**: `review.run_review(本文原文, 胡注, 訳文)`。
   - 「誤りがある前提」でチェック。根拠集合(本文+胡注)に無い情報のみ捏造=forbidden。
   - 出力は `research/02-review-schema.json` 準拠(verdict / findings)。
4. **判定と分岐**:
   - `verdict=pass` → `status=pass`、`translation` 確定。
   - `verdict=fail` → findings を翻訳へ FB し修正、**別の独立セッション**で再レビュー。
   - 反復が **3** に達しても未収束 → `status=halt`, `halt_reason=max_iter_unconverged`。
   - ラウンド間で指摘が **矛盾**(`detect_contradiction`)→ `status=halt`, `halt_reason=review_contradiction`。
5. **年レコード結合**: 全チャンク `pass` なら `translation_full` に結合、年 `status=pass`。
   いずれか `halt` なら年 `status=halt` で **ユーザーにアラート**(自動確定しない)。

## status / halt_reason
- chunk/year `status`: `pending` | `in_progress` | `pass` | `halt`。
- `halt_reason`: `max_iter_unconverged` | `review_contradiction` | `null`。

## レコードのキー(`_sample_record.json` 参照)
- 年: `id, juan, section, ruler, year_label, era, western_year, western_volume_range,
  status, halt_reason, persons[], places[], source(provenance), license_note,
  chunks[], translation_full, built_with, updated_at`。
- チャンク: `chunk_id, source_text(⟦nK⟧付き), hu_notes[], translation, status, halt_reason,
  iterations, review_history[{round, reviewer, verdict, findings, ts}]`。

## 実行系メモ
- 翻訳=Claude(Claude サブスク)/ レビュー=Codex(ChatGPT サブスク・5h レート律速)。
- `codex exec` は毎回新規セッション → §4「ラウンド独立セッション」を無コストで満たす。
- ルーチンは `--effort low`、難所(差し戻し多発・矛盾)で `high` に上げる(DESIGN §3)。
"""


def init_sample() -> list[Path]:
    KB_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    sample = empty_year_record("j001_y01")
    sample["_note"] = "雛形(空レコード)。確定訳は data/kb/卷NNN/jNNN_yMM.json に生成する。"
    p1 = KB_DIR / "_sample_record.json"
    p1.write_text(json.dumps(sample, ensure_ascii=False, indent=1), encoding="utf-8")
    written.append(p1)
    p2 = KB_DIR / "_LOOP.md"
    p2.write_text(LOOP_DOC, encoding="utf-8")
    written.append(p2)
    return written


# ---- セルフテスト(Codex 無しでループ制御を検証)---------------------------
def _selftest() -> int:
    def fixed_translate(ctx, prev, prev_tr):
        return "訳(ダミー)"

    def make_review(seq):
        it = iter(seq)
        return lambda src, notes, tr: next(it)

    def rv(verdict, findings):
        return {"verdict": verdict, "findings": findings, "_meta": {"reviewer": "fake"}}

    F = lambda span, sug: {"severity": "forbidden", "category": "c", "source_span": span,
                           "translated_span": "t", "issue": "i", "suggestion": sug}
    ok = True

    # (a) pass: 1 ラウンドで合格
    r = run_loop("j001_y01_c01", fixed_translate, make_review([rv("pass", [])]), max_iter=3)
    ok &= r["status"] == "pass" and r["iterations"] == 1
    print(f"  (a) pass  -> status={r['status']} iters={r['iterations']}")

    # (b) 未収束: 3 ラウンド fail(指摘は毎回別箇所で矛盾なし)
    seq = [rv("fail", [F("span1", "s1")]), rv("fail", [F("span2", "s2")]), rv("fail", [F("span3", "s3")])]
    r = run_loop("j001_y01_c01", fixed_translate, make_review(seq), max_iter=3)
    ok &= r["status"] == "halt" and r["halt_reason"] == "max_iter_unconverged" and r["iterations"] == 3
    print(f"  (b) unconverged -> status={r['status']} reason={r['halt_reason']} iters={r['iterations']}")

    # (c) 矛盾: 同一 span に逆の suggestion → 2 ラウンド目で halt
    seq = [rv("fail", [F("初命晉大夫", "削除せよ")]), rv("fail", [F("初命晉大夫", "復元せよ")])]
    r = run_loop("j001_y01_c01", fixed_translate, make_review(seq), max_iter=3)
    ok &= r["status"] == "halt" and r["halt_reason"] == "review_contradiction" and r["iterations"] == 2
    print(f"  (c) contradiction -> status={r['status']} reason={r['halt_reason']} iters={r['iterations']}")

    print("SELFTEST:", "OK" if ok else "FAILED")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="翻訳ループ雛形 + KB レコードスキーマ")
    ap.add_argument("--schema", action="store_true", help="空 KB レコード骨格(j001_y01)を表示")
    ap.add_argument("--init-sample", action="store_true", help="data/kb/ に空レコード雛形 + 手順書を書く")
    ap.add_argument("--selftest", action="store_true", help="ループ制御を Codex 無しで検証")
    args = ap.parse_args()

    if args.selftest:
        return _selftest()
    if args.schema:
        print(json.dumps(empty_year_record("j001_y01"), ensure_ascii=False, indent=1))
        return 0
    if args.init_sample:
        for p in init_sample():
            print(f"wrote {p.relative_to(ROOT)}")
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

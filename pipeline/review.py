#!/usr/bin/env python3
"""レビュー・ハーネス: codex exec をラップした独立クロスベンダー・レビュー。

DESIGN §3(オーケストレーション)/§4(レビューループ)/§2(品質契約)準拠。
- 出典(本文原文 + 胡三省注)+ 訳文 + 品質契約を渡し、research/02-review-schema.json 準拠の
  レビュー JSON(verdict / findings)を返す。
- codex exec を「新規・独立セッション / approval_policy=never / read-only / --output-schema」で起動。
  毎回新規セッションのため §4「各レビューラウンドは独立セッション」を無コストで満たす(resume 不使用)。
- タイムアウト / 失敗リトライ / JSON パース失敗 / スキーマ不適合を処理。
- --dummy: codex を呼ばずに配線(プロンプト生成 →(模擬出力)→ パース → スキーマ検証)を検証。
  ※ pip 無し環境のため jsonschema は使わず、対象スキーマ専用の軽量バリデータを内蔵。

使い方:
  python3 pipeline/review.py --dummy                       # 配線テスト(Codex レート消費なし)
  python3 pipeline/review.py --print-prompt --input in.json  # プロンプトのみ表示
  python3 pipeline/review.py --input in.json --effort low    # 実レビュー(Codex レート必要)
    in.json = {"source_text": "...", "hu_notes": ["..."], "translation": "..."}
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "research" / "02-review-schema.json"

SEVERITY = {"forbidden", "allowed", "style"}
VERDICT = {"pass", "fail"}
FINDING_KEYS = {"severity", "category", "source_span", "translated_span", "issue", "suggestion"}

# 品質契約(DESIGN §2/§4)— レビュアー・プロンプトの固定ヘッダ
CONTRACT = """\
あなたは資治通鑑・現代日本語訳プロジェクトの「独立検証レビュアー」です。
渡された訳文には誤りが含まれている前提で、原典に照らして厳格にチェックしてください。

# 品質契約(脚色の線引き)
- 許される脚色(severity=allowed): 主語の補完 / 語順の整理 / 比喩の言い換え / 読みやすい段落分け。
- 許されない脚色(severity=forbidden / 差し戻し対象): 原文にない事実・因果・心理描写の追加 / 年月日・数字の改変 / 発言の創作。
- 文体のブレ(severity=style)は許容するが指摘はする。
- 判定: 禁止脚色(forbidden)が1つでもあれば verdict=fail。なければ verdict=pass。
- 〔注:…〕でマーキングされた挿入は胡三省注由来。出典(胡注)に根拠があれば捏造としない。

# forbidden の範囲(重要・誤検出防止)
- forbidden は「根拠集合に存在しない **事実・因果・心理・数値・発言** の新規追加」に限定する。
- **翻訳上の自然な具体化・語の訳し分けは forbidden ではなく allowed**。例:
  - 「吮其疽(疽を吸う)」→「疽の膿を吸う」のような、語義の範囲内の自然な明確化。
  - 官職名・器物名を読者向けに意訳する(根拠集合の語義と矛盾しない範囲)。
  - 因果を**新規に創作していない**接続語(「そして」「すると」等の順接で、原文の事実順序を変えないもの)。
  ※ 原文に無い因果を**創作・強調**する場合のみ forbidden。
- 迷う場合は、それが「原文に無い新情報を読者に与えるか」を基準にする。与えないなら allowed/style。"""

INSTRUCTION = """\
# 指示
- 根拠集合(本文原文 + 胡三省注)のいずれにも存在しない情報のみを「捏造(forbidden)」と判定すること。
- 各指摘は translated_span(訳文側)と source_span(対応原文)を局所化して示すこと。
- 最終応答は、指定された JSON スキーマに厳密に従う JSON だけを返すこと(散文の説明は不要)。"""

# --dummy 用の模擬 Codex 出力(スキーマ準拠。実出力と同じパース経路で検証する)
DUMMY_OUTPUT = {
    "verdict": "fail",
    "findings": [{
        "severity": "forbidden",
        "category": "原文にない事実・因果の追加",
        "source_span": "初命晉大夫魏斯、趙籍、韓虔為諸侯。",
        "translated_span": "彼らの長年にわたる忠誠を高く評価して",
        "issue": "本文にも胡三省注にも、忠誠の評価を理由に諸侯にしたという因果は無い。",
        "suggestion": "当該句を削除し『初めて諸侯に任じた』とする。",
    }],
}

DUMMY_INPUT = {
    "source_text": "威烈王二十三年。初命晉大夫魏斯、趙籍、韓虔為諸侯。",
    "hu_notes": ["魏斯・趙籍・韓虔は晉の三家の大夫なり。命じて諸侯と為す。"],
    "translation": "威烈王の二十三年、周王は、晋の大夫である魏斯・趙籍・韓虔の三人を、"
                   "彼らの長年にわたる忠誠を高く評価して、諸侯に取り立てた。",
}


class ReviewError(Exception):
    """レビュー実行・パース・検証の失敗。"""


def _findings_digest(prev_findings: list[dict]) -> str:
    """前ラウンド findings を再レビュー用に1件1行へ要約。"""
    lines = []
    for f in prev_findings:
        if not isinstance(f, dict):
            continue
        sev = f.get("severity", "?")
        span = (f.get("translated_span") or f.get("source_span") or "").strip()
        issue = (f.get("issue") or "").strip()
        lines.append(f"- [{sev}] {span} … {issue}")
    return "\n".join(lines) if lines else "(なし)"


def build_review_prompt(source_text: str, hu_notes: list[str], translation: str, *,
                        continuity_text: str | None = None,
                        prev_findings: list[dict] | None = None) -> str:
    """レビュー・プロンプト組立。

    continuity_text: 同年の直前チャンクの確定訳(巻内連続性の根拠)。ここで確立済みの
        人物同定・地名・続柄は根拠集合の一部として扱い、捏造判定から除外させる。
    prev_findings: 前ラウンドの指摘(再レビュー時)。再litigation(同一箇所の蒸し返し)を抑止し、
        ①既出指摘の解消 ②新たな実質的誤り の2点に集中させる。独立判断は維持する。
    """
    notes_block = "(なし)" if not hu_notes else "\n".join(f"- {n}" for n in hu_notes)
    parts = [
        CONTRACT,
        "",
        "# 出典(根拠集合) = 本文原文 + 胡三省注",
        "## 本文原文",
        source_text,
        "",
        "## 胡三省注",
        notes_block,
        "",
    ]
    if continuity_text:
        parts += [
            "## 巻内連続コンテキスト(根拠集合の一部・直前チャンクの確定訳)",
            "※ ここで既に確立した人物同定・地名・続柄(例: 別名・分家後の姓・前出地名)は"
            "根拠集合に含まれるものとして扱い、当該チャンク本文に明示が無くても捏造としないこと。",
            continuity_text,
            "",
        ]
    parts += [
        "# 被レビュー訳文(現代日本語・口語超訳)",
        translation,
        "",
    ]
    if prev_findings:
        parts += [
            "# 前ラウンドの指摘(修正済みのはず・再レビュー)",
            _findings_digest(prev_findings),
            "※ 上記は前回の独立レビュアーの指摘。①これらが解消されたか ②新たな**実質的**誤りがないか"
            "に集中せよ。既に妥当に修正済みの箇所や、表現を変えただけの同義箇所を蒸し返さないこと。",
            "",
        ]
    parts.append(INSTRUCTION)
    return "\n".join(parts) + "\n"


def validate_review(obj) -> list[str]:
    """research/02-review-schema.json 専用の軽量バリデータ。エラー文字列のリストを返す(空=合格)。"""
    errs: list[str] = []
    if not isinstance(obj, dict):
        return [f"root is {type(obj).__name__}, expected object"]
    extra = set(obj) - {"verdict", "findings"}
    if extra:
        errs.append(f"root に未知キー: {sorted(extra)}")
    if obj.get("verdict") not in VERDICT:
        errs.append(f"verdict 不正: {obj.get('verdict')!r} (許可: {sorted(VERDICT)})")
    findings = obj.get("findings")
    if not isinstance(findings, list):
        errs.append("findings が配列でない")
        return errs
    for i, f in enumerate(findings):
        if not isinstance(f, dict):
            errs.append(f"findings[{i}] が object でない")
            continue
        missing = FINDING_KEYS - set(f)
        if missing:
            errs.append(f"findings[{i}] 欠落キー: {sorted(missing)}")
        extra = set(f) - FINDING_KEYS
        if extra:
            errs.append(f"findings[{i}] 未知キー: {sorted(extra)}")
        if f.get("severity") not in SEVERITY:
            errs.append(f"findings[{i}].severity 不正: {f.get('severity')!r}")
    return errs


def _invoke_codex(prompt: str, schema_path: Path, out_path: Path, timeout: int, effort: str) -> None:
    """codex exec を独立セッションで起動し out_path に最終 JSON を書かせる。失敗は ReviewError。"""
    cmd = [
        "codex", "exec",
        "-s", "read-only",
        "-c", "approval_policy=never",
        "-c", f"model_reasoning_effort={effort}",
        "--output-schema", str(schema_path),
        "--output-last-message", str(out_path),
        "-",  # プロンプトは stdin
    ]
    try:
        proc = subprocess.run(
            cmd, input=prompt, capture_output=True, text=True, timeout=timeout,
        )
    except FileNotFoundError as e:
        raise ReviewError(f"codex CLI が見つからない: {e}") from e
    except subprocess.TimeoutExpired as e:
        raise ReviewError(f"codex タイムアウト ({timeout}s)") from e
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-500:]
        raise ReviewError(f"codex 非ゼロ終了 ({proc.returncode}): {tail}")
    if not out_path.exists() or not out_path.read_text(encoding="utf-8").strip():
        raise ReviewError("codex が出力ファイルを生成しなかった")


def parse_output(out_path: Path) -> dict:
    """出力ファイルを JSON パース + スキーマ検証。失敗は ReviewError。"""
    raw = out_path.read_text(encoding="utf-8")
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ReviewError(f"JSON パース失敗: {e}; 先頭 200 字: {raw[:200]!r}") from e
    errs = validate_review(obj)
    if errs:
        raise ReviewError("スキーマ不適合: " + "; ".join(errs))
    return obj


def run_review(source_text: str, hu_notes: list[str], translation: str, *,
               continuity_text: str | None = None, prev_findings: list[dict] | None = None,
               schema_path: Path = SCHEMA_PATH, timeout: int = 300, retries: int = 2,
               effort: str = "medium", dummy: bool = False, out_path: Path | None = None) -> dict:
    """レビューを実行し {verdict, findings, _meta} を返す。

    _meta はハーネス側メタ情報(スキーマ外)。実 Codex 呼び出しは dummy=False のとき。
    continuity_text / prev_findings は誤検出・再litigation抑止用(build_review_prompt 参照)。
    timeout / 非ゼロ終了 / 出力欠落 / JSON パース / スキーマ不適合 を retries 回まで再試行する。
    """
    prompt = build_review_prompt(source_text, hu_notes, translation,
                                 continuity_text=continuity_text, prev_findings=prev_findings)
    tmp = None
    if out_path is None:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        tmp.close()
        out_path = Path(tmp.name)

    attempts = 0
    last_err: Exception | None = None
    t0 = time.time()
    try:
        for attempts in range(1, retries + 2):
            try:
                if dummy:
                    out_path.write_text(json.dumps(DUMMY_OUTPUT, ensure_ascii=False), encoding="utf-8")
                else:
                    _invoke_codex(prompt, schema_path, out_path, timeout, effort)
                review = parse_output(out_path)
                review["_meta"] = {
                    "reviewer": "dummy" if dummy else f"codex/{effort}",
                    "attempts": attempts,
                    "elapsed_s": round(time.time() - t0, 2),
                    "independent_session": True,
                }
                return review
            except ReviewError as e:
                last_err = e
                if attempts <= retries:
                    time.sleep(min(2 ** (attempts - 1), 10))  # 1s, 2s, 4s... 上限 10s
        raise ReviewError(f"レビュー {attempts} 回試行後も失敗: {last_err}")
    finally:
        if tmp is not None:
            try:
                Path(tmp.name).unlink()
            except OSError:
                pass


def main() -> int:
    ap = argparse.ArgumentParser(description="独立クロスベンダー・レビュー(codex exec ラッパ)")
    ap.add_argument("--input", help='JSON: {"source_text","hu_notes":[],"translation"}')
    ap.add_argument("--dummy", action="store_true", help="codex を呼ばず配線のみ検証(レート消費なし)")
    ap.add_argument("--print-prompt", action="store_true", help="プロンプトのみ表示して終了")
    ap.add_argument("--schema", default=str(SCHEMA_PATH))
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--effort", default="medium", choices=["minimal", "low", "medium", "high"])
    ap.add_argument("--out", help="codex 出力 JSON の保存先(省略時は一時ファイル)")
    args = ap.parse_args()

    if args.input:
        data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    elif args.dummy:
        data = DUMMY_INPUT
    else:
        ap.error("--input か --dummy のいずれかが必要")

    src = data["source_text"]
    notes = data.get("hu_notes", [])
    tr = data["translation"]
    continuity = data.get("continuity_text")
    prev_findings = data.get("prev_findings")

    if args.print_prompt:
        print(build_review_prompt(src, notes, tr,
                                  continuity_text=continuity, prev_findings=prev_findings))
        return 0

    try:
        review = run_review(
            src, notes, tr,
            continuity_text=continuity, prev_findings=prev_findings,
            schema_path=Path(args.schema), timeout=args.timeout, retries=args.retries,
            effort=args.effort, dummy=args.dummy,
            out_path=Path(args.out) if args.out else None,
        )
    except ReviewError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(review, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

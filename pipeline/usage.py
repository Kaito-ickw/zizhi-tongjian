#!/usr/bin/env python3
"""Claude Code のローカルセッションログから 5h ローリング枠の使用量を推定する。

レート上限の残量ゲージは API レスポンスヘッダにあり、Claude(モデル)自身からは
見えない。そこで運用は「アンカー + 補間」方式を採る:
  - アンカー = ユーザーが `/status` で読んだ「使用%」(=真値)。
  - 補間    = ローカルログの重み付きトークン和(本スクリプト)でアンカー間を埋める。
こうして 5h 枠の 90% ソフト上限まで自律運用する(ハード床は口座側の超過上限$0)。

設計上の保守バイアス(いずれも「早めに停止」=安全側):
  - 5h ローリング窓: 古い消費は時間で枠が回復するが、和は単調増加寄りに見える。
  - 重み付け: 全トークン種(input/output/cache_creation/cache_read)を満額カウント。
    キャッシュ読みは実コスト安だが満額で数える → 過大評価 → 早めに停止。
  - account スコープでも claude.ai 等 web 利用は捕捉外 → その時は再アンカー。

使い方:
  python3 pipeline/usage.py now                # 直近5hの重み付きトークン和(+内訳)
  python3 pipeline/usage.py anchor 30          # 「今=30%使用」として較正(tokens/% 保存)
  python3 pipeline/usage.py estimate           # 較正値から現在の推定使用%
  python3 pipeline/usage.py estimate --cap 90  # 90%まで残り何ポイントか/停止可否
オプション:
  --window-hours 5         ローリング窓(既定5)
  --scope account|project  集計範囲(既定 account = 全 Claude Code プロジェクト)
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECTS = Path.home() / ".claude" / "projects"
THIS_PROJECT = "-home-kaito-projects-zizhi-tongjian"
ANCHOR_FILE = Path(__file__).resolve().parent.parent / "data" / "staging" / "usage_anchor.json"

# 重み付け = レート消費の代理として Opus の課金比(input 等価)を用いる。
# 満額カウント(全種=1.0)は cache_read が支配的で混在比に過敏になり、
# アンカーより cache_read の薄いワークロードで推定%を過小評価=90%超過の危険があるため不採用。
# 価格比(input:1 / output:5 / cache_write:1.25 / cache_read:0.1)で実消費に追従させる。
TOKEN_WEIGHTS = {
    "input_tokens": 1.0,
    "output_tokens": 5.0,
    "cache_creation_input_tokens": 1.25,
    "cache_read_input_tokens": 0.1,
}
TOKEN_FIELDS = tuple(TOKEN_WEIGHTS)


def _log_files(scope: str):
    if scope == "project":
        return sorted(glob.glob(str(PROJECTS / THIS_PROJECT / "*.jsonl")))
    return sorted(glob.glob(str(PROJECTS / "*" / "*.jsonl")))


def _parse_ts(s: str) -> datetime | None:
    if not s:
        return None
    try:
        # "2026-06-22T13:08:19.413Z"
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def rolling_sum(window_hours: float, scope: str) -> dict:
    """直近 window_hours の重み付きトークン和と内訳を返す。"""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=window_hours)
    totals = {f: 0 for f in TOKEN_FIELDS}
    weighted = 0.0
    msgs = 0
    for fp in _log_files(scope):
        try:
            with open(fp, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or '"usage"' not in line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ts = _parse_ts(obj.get("timestamp", ""))
                    if ts is None or ts < cutoff:
                        continue
                    msg = obj.get("message")
                    if not isinstance(msg, dict):
                        continue
                    usage = msg.get("usage")
                    if not isinstance(usage, dict):
                        continue
                    for f in TOKEN_FIELDS:
                        v = usage.get(f) or 0
                        if isinstance(v, int):
                            totals[f] += v
                            weighted += v * TOKEN_WEIGHTS[f]
                    msgs += 1
        except OSError:
            continue
    return {
        "now": now.isoformat(),
        "window_hours": window_hours,
        "scope": scope,
        "messages": msgs,
        "by_field": totals,
        "weighted_tokens": weighted,
    }


def _fmt_int(n: int) -> str:
    return f"{n:,}"


def cmd_now(args) -> int:
    r = rolling_sum(args.window_hours, args.scope)
    print(f"[usage] 直近 {r['window_hours']}h / scope={r['scope']} / messages={r['messages']}")
    for f in TOKEN_FIELDS:
        print(f"  {f:30s} {_fmt_int(r['by_field'][f]):>14s}  (x{TOKEN_WEIGHTS[f]})")
    print(f"  {'weighted_tokens(価格比)':30s} {_fmt_int(int(r['weighted_tokens'])):>14s}")
    return 0


def cmd_anchor(args) -> int:
    pct = float(args.percent)
    if not (0 < pct <= 100):
        print("anchor% は 0<pct<=100 で指定してください", file=sys.stderr)
        return 2
    r = rolling_sum(args.window_hours, args.scope)
    s0 = r["weighted_tokens"]
    if s0 <= 0:
        print("直近窓のトークン和が 0。窓を広げるか、少し動かしてから較正してください", file=sys.stderr)
        return 1
    tpp = s0 / pct  # tokens per 1%
    ANCHOR_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "anchored_at": r["now"],
        "anchor_pct": pct,
        "window_hours": args.window_hours,
        "scope": args.scope,
        "s0_weighted_tokens": s0,
        "tokens_per_pct": tpp,
    }
    ANCHOR_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[anchor] now={pct:.1f}% used / s0={_fmt_int(int(s0))} weighted tokens")
    print(f"[anchor] tokens_per_pct={tpp:,.0f} → {ANCHOR_FILE}")
    print("  ※ 他プロジェクト/claude.ai を挟んだら再アンカー(/status を読み直して anchor し直す)")
    return 0


def cmd_estimate(args) -> int:
    if not ANCHOR_FILE.exists():
        print("未較正。先に `python3 pipeline/usage.py anchor <pct>` を実行してください", file=sys.stderr)
        return 1
    a = json.loads(ANCHOR_FILE.read_text(encoding="utf-8"))
    tpp = a["tokens_per_pct"]
    window = a.get("window_hours", args.window_hours)
    scope = a.get("scope", args.scope)
    r = rolling_sum(window, scope)
    s1 = r["weighted_tokens"]
    est = s1 / tpp if tpp > 0 else 0.0
    print(f"[estimate] アンカー: {a['anchor_pct']:.1f}% @ {a['anchored_at']} (window={window}h, scope={scope})")
    print(f"[estimate] 現在の重み付きトークン和 s1={_fmt_int(int(s1))} (tokens_per_pct={tpp:,.0f})")
    print(f"[estimate] 推定使用率 ≈ {est:.1f}%")
    cap = args.cap
    remain = cap - est
    print(f"[estimate] 上限 {cap:.0f}% まで残り {remain:.1f} ポイント", end="")
    if remain <= 0:
        print("  → STOP(これ以上の波を投げない)")
        return 3  # 呼び出し側が「停止」を検知できるよう非0
    print("  → GO(波コストが残ポイント以内なら投入可)")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--window-hours", type=float, default=5.0)
    p.add_argument("--scope", choices=("account", "project"), default="account")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("now")
    pa = sub.add_parser("anchor")
    pa.add_argument("percent")
    pe = sub.add_parser("estimate")
    pe.add_argument("--cap", type=float, default=90.0)
    args = p.parse_args()
    cmd = args.cmd or "now"
    if cmd == "now":
        return cmd_now(args)
    if cmd == "anchor":
        return cmd_anchor(args)
    if cmd == "estimate":
        return cmd_estimate(args)
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

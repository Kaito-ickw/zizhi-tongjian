#!/usr/bin/env python3
"""維基文庫「資治通鑒 (胡三省音注)」全294巻の取り込み(セグメント層)。

- MediaWiki Action API から各巻の wikitext を取得し revid を固定する。
- 出力: data/raw/wikisource/卷NNN.wikitext + 卷NNN.meta.json(再開可能)
- 集約: pipeline/manifests/wikisource.manifest.json
- 礼儀: 説明的 User-Agent / 低頻度 / 429・503 は Retry-After を尊重して指数バックオフ。

DESIGN §9(セグメント層)・検証① research/01-ctext-knockout.md を参照。
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://zh.wikisource.org/w/api.php"
UA = "ZizhiTongjianTranslationBot/0.1 (non-commercial research; contact: kaito52110@gmail.com)"
TITLE_FMT = "資治通鑒 (胡三省音注)/卷{:03d}"
JUAN_RANGE = range(1, 295)  # 卷001 .. 卷294

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "raw" / "wikisource"
MANIFEST = ROOT / "pipeline" / "manifests" / "wikisource.manifest.json"

BASE_DELAY = 1.0       # 通常リクエスト間隔(秒)
MAX_RETRIES = 6


def api_get(params: dict) -> dict:
    """1 リクエスト。429/5xx は Retry-After 尊重 + 指数バックオフで再試行。"""
    qs = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    url = f"{API}?{qs}"
    delay = 2.0
    for attempt in range(1, MAX_RETRIES + 1):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < MAX_RETRIES:
                ra = e.headers.get("Retry-After")
                wait = float(ra) if (ra and ra.isdigit()) else delay
                print(f"  HTTP {e.code} -> wait {wait:.0f}s (attempt {attempt})", flush=True)
                time.sleep(wait)
                delay = min(delay * 2, 60)
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < MAX_RETRIES:
                print(f"  net error {e} -> wait {delay:.0f}s (attempt {attempt})", flush=True)
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue
            raise
    raise RuntimeError("unreachable")


def fetch_juan(n: int) -> dict:
    title = TITLE_FMT.format(n)
    data = api_get({
        "action": "query",
        "format": "json",
        "formatversion": "2",
        "prop": "revisions",
        "rvslots": "main",
        "rvprop": "ids|timestamp|size|content",
        "titles": title,
        "redirects": "1",
    })
    pages = data.get("query", {}).get("pages", [])
    if not pages:
        raise RuntimeError(f"no pages for {title}")
    page = pages[0]
    if page.get("missing"):
        raise RuntimeError(f"MISSING page: {title}")
    rev = page["revisions"][0]
    content = rev["slots"]["main"]["content"]
    return {
        "juan": n,
        "title": page["title"],
        "pageid": page["pageid"],
        "revid": rev["revid"],
        "parentid": rev.get("parentid"),
        "timestamp": rev["timestamp"],
        "size": rev.get("size"),
        "note_template_count": content.count("{{*|"),
        "chars": len(content),
        "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "content": content,
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)

    entries: list[dict] = []
    errors: list[str] = []
    fetched = skipped = 0

    for n in JUAN_RANGE:
        wt_path = OUT_DIR / f"卷{n:03d}.wikitext"
        meta_path = OUT_DIR / f"卷{n:03d}.meta.json"
        if wt_path.exists() and meta_path.exists() and wt_path.stat().st_size > 0:
            entries.append(json.loads(meta_path.read_text(encoding="utf-8")))
            skipped += 1
            continue
        try:
            rec = fetch_juan(n)
        except Exception as e:  # noqa: BLE001
            msg = f"卷{n:03d}: {e}"
            print(f"ERROR {msg}", flush=True)
            errors.append(msg)
            time.sleep(BASE_DELAY)
            continue
        content = rec.pop("content")
        wt_path.write_text(content, encoding="utf-8")
        meta_path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        entries.append(rec)
        fetched += 1
        print(f"OK 卷{n:03d} revid={rec['revid']} chars={rec['chars']} notes={rec['note_template_count']}", flush=True)
        time.sleep(BASE_DELAY)

    entries.sort(key=lambda r: r["juan"])
    manifest = {
        "source_id": "wikisource-zh-zztj-husanxing",
        "role": "segment_layer (標点 + 論理注境界)",
        "api": API,
        "base_title": "資治通鑒 (胡三省音注)",
        "license": "CC-BY-SA-4.0",
        "retrieved_at": time.strftime("%Y-%m-%d"),
        "juan_count": len(entries),
        "expected": 294,
        "complete": len(entries) == 294 and not errors,
        "total_chars": sum(r["chars"] for r in entries),
        "total_notes": sum(r["note_template_count"] for r in entries),
        "errors": errors,
        "juan": [{k: r[k] for k in ("juan", "title", "pageid", "revid", "timestamp", "size", "chars", "note_template_count", "sha256")} for r in entries],
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== SUMMARY ===", flush=True)
    print(f"fetched={fetched} skipped={skipped} errors={len(errors)} total={len(entries)}/294", flush=True)
    print(f"total_chars={manifest['total_chars']} total_notes={manifest['total_notes']}", flush=True)
    print(f"manifest -> {MANIFEST.relative_to(ROOT)}", flush=True)
    return 1 if (errors or len(entries) != 294) else 0


if __name__ == "__main__":
    sys.exit(main())

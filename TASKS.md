# TASKS — 1タスク=1セッション

運用は `CLAUDE.md` の再開プロトコル参照。**最初の `[ ]` を1つだけ**実施 → `[x]` 化 + 結果1行 → commit → 停止。
印: `[Claude]`=Claude/ローカルのみ / `[Codex]`=実行に Codex レート必要 / `[agy]`=agy 委譲可。

---

## [x] T00 — 基盤・着手前検証・データ取込・B・C
結果: 設計§1-10確定 / 検証①②③ / Kanripo+維基文庫 全294巻pin / 年分割1,397・チャンク2,096 / B西暦(巻レベル) / Cエンティティ辞書seed(人物75k/官職34k/地名13k)。commit 866c073..d6f2588。

## [x] T01 — コンテキストパケット組立 `pipeline/context.py` [Claude]
結果: context.py 実装。chunk_id→位置(巻/section/年/西暦)/本文/胡注/エンティティ候補集合/直前確定訳。name_index 最長一致スキャン + 西暦窓フィルタ(±80年)+ min-len2 + confidence(dated/office/provisional)。諸葛亮/魏郡/太守 解決確認、c01 は 205→37 表記に抑制。約1.3s。
- Goal: chunk_id を入力に翻訳用コンテキストを JSON 化 — 位置(巻/section/年/西暦)、本文中に出現する人物/官職/地名の候補(`dict/name_index.jsonl` 照合・候補集合)、当該チャンクの胡注、直前チャンクの確定訳(あれば)。
- Done: `python3 pipeline/context.py j001_y01_c01` がコンテキスト JSON を出力。name_index 照合が動く(諸葛亮/太守 等がヒット)。
- Notes: name_index は12万行。起動毎ロードが重ければ sqlite 化 or 最長一致スキャンを工夫。Codex 不使用。

## [x] T02 — レビュー・ハーネス `pipeline/review.py` [Claude](実行のみ[Codex])
結果: review.py 実装。codex exec ラッパ(read-only / approval_policy=never / --output-schema / stdin プロンプト・毎回独立セッション)+ 品質契約プロンプト(DESIGN §2)+ 02-review-schema.json 専用の軽量バリデータ(pip 無し)。timeout / retries(指数バックオフ)/ JSON パース失敗 / スキーマ不適合 を処理。--dummy で配線(生成→模擬→パース→検証)合格、Codex レート未消費。実 Codex 呼び出しは T04 で。
- Goal: `codex exec` をラップし、出典(本文原文+胡三省注)+訳文+品質契約(DESIGN §2)を渡してレビュー JSON(`research/02-review-schema.json` 準拠)を返す関数/CLI。独立セッション・`approval_policy=never`・`read-only`・`--output-schema`。
- Done: ダミー入力で schema 準拠 JSON をパースして返す(実 Codex 呼び出しはレート確認後で可、まずは配線完成)。タイムアウト/失敗リトライ/JSON パース失敗処理を実装。

## [x] T03 — 翻訳KB出力スキーマ + 翻訳ループ雛形 `pipeline/translate_loop.py` [Claude]
結果: translate_loop.py 実装。年/チャンクの確定 KB スキーマ(訳文/review_history/iterations/status=pending|in_progress|pass|halt + halt_reason)定義。最大3反復ループ(翻訳=Claude注入点 / レビュー=review.py)+ 矛盾検出(detect_contradiction)で pass/未収束/矛盾→halt。--selftest 3ケース合格、--init-sample で data/kb/_sample_record.json(空レコード)+ _LOOP.md(手順書, DESIGN §4整合)生成。
- Goal: 確定レコードの最終スキーマ(訳文/レビュー履歴/反復回数/status=pass|halt)を `data/kb/` 用に定義。翻訳=Claude(セッション内)、レビュー=Codex、最大3反復・矛盾/未収束は停止アラート(DESIGN §4)のループ手順を文書化+雛形。
- Done: `data/kb/` のサンプル空レコード + ループ手順書(DESIGN §4 と整合)。

## [ ] T04 — 縦スライス: `j001_y01` 翻訳→レビュー実走 [Codex]
- Goal: 威烈王二十三年(3チャンク)を コンテキスト→翻訳(Claude)→Codexレビュー→修正→再レビュー で1レコード完成させる。
- Done: `data/kb/` に j001_y01 の確定訳(品質基準合格 or 停止アラート)+ レビュー履歴。**Codex レート必要**。

## [ ] T05 — 翻訳バッチ: 卷001 全年(30年) [Codex]
- Goal: T04 のループで卷001 の全年レコードを確定。1セッションで収まらなければ年単位に分割して積み直す。
- Done: `data/kb/卷001/` に全年の確定訳。

---

## TODO(順不同・随時着手可)
## [ ] T-s2t — 地名 s2t 適用(opencc 導入後 `build_dict.py` 再実行) [Claude]
- pip 不可のため venv か npm `opencc-js` か。導入後 `place_s2t_applied:true` を確認。

## [ ] T-year — 巻内の年単位西暦(在位表ベース) [agy/Claude]
- 元号・ルーラー別在位開始年表を整備し year_record.western_year を埋める。数値=要検証。

## [ ] T-xcheck — Wikisource × Kanripo クロスチェック [agy/Claude]
- 同一巻の本文/注を両ソースで突き合わせ、欠落・異読を検出してレポート。

## [ ] T-jiankan — 後世校勘レイヤ判別 [Claude]
- 胡注内/本文中の後世校勘(「章：十二行本…」「孔本同」等)を分類し翻訳対象外メタへ。

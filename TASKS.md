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

## [x] T04 — 縦スライス: `j001_y01` 翻訳→レビュー実走 [Codex]
結果: 威烈王二十三年3チャンクを context→翻訳(Claude)→Codex独立レビュー(codex/medium・毎回独立セッション)→修正→再レビューで実走(計9 Codex 呼び出し)。`data/kb/卷001/j001_y01.json` 生成。**c01=pass(3反復で収束)**、**c02/c03=halt(max_iter_unconverged)**。各ラウンドで実質的誤りを検出・修正(臣聞の意訳/微子・季札の反実仮想逆転/鬢→髭/三失→何度も/鎔範に「鍛え」追加/卜相=占い誤解/疽→膿の特定 等、計18件)。残存は軽微(輔果=智果の巻内連続同定、膿/疽の特定、因果の「すると」)。**知見**: チャンク単独レビューは正しい巻内連続性(輔果=智果・晋陽・兄伯魯)を「根拠集合外」と弾く / 敵対的レビュアーが独立セッションごとに新しい微細指摘を出し続け3反復で収束しにくい(DESIGN 決定ログに記録、要方針判断 → T-review-policy)。**→ 後続 T-review-policy 適用後の R4 再レビューで c02/c03 とも pass。j001_y01 は全チャンク pass・年 pass で確定。**
- Goal: 威烈王二十三年(3チャンク)を コンテキスト→翻訳(Claude)→Codexレビュー→修正→再レビュー で1レコード完成させる。
- Done: `data/kb/` に j001_y01 の確定訳(品質基準合格 or 停止アラート)+ レビュー履歴。**Codex レート必要**。

## T05 — 翻訳バッチ: 卷001 全年(30年) [Codex]
- Goal: T04 のループで卷001 の全年レコードを確定。**1セッションに収まらないため年単位バッチに分割**(下記 T05a–T05d)。y01 は T04 で確定済み。
- Done: `data/kb/卷001/` に全30年の確定訳(T05a–T05d 全て `[x]`)。

### [x] T05a — 卷001 y02–y08 翻訳→レビュー [Codex]
結果: j001_y02〜y08(7年・各1チャンク)を context→翻訳(Claude)→Codex/low 独立レビューで実走。**全7年 pass**。6年は R1 で pass、y07(聶政の刺殺・203字)のみ R1 で 2件 forbidden(『亡骸にすがって』『みずから死んだ』=本文/胡注に無い行為・死因の付加)を検出→修正し R2(別独立セッション)で pass。Codex 呼び出し計8回。`data/kb/卷001/j001_y02.json`〜`y08.json` 生成。
- 対象: j001_y02〜y08(7年・各1チャンク、全て短文)。context→翻訳(Claude)→Codexレビュー→修正→再レビュー(最大3反復)。
- Done: `data/kb/卷001/j001_y02.json`〜`j001_y08.json`(各 pass、halt なら年アラート)。

### [ ] T05b — 卷001 y09–y14 翻訳→レビュー [Codex]
- 対象: j001_y09〜y14(6年・各1チャンク、y14=695字が大)。
- Done: `data/kb/卷001/j001_y09.json`〜`j001_y14.json`。

### [ ] T05c — 卷001 y15–y23 翻訳→レビュー [Codex]
- 対象: j001_y15〜y23(9年・各1チャンク、y23=485字が大)。
- Done: `data/kb/卷001/j001_y15.json`〜`j001_y23.json`。

### [ ] T05d — 卷001 y24–y30 翻訳→レビュー [Codex]
- 対象: j001_y24〜y30(7年・各1チャンク、y29=270/y30=248字が大)。
- Done: `data/kb/卷001/j001_y24.json`〜`j001_y30.json`。

---

## TODO(順不同・随時着手可)
## [x] T-view — 閲覧ビュー生成 `pipeline/build_view.py`(最小構成・巻1) [Codex]
結果: 実装を Codex 委譲(`codex exec -s workspace-write`、ユーザー指示 §3)。`pipeline/build_view.py`(stdlib のみ・冪等・決定論的)が `data/kb/卷NNN/*.json`(status=pass)→ `docs/卷NNN/jNNN_yNN.md` を生成。各年=オリエン(巻/紀/年号/巻範囲西暦+年単位西暦は T-year 待ちで未確定明記)+ 訳文本文(`translation_full` 無改変)+ `<details>` 原文(`⟦nK⟧`/`'''`/行頭`:`/丸数字を清掃)+ 出典フッタ + 前後年/巻indexナビ。マスター+巻別 README も生成。巻1の確定8年(y01–y08)= 10ファイル出力。Claude 独立検証: 本文全件無改変・端ナビ正・**2回実行でハッシュ一致(冪等)**。`docs/` は tracked(§11 甲)。entity リンクは延期(§11、無名人物密集巻で要否判定)。
- Goal: `data/kb/卷NNN/*.json`(status=pass)→ `docs/卷NNN/jNNN_yNN.md` を生成(DESIGN §11)。各ファイル=① 冒頭オリエンテーション(巻/年号/西暦/全体内位置)② 訳文本文(`〔注:…〕` インライン・臣光曰ブロック)③ ナビ(前年/次年 + 巻インデックスへ戻る)。原文は `<details>` で畳む。マスター+巻別インデックス生成。レンダラは冪等。`docs/` は **tracked**(§11 甲=生成データ gitignore の例外)。
- Done: `python3 pipeline/build_view.py` で巻1の確定年(現状 y01–y08)が `docs/卷001/` に出力され、GitHub 上で前後リンク・インデックスを辿って通読できる。entity リンクは無し(§11 で延期)。
- Notes: 実装は **Codex 委譲**(ユーザー指示 §3)。確定済み(pass)年のみ出力。entity リンクは「無名人物密集巻を1つ読んでから」判定(§11 サンプリング地雷)。

## [x] T-review-policy — レビュー合格判定の方針見直し(T04 知見、T05 の前提) [Claude/ユーザー承認済]
結果: §4 改訂 + 実装。(1) 根拠集合に巻内連続コンテキスト(直前チャンク確定訳=`continuity_text`)を追加し誤検出①を解消。(2) forbidden を「根拠集合に無い事実・因果・心理・数値・発言の新規追加」に限定し、翻訳上の自然な具体化は allowed と明記して過剰検出②を解消。(3) 再レビューに前ラウンド findings(`prev_findings`)を同梱し再litigation抑止。(4) 合格ゲートは verdict=pass のみ維持。`review.py`/`translate_loop.py` 反映、selftest/dummy 合格。効果検証: 旧方針 halt の j001_y01 c02/c03 を新方針で再レビュー→両方 pass。`data/kb/卷001/j001_y01.json` を全チャンク pass・年 pass に更新(R1-3旧+R4新を監査保持)。
- 課題①: チャンク単独レビューが正しい巻内連続性(輔果=智果・晋陽・兄伯魯)を「根拠集合外」と弾く → レビュアーへ**直前チャンク確定訳/巻内既出エンティティ**も根拠として渡すか検討。
- 課題②: 「誤りがある前提」の独立セッションが毎回新しい微細指摘を出し3反復で収束しにくい → 案: (a) 前ラウンドの findings をレビュアーに提示し再litigationを抑止 / (b) severity を厳格に運用し forbidden の実質性で pass 判定 / (c) max_iter を長文チャンクで引上げ / (d) 軽微指摘は style 扱い。
- Done: 方針を DESIGN §4 に確定追記 + review.py/translate_loop.py 反映。

## [x] T-s2t — 地名 s2t 適用(opencc 導入後 `build_dict.py` 再実行) [Claude]
結果: `python3 -m venv .venv` + opencc(PyPI `OpenCC` 1.3.1)を `.venv` に導入(システム python は pip 不可のため venv 採用、npm opencc-js は不採用)。`.venv/bin/python pipeline/build_dict.py` 再実行で `place_s2t_applied:true`。地名の繁体字索引が生成され `name_index_surfaces` 120,928→128,783、`ambiguous_surfaces` 17,730→21,064。繁体字本文との照合を確認(長安/廣陵 等の繁体字 surface が place 候補にヒット、簡体字 surface も保持)。`.gitignore` に `.venv/` 追加。再現手順は `.venv/bin/python pipeline/build_dict.py`。
- pip 不可のため venv か npm `opencc-js` か。導入後 `place_s2t_applied:true` を確認。

## [x] T-year — 巻内の年単位西暦(在位表ベース) [Codex実装/Claude検証]
結果: 実装を **Codex 委譲**(メモリ方針)。`pipeline/year_western.py`(stdlib・決定論的・冪等・LLM不使用)が `data/kb/卷NNN/jNNN_yMM.json` の `western_year` を埋める。一次根拠は husanxing **年頭注の `（干支、前NNN）`**(例 `（戊寅、前四○三）`)。位取り漢数字パーサ `cn_positional2int` を追加、干支算出/西暦変換は `western_years.py` を再利用。**多重検証**: 干支×astro / 巻範囲(`volume_years.json`) / 同巻連番+1 / ルーラー別在位整合 → 全件 0 違反。在位表(マニフェスト `manifests/year_western.json`)= 威烈王元年 425 BCE・安王元年 401 BCE。巻1の8年= 403→396 BCE。Claude 独立検証: 差分は western_year のみ(null→値8件)・**2回実行でバイト一致(冪等)**・**独立アンカー(1984=甲子)再計算+胡注literal**と全8件一致。`build_view.py` 再生成で docs に年単位西暦反映(「未確定」注除去)。

## [ ] T-xcheck — Wikisource × Kanripo クロスチェック [agy/Claude]
- 同一巻の本文/注を両ソースで突き合わせ、欠落・異読を検出してレポート。

## [ ] T-jiankan — 後世校勘レイヤ判別 [Claude]
- 胡注内/本文中の後世校勘(「章：十二行本…」「孔本同」等)を分類し翻訳対象外メタへ。

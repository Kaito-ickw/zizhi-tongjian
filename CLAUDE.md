# 資治通鑑 翻訳プロジェクト — セッション指針

資治通鑑(全294巻・約300万字)を現代日本語の平易な口語超訳でナレッジベース化する。
実行系: **Claude=翻訳/オーケストレーション**, **Codex(`codex exec`)=独立クロスベンダー・レビュー + 実装 + 画像生成(built-in `image_gen`)**, **agy(Gemini, `agy -p`)=ワンショット実装/機械的検証/画像生成(nano-banana)**。
- **レート方針(2026-06-26)**: Claude レートが律速なので**翻訳本体だけ Claude**に残し、周辺(pipeline/検証/画像同期/マージ/調査)は Codex/agy へ寄せる(詳細 DESIGN §3)。

- 設計の正本: **DESIGN.md**(§1-10 + 決定ログ)。作業前に関連箇所を必ず参照。
- 翻訳キュー: **`python3 pipeline/translation_queue.py next`**。staging と `data/kb/` の実状態から次の翻訳バッチを決める。
- 保守タスク: **TASKS.md**(翻訳以外。明示されたときだけ使う)。
- 調査根拠: `research/`、データ来歴: `pipeline/manifests/`、辞書: `dict/`。

## 翻訳再開プロトコル(ユーザーが「再開して」「翻訳再開して」と言ったら)
**Claude は翻訳本体と Codex review 指摘の反映に集中する。** 次対象の判断に TASKS.md は使わない。
1. `python3 pipeline/translation_queue.py check` を実行する。
   - `previous_year` が FAIL: stale worktree / continuity 欠落の疑い。翻訳せず停止。
   - `target_outputs_absent` が FAIL: 既存 KB との衝突。翻訳せず停止。
   - `worktree_clean_for_translation` が FAIL: 未コミット差分を確認し、翻訳を混ぜない。
2. check が OK なら `python3 pipeline/translation_queue.py next` で表示された **1バッチだけ**翻訳する。
   - 対象年・チャンク・continuity source は queue 出力を正とする。
   - `pipeline/context.py <chunk_id>` で翻訳パケットを取り、Claude が口語超訳を生成する。
   - `pipeline/review.py --input ... --effort low` で Codex 独立レビュー。fail の場合は findings を反映し、前ラウンド findings 同梱で別セッション再レビュー。
3. バッチ内の全チャンクが pass したら、年レコードを `data/kb/卷NNN/jNNN_yMM.json` に保存する。
4. 決定論的な後処理だけ実行する: `python3 pipeline/year_western.py`、`python3 pipeline/build_view.py`。
5. 変更を git コミット(メッセージ末尾に `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`)。
6. 停止し、「完了した翻訳バッチ / 次の翻訳バッチ」を1行ずつ報告して終わる。

- 翻訳中に設計判断・校勘分類・画像・保守 TODO が見えても、翻訳品質に直結しない限り着手しない。必要なら保守タスクとしてメモし、翻訳バッチを完了して停止する。
- `python3 pipeline/translation_queue.py next` が「All staging years...」を返したときだけ、保守タスクへ移るかをユーザーに確認する。

## 保守タスク再開プロトコル(ユーザーが「保守タスクを再開して」と言ったら)
**1セッション=1タスク。** 以下を厳守する。
1. `python3 pipeline/task.py next`(または TASKS.md)で最初の未完了 `[ ]` タスクを **1つ** 選ぶ。
2. そのタスクの **done-criteria を満たすまで完遂**する。**次のタスクには進まない**(勝手に複数こなさない)。
3. 完了したら TASKS.md の該当行を `[x]` にし、結果を1行追記。設計判断が出たら DESIGN.md 決定ログも更新。
4. 変更を git コミット(メッセージ末尾に `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`)。
5. 停止し、「完了したタスク / 次のタスク」を1行ずつ報告して終わる。

- タスクが1セッションに収まらないと判明したら、**分割して TASKS.md に積み直し**、最初の小タスクだけ実施する。
- 着手前に不明点があり判断が要る場合のみユーザーに確認。それ以外は default を選んで進める。

## 画像作成再開プロトコル(ユーザーが「画像作成タスクを再開して」と言ったら)
**画像追加も1セッション=1タスク。** 画像生成エンジン(Codex built-in `image_gen` か agy/nano-banana)が画像を生成し、Claudeがワークフロー全体をオーケストレートする。以下の手順を厳守すること。

① `python3 pipeline/image_task.py next` で対象年を特定する。
② 対象年の翻訳・胡注を読み、画像生成エンジンで `.agents/instruction-gen-image.md` 準拠の画像を生成する。エンジンは **(a) Codex built-in `image_gen`**(`codex exec -s workspace-write -c approval_policy=never -c sandbox_workspace_write.network_access=true` で起動し、built-in tool 出力の base64 をファイル保存させる)または **(b) agy/nano-banana** のいずれか。Codex が利用制限に当たったら agy へ切替。**どちらもサブスク内・従量API不要**(CLI `gpt-image-2` は `OPENAI_API_KEY`=従量のため使わない)。
③ `pipeline/image_sync.py` で `docs/images/卷NNN/` に圧縮配置する。
④ kb record の `illustrations` 配列に登録する（`translation_full` 本文は触らない）。
⑤ `build_view.py` 再生成し、リンク解決を確認する。
⑥ `IMAGES.md` を `[x]` 化し結果を1行追記する。
⑦ git コミットする。

## ドレインモード(ユーザーが「並列で回して」「使い切って」等と言ったら)
**律速は Codex でも Claude レートでもなく「指示を出せる回数(≒2回/日)」。** 1指示で余っている Claude 予算を安全に使い切るモード。上記「1タスク=1セッション」とは別運用。

- **実証済みモデル(2026-06-28〜29 に卷001-047 で運用。旧 `isolation:"worktree"` 案は使わない)**: 翻訳源 `data/staging/` は **gitignore で fresh worktree に存在しない**ため worktree だと `context.py` が動かない。詳細・事故復旧は memory [[drain-agents-commit-to-main-bug]]。
  - **並列単位 = 巻**。未完巻を K 個選び、巻ごとに background Agent 1体(`run_in_background`・**`isolation` 指定なし=main checkout で実行**・**`model` 指定なし=セッション既定モデルを継承**)。2026-06-28 の実験で旧 Sonnet(4.5系)は forbidden 2.9倍で却下し Opus 確定としていたが、**2026-07-02 ユーザー指示で Sonnet 5 での再検証に切替**。品質劣化の再発有無を監視し、再び forbidden 超過が見られたら Opus へ戻す(詳細 [[drain-sonnet-default-experiment]])。
  - 各エージェントは **git を一切使わない write-only**: 年 JSON を `data/kb/卷NNN/` に書くだけ。`review.py` の temp は巻別ユニーク名(`/tmp/opNNN_<chunk>_*.json`)。冒頭で `ls data/staging/kb/卷NNN.json` を確認(無ければ停止)。
  - 各巻は **first ~4年に bound**(巻完走は超線形コスト [[drain-wave-cost-calibration]])。巻内は年順(前年を書いてから次年の context.py)、巻境界は自然なリセット(fresh 巻は `previous_translation=None` でOK)。ruler/year_label/era は staging から年ごとに取る(null や section 前置詞の癖がある巻は司令塔が上書き指示)。
  - **全エージェント完了後に司令塔(Claude)が一括処理**: `data/kb` を1コミット → `year_western.py`/`build_view.py` を1回 → コミット → 次の波。
  - **halt**(チャンクが3R 非収束)は溜めて、後で **opus + Codex `--effort high` の halt解決波**(records を in-place 編集して再レビュー→pass化)で一括処理。high でも非収束/真の校勘係争は人手へ残す。
- **予算ガード(二段構え)**:
  - ハード床 = **口座側の超過上限 $0**(超えたら 429 で物理停止)。用途次第で都度引き上げる前提。月次 spend limit も別ハード床で、`ai-quota status` の Claude `extra_usage`(`used_credits`/`monthly_limit`)に残額が出る(null のときはユーザーに確認)。
  - ソフト停止 = **5h 枠の 90%**(週間枠も監視)。残量は **`ai-quota status` が Claude/Codex 両方の実値**(5h・週次の `utilization` と `resets_at`)を直接返すので、旧来のアンカー+補間や `/status` 聞き取りは不要:
    1. **波をローンチする前に毎回** `ai-quota status --json` を実行。Claude `five_hour.utilization`(+ `seven_day`)と Codex `five_hour`/`seven_day`(レビュー消費=しばしば真の律速)を読む。
    2. 残ヘッドルーム = 90 −(Claude 5h%)。**1エージェント ≒18pt**(実測較正)で割って投入エージェント数を決める。残ヘッドルームが 1エージェント分を切る、または Codex 週次が枯渇間近なら**新規波を投げない**。`resets_at` も判断材料。
    3. **天井に近づくほど単位を縮める**(K=3巻 → K=1巻 → 1サブバッチ)でオーバーシュート最小化。
- **波の対象選定**: `python3 pipeline/translation_queue.py list` で未完巻を確認(司令塔が frontier を決める)。各エージェントは自巻の `data/staging/kb/卷NNN.json` 存在を確認してから着手。
- **停止条件**: `ai-quota status` が Claude 5h≥90%(または Codex 週次が枯渇)/ 対象巻が尽きた / 429(ハード床)/ ユーザー停止。停止時は「確定した巻・年・現在の 5h%(ai-quota 実値)/ 次に残っている巻」を報告。
- **冪等再開**: write-only なので途中停止で失うのは未コミットの実行中年のみ。再開は `translation_queue.py` が `data/kb/` の実状態から frontier を再判定するので、新セッションで「並列で開始して」と言えば続きから再開できる(self-pace ループ自体は `/loop` 再投入が必要)。

## 実行系と予算(詳細 DESIGN §3)
- Codex は ChatGPT サブスクの **5h レートが律速**。`[Codex]` 印のタスクはレート残量を確認してから。
- 検証・コード生成・調査は **agy 優先**(最安)→ Claude/Codex 予算を温存。
- **Claude レートが律速のときは翻訳本体のみ Claude**に残し、周辺作業(pipeline/検証/画像同期/マージ/調査)を Codex/agy へ寄せて生成トークンを温存する(2026-06-26 方針)。
- 生成データ(`data/raw/`, `data/staging/`, `dict/*.jsonl`)は **gitignore**。manifest と script のみ tracked。

## 環境メモ
- `python3` に **pip 無し**(opencc 等の追加導入は venv/別手段が必要)。Node 22/npm あり。
- 非対話実行: `codex exec -s read-only -c approval_policy=never --output-schema S --output-last-message O -`(prompt は stdin)/ `agy -p "…" --dangerously-skip-permissions`。

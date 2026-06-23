# 資治通鑑 翻訳プロジェクト — セッション指針

資治通鑑(全294巻・約300万字)を現代日本語の平易な口語超訳でナレッジベース化する。
実行系: **Claude=翻訳/オーケストレーション**, **Codex(`codex exec`)=独立クロスベンダー・レビュー**, **agy(Gemini, `agy -p`)=ワンショット実装/機械的検証**。

- 設計の正本: **DESIGN.md**(§1-10 + 決定ログ)。作業前に関連箇所を必ず参照。
- 進捗と次タスク: **TASKS.md**(1タスク=1セッションで完結する粒度)。
- 調査根拠: `research/`、データ来歴: `pipeline/manifests/`、辞書: `dict/`。

## 再開プロトコル(ユーザーが「再開して」と言ったら)
**1セッション=1タスク。** 以下を厳守する。
1. `python3 pipeline/task.py next`(または TASKS.md)で最初の未完了 `[ ]` タスクを **1つ** 選ぶ。
2. そのタスクの **done-criteria を満たすまで完遂**する。**次のタスクには進まない**(勝手に複数こなさない)。
3. 完了したら TASKS.md の該当行を `[x]` にし、結果を1行追記。設計判断が出たら DESIGN.md 決定ログも更新。
4. 変更を git コミット(メッセージ末尾に `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`)。
5. 停止し、「完了したタスク / 次のタスク」を1行ずつ報告して終わる。

- タスクが1セッションに収まらないと判明したら、**分割して TASKS.md に積み直し**、最初の小タスクだけ実施する。
- 着手前に不明点があり判断が要る場合のみユーザーに確認。それ以外は default を選んで進める。

## 画像作成再開プロトコル(ユーザーが「画像作成タスクを再開して」と言ったら)
**画像追加も1セッション=1タスク。** Antigravity（agy）が画像を生成し、Claudeがワークフロー全体をオーケストレートする。以下の手順を厳守すること。

① `python3 pipeline/image_task.py next` で対象年を特定する。
② 対象年の翻訳・胡注を読み、`agy` を repo workspace で起動して `.agents/instruction-gen-image.md` 準拠の画像を生成する。
③ `pipeline/image_sync.py` で `docs/images/卷NNN/` に圧縮配置する。
④ kb record の `illustrations` 配列に登録する（`translation_full` 本文は触らない）。
⑤ `build_view.py` 再生成し、リンク解決を確認する。
⑥ `IMAGES.md` を `[x]` 化し結果を1行追記する。
⑦ git コミットする。

## ドレインモード(ユーザーが「並列で回して」「使い切って」等と言ったら)
**律速は Codex でも Claude レートでもなく「指示を出せる回数(≒2回/日)」。** 1指示で余っている Claude 予算を安全に使い切るモード。上記「1タスク=1セッション」とは別運用。

- **並列単位 = 巻まるごと**。未完の巻を K 個選び、**巻ごとに background Agent を1体**(`run_in_background` + `isolation:"worktree"`)。各エージェントは自分の巻を `data/kb/_LOOP.md` 手順でサブバッチ a→i 順に翻訳→Codex レビュー→**サブバッチ毎に自分ブランチへコミット**。終わったら司令塔が main へマージ→`year_western.py`/`build_view.py` を1回→コミット→次の波。
  - 巻単位にする理由: `continuity_text` は巻内で逐次連鎖。1巻=1エージェントなら連続性が保たれ、巻境界は自然なリセット点。サブバッチを別エージェントに割らない。
  - フレッシュ隔離コンテキスト=手動 `/clear` 相当でトークン効率を保つ。worktree=同一ディレクトリ衝突/コミットレースを構造的に排除。
- **予算ガード(二段構え)**:
  - ハード床 = **口座側の超過上限 $0**(超えたら 429 で物理停止)。用途次第で都度引き上げる前提。
  - ソフト停止 = **5h 枠の 90%**(週間枠は手動管理)。残量ゲージは API ヘッダにありモデルからは見えないため、**アンカー+補間**で運用:
    1. ドレイン開始時に較正する。`data/staging/usage_anchor.json` の `anchored_at` が新しい(目安15分以内・以後に重い他作業なし)ならそれを**再利用可**。無ければユーザーに `/status` の使用%を聞き `python3 pipeline/usage.py anchor <pct>`。各ドレイン冒頭で取り直すのは**ワークロード混在比の差を吸収**するため。
    2. **波をローンチする前に毎回** `python3 pipeline/usage.py estimate --cap 90`。残ポイントが「較正した最悪波コスト」以上のときだけ波を投入。exit=3(STOP)なら新規波を投げない。
    3. **天井に近づくほど単位を縮める**(K=3巻 → K=1巻 → 1サブバッチ)でオーバーシュート最小化。
    4. 他プロジェクト/claude.ai を挟んだら過小評価しうる → ユーザーに `/status` を聞いて**再アンカー**。
- **停止条件**: estimate が STOP / 対象巻が尽きた / 429(ハード床)/ ユーザー停止。停止時は「確定した巻・年・推定使用% / 次に残っている巻」を報告。
- サブバッチ毎コミット+冪等再開(`task.py`/TASKS チェック欄)なので、途中停止で失うのは実行中の1サブバッチのみ。

## 実行系と予算(詳細 DESIGN §3)
- Codex は ChatGPT サブスクの **5h レートが律速**。`[Codex]` 印のタスクはレート残量を確認してから。
- 検証・コード生成・調査は **agy 優先**(最安)→ Claude/Codex 予算を温存。
- 生成データ(`data/raw/`, `data/staging/`, `dict/*.jsonl`)は **gitignore**。manifest と script のみ tracked。

## 環境メモ
- `python3` に **pip 無し**(opencc 等の追加導入は venv/別手段が必要)。Node 22/npm あり。
- 非対話実行: `codex exec -s read-only -c approval_policy=never --output-schema S --output-last-message O -`(prompt は stdin)/ `agy -p "…" --dangerously-skip-permissions`。

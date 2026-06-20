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

## 実行系と予算(詳細 DESIGN §3)
- Codex は ChatGPT サブスクの **5h レートが律速**。`[Codex]` 印のタスクはレート残量を確認してから。
- 検証・コード生成・調査は **agy 優先**(最安)→ Claude/Codex 予算を温存。
- 生成データ(`data/raw/`, `data/staging/`, `dict/*.jsonl`)は **gitignore**。manifest と script のみ tracked。

## 環境メモ
- `python3` に **pip 無し**(opencc 等の追加導入は venv/別手段が必要)。Node 22/npm あり。
- 非対話実行: `codex exec -s read-only -c approval_policy=never --output-schema S --output-last-message O -`(prompt は stdin)/ `agy -p "…" --dangerously-skip-permissions`。

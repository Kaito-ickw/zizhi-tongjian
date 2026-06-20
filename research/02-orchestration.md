# 検証② オーケストレーション機構 — 結論

- 調査日: 2026-06-20
- 結論: **`codex exec` をサブプロセス起動する方式に確定**(MCP は将来オプション)。

## 実証根拠
- 検証①(web 調査 / `workspace-write` + ネット許可 + `curl`)と本②スモークテスト(`read-only` + `--output-schema`)の双方で、headless 非対話動作・構造化 JSON 往復・別モデルレビュー品質を実機確認した。

## I/O 契約
- **入力**: プロンプトは stdin で渡す(日本語の引用符崩れ回避)。出典・コンテキストはファイル渡し。
- **出力**: `--output-schema <schema.json>` で最終応答の JSON 形状を強制 + `--output-last-message <file>` で捕捉してパース。`--json`(JSONL イベント)は必要時のトレース用。
- 例(レビュー): `research/02-review-schema.json` に準拠した JSON が返り、`research/02-review-smoketest.out.json` に捕捉された。

## 独立性(§4 と整合)
- `codex exec` は呼ぶたびに新規セッションを張る → **§4「各レビューラウンドは独立セッション」が無コストで満たされる**。`resume` は使わない。

## 実行フラグ
- レビュー: `-s read-only`(FS 書き込み不要)。
- 取り込み・調査: `-s workspace-write` + `-c sandbox_workspace_write.network_access=true`。
- 共通: `-c approval_policy="never"`(非対話)。
- web 取得は **`curl` で直接**(ネイティブ web 検索は Cloudflare 403 で不可)。

## 品質実証
- gpt-5.5 が品質契約(許容 / 禁止脚色)を適用し、仕込んだ禁止脚色を `translated_span` 単位で局所化し `verdict=fail` を返した。根拠集合に本文+胡注の両方を使用。→ §4 + §7-A 妥当。

## コスト / スループット
- ②スモークは 1 文レビューで **約 18,693 tokens**(reasoning_effort=high で膨張)。
- ChatGPT Plus は従量課金ではなく **サブスクのレート/週次上限が律速**。
- 最適化方針:
  - ルーチンなレビューは `model_reasoning_effort` を下げ、難所(差し戻し多発・矛盾)のみ high に上げる。
  - 翻訳=Claude(Claude サブスク)、レビュー=Codex(ChatGPT サブスク)で負荷を 2 サブスクに分散(ユーザー方針)。

## 将来オプション
- `codex mcp-server` で Codex を MCP ツールとして常駐呼び出しする方式もある。永続セッション/ストリーミングが必要になった場合のみ再検討。現状は subprocess が最小・実証済みで優位。

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

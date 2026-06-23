# 資治通鑑 翻訳プロジェクト — エージェント向け開発ガイド (AGENTS.md)

## プロジェクト概要
『資治通鑑』（全294巻）を平易な現代日本語に超訳し、Markdown形式のナレッジベース（KB）として構築します。

## 実行系
- **翻訳/オーケストレーション**: Claude
- **独立レビュー**: Codex (`codex exec`)
- **画像生成**: Antigravity (`agy`)

## 画像生成タスク (Antigravity 主担当)
画像生成の具体的なビジュアルスタイルについては、[.agents/instruction-gen-image.md](.agents/instruction-gen-image.md) を参照してください。

### ワークフロー契約（I/O）
1. **インプット**: 対象年の `translation_full` および胡注を読み込む。
2. **生成**: スタイルガイドラインに準拠した画像を生成する。
3. **アウトプット**: `docs/images/卷NNN/jNNN_yMM_<slug>.jpg` として保存する。
4. **登録**: kb record (データファイル `data/kb/卷NNN/jNNN_yMM.json`) の `illustrations` 配列へ登録する。**`translation_full` の本文は編集してはならない。**
5. **レンダリング・コミット**: `pipeline/build_view.py` によるビューの再生成および git commit は、オーケストレータ（Claude）が実施する。

### 登録スキーマ (SHARED SCHEMA)
kb record 内の登録フォーマット：
```json
kb record OPTIONAL top-level "illustrations": [ { "slug":"map", "category":"A" (A=map/B=scene/C=portrait/D=artifact), "file":"jNNN_yMM_slug.jpg" (basename; lives in docs/images/卷NNN/), "caption":"…", "anchor":"translation_full 内の一意な部分文字列。画像はこの直後に挿入される" } ]. Omit the array entirely when there are no images.
```

## ワークスペースと権限
- **ワークスペース**: リポジトリルートを workspace とする。
- **書き込み権制限**: 書き込みは `docs/images/` および `data/kb/` のみとする。

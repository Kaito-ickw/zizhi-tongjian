# IMAGES — 画像作成・追加タスク

運用は `CLAUDE.md` の「画像作成再開プロトコル」を参照。**最初の `[ ]` を1つだけ**実施 → `[x]` 化 + 結果1行 → commit → 停止。

---

## [x] I00 — 画像生成スタイル検証・モックアップ作成 [Claude]
結果: 地図/挿絵/肖像/文物のスタイルを検証し、`embedded_visuals_mock.md` を作成。スタイルガイド `instruction-gen-image.md` を整備。

## [x] I01 — 卷001 威烈王二十三年 (j001_y01) に確定画像を追加 [Claude]
*   **対象**: `data/kb/卷001/j001_y01.json`
*   **タスク**: サンプル生成した 1. 晋陽の水攻め（中程度水墨挿絵）、2. 豫讓の肖像（あっさり写意）、3. 三晋版図マップ（日本語地図）、4. 繁纓（日本語文物）を `docs/images/` に配置し、`translation_full` に相対パスで埋め込み、`build_view.py` でMarkdown出力を更新する。
結果: Antigravity CLI 確定4枚（map=three_jin_map_jp / fanying / jinyang_flooding_e / yurang_portrait_c）を `docs/images/卷001/j001_y01_{map,fanying,jinyang,yurang}.jpg` に配置。mock 準拠の4箇所へ `../images/卷001/...` で埋め込み、`build_view.py` 再生成→4リンク全解決を確認。brain→repo の組み込み往復を検証済み。

## [ ] I02 — 卷001 威烈王二十四年 (j001_y02) の画像追加 [Claude]
*   **対象**: `data/kb/卷001/j001_y02.json` (魏文侯が卜子夏・田子方・段干木を師と仰ぐ年)
*   **タスク**: 翻訳テキストを読み、賢者をうやうやしく迎える魏文侯の挿絵、または賢者の肖像を生成・追加する。

## [ ] I03 — 卷001 安王元年 (j001_y03) の画像追加 [Claude]
*   **対象**: `data/kb/卷001/j001_y03.json` (魏文侯が野の番人との約束を守り、雨の中狩りを中止しに行く年)
*   **タスク**: 翻訳テキストを読み、雨の中で車に乗り約束を守る文侯の挿絵などを生成・追加する。

## [ ] I04 — 卷001 安王二年 (j001_y04) の画像追加 [Claude]
*   **対象**: `data/kb/卷001/j001_y04.json`

## [ ] I05 — 卷001 安王三年 (j001_y05) の画像追加 [Claude]
*   **対象**: `data/kb/卷001/j001_y05.json`

## [ ] I06 — 卷001 安王四年 (j001_y06) の画像追加 [Claude]
*   **対象**: `data/kb/卷001/j001_y06.json`

# IMAGES — 画像作成・追加タスク

運用は `CLAUDE.md` の「画像作成再開プロトコル」を参照。**最初の `[ ]` を1つだけ**実施 → `[x]` 化 + 結果1行 → commit → 停止。

---

## [x] I00 — 画像生成スタイル検証・モックアップ作成 [Claude]
結果: 地図/挿絵/肖像/文物のスタイルを検証し、`embedded_visuals_mock.md` を作成。スタイルガイド `instruction-gen-image.md` を整備。

## [x] I01 — 卷001 威烈王二十三年 (j001_y01) の画像追加（本番生成） [Claude/agy]
結果: 画像ドレインで実施。agy(Antigravity, **Imagen 3**)が4スロットを `.agents/instruction-gen-image.md` §1-3 準拠で本番生成し、Claude が §3.5 選定(全4枚を視認検証: map/fanying の日本語ラベルは簡体字なし・崩れなしを §3.3 確認、jinyang/fanying のスタイル合致を確認)→ `image_sync.py` 圧縮(全 ≤300KB・長辺1200px)→ `illustrations[]` 4件登録(`translation_full` 無改変)→ `build_view.py` 反映(anchor 直後挿入・`../images/卷001/` リンク解決確認)。§3.6 来歴: AI生成画像・モデル=Gemini Imagen 3(agy)・成果物ライセンス CC BY-NC-SA 4.0。
*   **対象**: `data/kb/卷001/j001_y01.json`
*   ⚠ **経緯**: 旧I01は I00 のスタイル**検証用サンプル4枚**を、§3.5 バリアント選定・§3.6 来歴記録を経ないまま本番レコードへ確定投入していた（ワークフロー検証の試作画像を本番利用してしまった）。2026-06-24 に本番から撤去（kb の `illustrations[]` 削除・jpg4枚削除・`build_view.py` 再生成で pre-I01 へバイト一致復帰）し、正規生成タスクとして再オープン。
*   **タスク**: 下記4スロットを `.agents/instruction-gen-image.md` §1-3 準拠で **agy により本番生成**し直す → `image_sync.py` で圧縮 → kb `illustrations[]` 登録 → `build_view.py` 再生成。anchor/caption/category は検証時のキュレーションを**再利用してよい**。
*   **再利用スロット（curation 保全）**:
    1. `map`（A=地図）: cap=「戦国時代初期、三晋（韓・魏・趙）と智氏の版図マップ」 / anchor=「この年、周王は初めて、晋の大夫である魏斯(ぎし)・趙籍(ちょうせき)・韓虔(かんけん)の三人を、正式な諸侯として認めた。」
    2. `fanying`（D=文物）: cap=「繁纓（はんえい）— 身分の高い者にのみ許された格式ある馬装具の図解」 / anchor=「だから「分の中で名より大きいものはない」と言うのである。」
    3. `jinyang`（B=挿絵）: cap=「晋陽の水攻め（手描き水墨画）」 / anchor=「ただ、かつて分家していた輔果(ほか)〔=智果〕だけが生き残った。」
    4. `yurang`（C=肖像）: cap=「豫讓（よじょう）の肖像（写意人物画）」 / anchor=「襄子が橋にさしかかると、馬が驚いた。人に探させると豫讓が見つかり、今度はついに殺された。」

## [x] I02 — 卷001 威烈王二十四年 (j001_y02) の画像追加 [Claude]
*   **対象**: `data/kb/卷001/j001_y02.json` (威烈王崩御→安王即位 / 楚で賊が聲王を弑し悼王擁立)
*   ⚠ 旧説明「魏文侯が賢者を師と仰ぐ年」は**年次取り違え**(その内容は y01 後半に在る→ I07 で対応)。y02 実内容に合わせて再定義済み。
*   **タスク**: カテゴリB水墨画「楚の聲王が賊に弑される場面」1枚を生成・追加。
結果: agy(`agy -p` 非対話)で生成→`image_sync.py` で 956KB→200KB 圧縮し `docs/images/卷001/j001_y02_chu.jpg` 配置→kb に `illustrations[]`(slug=chu/cat=B)登録→`build_view.py` でリンク解決確認。委譲フロー(agy生成→Claude同期/登録/build/commit)を end-to-end 検証。

## [x] I03 — 卷001 安王元年 (j001_y03) の画像追加 [Claude]
結果: 安王元年の実内容「秦の魏侵攻（陽孤）」を確認し、カテゴリーB水墨画「秦軍の陽孤侵攻」1枚を生成・追加。docs/images/卷001/j001_y03_qin_attack.jpg に圧縮配置、illustrations[] に登録、build_view.py 再生成確認。
*   **対象**: `data/kb/卷001/j001_y03.json`
*   ⚠ 旧説明「雨中の虞人との約束」も**年次取り違えの疑い**(その逸話も y01 後半→ I07)。着手時に y03 の実内容を確認してから再定義すること。

## [ ] I07 — 卷001 威烈王二十三年 (j001_y01) 後半・魏文侯エピソード群の画像追加 [Claude]
*   **対象**: `data/kb/卷001/j001_y01.json`(既に4枚あり。後半の魏文侯パートは未挿絵)
*   **背景**: 魏文侯が賢者(卜子夏・田子方・段干木)を師と仰ぐ/虞人との約束を守り雨中に狩りを中止/任座の直諫/田子方の応対/李克の宰相選び/呉起——これらは全て y01 の巨大エントリ後半に在る(I02・I03 の旧説明はこれを別年と誤認していた)。
*   **タスク**: 魏文侯が段干木の門前で会釈する場面、または賢者を迎える挿絵(カテゴリB/C)を1〜2枚、`illustrations[]` で追加。

## [x] I04 — 卷001 安王二年 (j001_y04) の画像追加 [Claude]
結果: カテゴリB水墨画「鄭軍による韓の陽翟包囲戦」1枚を生成・追加。docs/images/卷001/j001_y04_yangdi_siege.jpg に圧縮配置、illustrations[] に登録、build_view.py 再生成確認。(agy/Imagen 3)
*   **対象**: `data/kb/卷001/j001_y04.json`

## [x] I05 — 卷001 安王三年 (j001_y05) の画像追加 [Claude]
結果: カテゴリB水墨画「虢山崩壊・黄河堰塞」1枚を生成・追加。docs/images/卷001/j001_y05_guoshan_landslide.jpg に圧縮配置、illustrations[] に登録、build_view.py 再生成確認。(agy/Imagen 3)
*   **対象**: `data/kb/卷001/j001_y05.json`

## [x] I06 — 卷001 安王四年 (j001_y06) の画像追加 [Claude]
結果: カテゴリB水墨画「楚軍による鄭包囲戦」1枚を生成・追加。docs/images/卷001/j001_y06_zheng_siege.jpg に圧縮配置、illustrations[] に登録、build_view.py 再生成確認。(agy/Imagen 3)
*   **対象**: `data/kb/卷001/j001_y06.json`

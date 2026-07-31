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

## [x] I07 — 卷001 威烈王二十三年 (j001_y01) 後半・魏文侯エピソード群 of 画像追加 [Claude]
結果: カテゴリB水墨画「魏の文侯が賢者・段干木の門前を通る際に車上から敬意を表する場面」1枚を生成・追加。docs/images/卷001/j001_y01_duanganmu.jpg に圧縮配置、illustrations[] に登録、build_view.py 再生成確認。(agy/Imagen 3)
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

## [x] I08 — 卷001–006 画像バッチ統合(並行画像セッション分・29枚) [Claude/agy]
結果: 並行画像セッション(agy)が生成した卷001–006の挿絵29枚を司令塔セッションが整合検証のうえ main へマージ。内訳=卷001 y14(呉起/西河「在徳不在険」)・y23(子思)/卷002 ×7(商鞅・西門豹・孫臏・馬陵・趙良・蘇秦・孟嘗君)/卷003 ×10/卷004 ×5/卷005 ×4/卷006 ×1。マージ時検証=全39 illustrations の anchor が translation_full に各1回・参照jpg全実在・孤立jpgなし・build_view.py exit 0(150レコード/158ファイル)。**修正1件**: j001_y14 の anchor が言い換え(`武侯が西河を舟で下り`)で本文非一致→本文の実在表現 `武侯が西河(せいが)に舟を浮かべて川を下った` に是正。`translation_full` 本文は全件無改変。
*   **対象**: `data/kb/卷001–006/` の illustrations[] 追加 + `docs/images/卷001–006/*.jpg`

## [x] I09 — 卷011 太祖高皇帝中 五〜七年 (j011_y01–y03) の画像追加 [Claude/agy]
結果: カテゴリB水墨画4枚を agy(nano-banana)で生成し追加。y01=「垓下の四面楚歌」(gaixia)・「烏江で亭長の舟を退ける項羽」(wujiang) / y02=「陳の会同での韓信捕縛」(hanxin_arrest) / y03=「白登山の包囲」(baideng)。§3.5 選定: gaixia は2バリアント生成し、遠景陣営に文字状の走り書きが出た v1 を却下して blank banner の v2 を採用(他3枚は初回で §1 no-text 合格)。`image_sync.py` で全4枚 1376x768 / ≤229KB に圧縮配置 → `illustrations[]` 登録(`translation_full` 無改変・anchor は各記録内で一意を機械確認) → `build_view.py` 再生成でリンク解決確認(151巻/1062ファイル)。§3.6 来歴: AI生成画像・モデル=Gemini nano-banana(agy)・ライセンス CC BY-NC-SA 4.0。
*   **対象**: `data/kb/卷011/j011_y01–y03.json` + `docs/images/卷011/*.jpg`

## [x] I10 — 卷002 顯王十八年 (j002_y15) の画像追加 [Claude/Codex]
結果: カテゴリB水墨画2枚を Codex built-in `image_gen`(headless `codex exec -s workspace-write`、モデル=gpt-5.6-sol セッション内蔵 image_gen、base64→PNG保存→/tmp経由)で生成し追加。`shenbuhai`=「私的請託を退けられ韓の昭侯に罪を請う申不害」/ `biku`=「すり切れた袴を功ある者のために蔵するよう命じる昭侯」。§1 no-text 目視検証=2枚とも文字状描き込みなしで初回合格(1枚目は生成有無をセッションID+タイムスタンプで機械確認)。`image_sync.py` で 1536x1024 / ≤250KB に圧縮配置 → `illustrations[]` 登録(`translation_full` 無改変・anchor 各1回一致を機械確認) → `build_view.py` 再生成(151巻/1062ファイル)でリンク解決確認。§3.6 来歴: AI生成画像・engine=Codex built-in image_gen(gpt-image系)・ライセンス CC BY-NC-SA 4.0。
*   **対象**: `data/kb/卷002/j002_y15.json` + `docs/images/卷002/j002_y15_{shenbuhai,biku}.jpg`

## [x] I11 — 卷002 顯王二十九年 (j002_y23) の画像追加 [Claude/agy]
結果: カテゴリB水墨画2枚を agy(nano-banana)で生成し追加。`ang`=「偽りの和睦の酒宴で伏兵に公子卬を捕らえさせる衞鞅」/ `daliang`=「安邑を捨て大梁へ遷る魏惠王の車列」。§1 no-text 目視検証=2枚とも旗・幕は無地で文字状描き込みなし、初回で合格。`image_sync.py` で 1376x768 / ≤254KB に圧縮配置 → `illustrations[]` 登録(`translation_full` 無改変・anchor 各1回一致を機械確認・`git diff --numstat` で追加行が illustrations 分のみを確認) → `build_view.py` 再生成(151巻/1062ファイル)でリンク解決確認。§3.6 来歴: AI生成画像・engine=agy(Antigravity)・モデル=Gemini nano-banana・ライセンス CC BY-NC-SA 4.0。
*   **対象**: `data/kb/卷002/j002_y23.json` + `docs/images/卷002/j002_y23_{ang,daliang}.jpg`

## [x] I12 — 卷002 顯王三十三年 (j002_y26) の画像追加 [Claude/agy]
結果: カテゴリB水墨画2枚を agy(nano-banana)で生成し追加。`mengzi_liang`=「魏の惠王に『何ぞ必ずしも利と曰わん、仁義あるのみ』と説く孟子」/ `zisi_mengzi`=「師の子思に民を治める道を問う若き日の孟子」。§1 no-text 目視検証=2枚とも文字状描き込みなし(竹簡は無地の線のみ)、初回で合格。生成は /tmp/zzt_image_agy_j002_y26/ で実施しリポジトリに中間PNGなし。`image_sync.py` で 1024x1024 / ≤235KB に圧縮配置 → `illustrations[]` 登録(`translation_full` 無改変・anchor 各1回一致を機械確認・`git diff --numstat` で追加行が illustrations 分のみを確認) → `build_view.py` 再生成(151巻/1062ファイル)でリンク解決確認。§3.6 来歴: AI生成画像・engine=agy(Antigravity)・モデル=Gemini nano-banana・ライセンス CC BY-NC-SA 4.0。
*   **対象**: `data/kb/卷002/j002_y26.json` + `docs/images/卷002/j002_y26_{mengzi_liang,zisi_mengzi}.jpg`

## [x] I13 — 卷003 愼靚王四年 (j003_y04) の画像追加 [Claude/agy]
結果: カテゴリB水墨画2枚を agy(nano-banana)で生成し追加。`xiuyu`=「脩魚の戦い(秦が韓軍を大破し八万を斬首、䱸・申差を濁沢で捕縛)」/ `zhangyi_wei`=「張儀が魏の襄王に連衡を説き、魏が合従の盟約に背く」。§3.5 選定: zhangyi_wei は2バリアント生成し、右上の掛軸に文字状の描き込みが出た v1 を却下して掛軸なしの v2 を採用(xiuyu は旗が無地で初回 §1 no-text 合格)。生成は /tmp/zzt_image_agy_j003_y04/ で実施しリポジトリに中間PNGなし。`image_sync.py` で 1376x768 / ≤187KB に圧縮配置 → `illustrations[]` 登録(`translation_full` 無改変・anchor 各1回一致を機械確認・`git diff --numstat` で追加行が illustrations 分16行のみを確認) → `build_view.py` 再生成(151巻/1062ファイル)でリンク解決確認。§3.6 来歴: AI生成画像・engine=agy(Antigravity)・モデル=Gemini nano-banana・ライセンス CC BY-NC-SA 4.0。
*   **対象**: `data/kb/卷003/j003_y04.json` + `docs/images/卷003/j003_y04_{xiuyu,zhangyi_wei}.jpg`

## [x] I14 — 卷004 赧王三十四年 (j004_y17) の画像追加 [Claude/Codex]
結果: カテゴリB水墨画2枚を Codex built-in `image_gen`(headless `codex exec --skip-git-repo-check -s workspace-write -c approval_policy=never`、prompt=stdin、生成物 `~/.codex/generated_images/<session>/*.png` を cp)で生成し追加。`wugong`=「東周の武公が楚の令尹昭子に周攻略を思いとどまらせる説得の場面」/ `mihu`=「寓話『虎の皮を蒙る麋』— 沢中で虎皮をまとった麋を狩人たちが遠巻きに狙う」。§1 no-text 目視検証=2枚とも文字状描き込みなし(垂幕・幟は無地)、初回で合格。生成は /tmp/zzt_image_codex_j004_y17/ で実施しリポジトリに中間PNGなし。`image_sync.py` で 1536x1024 / ≤285KB に圧縮配置 → `illustrations[]` 登録(`translation_full` 無改変・anchor 各1回一致を機械確認・`git diff --numstat` で追加行が illustrations 分16行のみを確認) → `build_view.py` 再生成(151巻/1062ファイル)でリンク解決確認。§3.6 来歴: AI生成画像・engine=Codex built-in image_gen(gpt-image系、セッション tokens≒34k)・ライセンス CC BY-NC-SA 4.0。
*   **対象**: `data/kb/卷004/j004_y17.json` + `docs/images/卷004/j004_y17_{wugong,mihu}.jpg`

## [x] I15 — 卷005 赧王五十五年 (j005_y12) の画像追加 [Claude/Codex]
結果: カテゴリB水墨画3枚を Codex built-in `image_gen`(headless `codex exec --skip-git-repo-check -s workspace-write -c approval_policy=never -c sandbox_workspace_write.network_access=true`、prompt=stdin、生成物 `~/.codex/generated_images/<session>/*.png` を cp)で生成し追加。長平の戦いの年。`kuomu`=「趙括の母が王に上書し括の任将を諫める(連座免除のみ許される)」/ `changping`=「長平の包囲——白起の奇兵が趙軍を二分し糧道を断つ俯瞰図」/ `tuwei`=「絶糧四十六日、趙括最後の突囲と戦死」。§1 no-text 目視検証=3枚とも文字状描き込みなし(旗・巻物は無地)、初回で合格。生成は /tmp/zzt_image_codex_j005_y12/ で実施しリポジトリに中間PNGなし。`image_sync.py` で 1536x1024 / ≤297KB に圧縮配置 → `illustrations[]` 登録(`translation_full` 無改変・anchor 各1回一致を機械確認・`git diff --numstat` で追加行が illustrations 分23行のみを確認) → `build_view.py` 再生成(159巻/1083ファイル)でリンク解決確認。§3.6 来歴: AI生成画像・engine=Codex built-in image_gen(gpt-image系、セッション tokens≒31k/枚)・ライセンス CC BY-NC-SA 4.0。
*   **対象**: `data/kb/卷005/j005_y12.json` + `docs/images/卷005/j005_y12_{kuomu,changping,tuwei}.jpg`

## [x] I16 — 卷005 赧王五十六年 (j005_y13) の画像追加 [Claude/agy]
結果: 水墨画3枚(B×2, C×1)を agy(nano-banana)で生成し追加。`yanque`=「燕雀処屋——軒の燕雀と棟に迫るかまどの炎(子順の諫言の寓話)」/ `yuqing`=「虞卿、宰相の印を投げ捨て魏齊とともに出奔」/ `zishun`=「子順(孔斌、孔子六世孫)の写意ポートレート」。§1 no-text 目視検証=3枚とも文字状描き込みなし(瓦装飾は唐草文様・相印は無文)、初回で合格。生成は /tmp/zzt_image_agy_j005_y13/ で実施しリポジトリに中間PNGなし(agy CLI は応答待ちで2回 exit 1 したが生成物は保存済みを確認)。`image_sync.py` で 1024x1024 / ≤170KB に圧縮配置 → `illustrations[]` 登録(`translation_full` 無改変・anchor 各1回一致を機械確認・`git diff --numstat` で追加行が illustrations 分23行のみを確認) → `build_view.py` 再生成(159巻/1083ファイル)でリンク解決確認。§3.6 来歴: AI生成画像・engine=agy(Antigravity)・モデル=Gemini nano-banana・ライセンス CC BY-NC-SA 4.0。
*   **対象**: `data/kb/卷005/j005_y13.json` + `docs/images/卷005/j005_y13_{yanque,yuqing,zishun}.jpg`

## [x] I17 — 卷005 赧王五十七年 (j005_y14) の画像追加 [Claude/Codex]
結果: カテゴリB水墨画3枚を Codex built-in `image_gen`(headless `codex exec --skip-git-repo-check -s workspace-write -c approval_policy=never -c sandbox_workspace_write.network_access=true`、prompt=stdin、生成物 `~/.codex/generated_images/<session>/*.png` を cp)で生成し追加。邯鄲包囲・毛遂自薦・竊符救趙の年。`maosui`=「毛遂の按剣——楚王に合従を迫る」/ `houying`=「信陵君、上座を空けて夷門に侯嬴を迎える」/ `jinbi`=「朱亥、鄴の陣営で晉鄙を椎殺(竊符救趙)」。§1 no-text 目視検証=3枚とも文字状描き込みなし(垂幕・軍旗は無地、兵符は無文)、初回で合格。生成は /tmp/zzt_image_codex_j005_y14/ で実施しリポジトリに中間PNGなし(1セッション目が2枚で timeout したため jinbi のみ別セッションで生成、計2セッション)。`image_sync.py` で 1536x1024 / ≤294KB に圧縮配置 → `illustrations[]` 登録(`translation_full` 無改変・anchor 各1回一致を機械確認・`git diff --numstat` で追加行が illustrations 分23行のみを確認) → `build_view.py` 再生成(159巻/1083ファイル)でリンク解決確認。§3.6 来歴: AI生成画像・engine=Codex built-in image_gen(gpt-image系、モデル=gpt-5.6-sol セッション内蔵、≒29k tokens/枚)・ライセンス CC BY-NC-SA 4.0。
*   **対象**: `data/kb/卷005/j005_y14.json` + `docs/images/卷005/j005_y14_{maosui,houying,jinbi}.jpg`

## [x] I18 — 卷005 赧王五十八年 (j005_y15) の画像追加 [Claude/agy]
結果: カテゴリB水墨画3枚を agy(nano-banana)で生成し追加。白起の最期・信陵君留趙・奇貨可居の年。`baiqi`=「白起、杜郵に死す——士伍に落とされ陰密へ追われた武安君が王の賜剣を受けて自殺」/ `maogong`=「信陵君、処士を訪う——博徒に隠れる毛公・酒売りの家の薛公をお忍びの徒歩で訪ねる」/ `qihuo`=「奇貨居くべし——呂不韋が邯鄲で人質異人と灯下に世継ぎ擁立の策を語る」。§1 no-text 目視検証: baiqi/qihuo は初回合格、maogong は §3.5 で2バリアント生成し、酒壺のラベルに擬似文字が出た v1 を却下して無地壺の v2 を採用。生成は /tmp/zzt_image_agy_j005_y15/ で実施しリポジトリに中間PNGなし(agy CLI は初回「timeout waiting for response」で exit 1、再試行で成功)。`image_sync.py` で 1024x1024〜1200x896 / ≤192KB に圧縮配置 → `illustrations[]` 登録(`translation_full` 無改変・anchor 各1回一致を機械確認・`git diff --numstat` で追加行が illustrations 分23行のみを確認) → `build_view.py` 再生成(159巻/1083ファイル)でリンク解決確認。§3.6 来歴: AI生成画像・engine=agy(Antigravity)・モデル=Gemini nano-banana・ライセンス CC BY-NC-SA 4.0。
*   **対象**: `data/kb/卷005/j005_y15.json` + `docs/images/卷005/j005_y15_{baiqi,maogong,qihuo}.jpg`

## [x] I19 — 卷006 始皇帝上 二年 (j006_y11) の画像追加 [Claude/Codex]
結果: カテゴリB水墨画2枚を Codex built-in `image_gen`(headless `codex exec --skip-git-repo-check -s workspace-write -c approval_policy=never -c sandbox_workspace_write.network_access=true`、prompt=stdin、生成物 `~/.codex/generated_images/<session>/*.png` を cp)で生成し追加。廉頗晩年の年(245 BCE)。`lianpo`=「廉頗老いたりと雖も——使者の前で一飯斗米・肉十斤を平らげ被甲上馬してみせる老将」/ `shouchun`=「『わしはやはり趙の兵を率いたい』——北の故国を望みつつ壽春で客死した廉頗の晩年」。§1 no-text 目視検証=2枚とも文字状描き込みなし(甲冑・器物は無文)、初回で合格。生成は /tmp/zzt_image_codex_j006_y11/ で実施しリポジトリに中間PNGなし。`image_sync.py` で 1536x1024 / ≤292KB に圧縮配置 → `illustrations[]` 登録(`translation_full` 無改変・anchor 各1回一致を機械確認・`git diff --numstat` で追加行が illustrations 分16行のみを確認) → `build_view.py` 再生成(159巻/1083ファイル)でリンク解決確認。§3.6 来歴: AI生成画像・engine=Codex built-in image_gen(gpt-image系、セッション tokens≒33k/2枚)・ライセンス CC BY-NC-SA 4.0。
*   **対象**: `data/kb/卷006/j006_y11.json` + `docs/images/卷006/j006_y11_{lianpo,shouchun}.jpg`

## [x] I20 — 卷006 始皇帝上 三年 (j006_y12) の画像追加 [Claude/agy]
結果: 水墨画2枚(C×1, B×1)を agy(nano-banana)で生成し追加。李牧伝の年(244 BCE)。`limu_portrait`=「李牧——趙の北辺を守った名将の写意ポートレート」/ `limu_ambush`=「李牧の匈奴殲滅——野に放った家畜で誘い込み、戦車と騎兵の両翼で単于の大軍を挟撃する俯瞰図」。§1 no-text 目視検証=2枚とも文字状描き込みなし(軍旗・幟はすべて無地)、初回で合格。生成は /tmp/zzt_image_agy_j006_y12/ で実施しリポジトリに中間PNGなし。`image_sync.py` で 1376x768 / ≤194KB・896x1200 / ≤108KB に圧縮配置 → `illustrations[]` 登録(`translation_full` 無改変・anchor 各1回一致を機械確認・`git diff --numstat` で追加行が illustrations 分16行のみを確認) → `build_view.py` 再生成(163巻/1094ファイル)でリンク解決確認。§3.6 来歴: AI生成画像・engine=agy(Antigravity)・モデル=Gemini nano-banana・ライセンス CC BY-NC-SA 4.0。
*   **対象**: `data/kb/卷006/j006_y12.json` + `docs/images/卷006/j006_y12_{limu_portrait,limu_ambush}.jpg`

## [x] I21 — 卷006 始皇帝上 六年 (j006_y15) の画像追加 [Claude/Codex]
結果: 水墨画2枚(B×1, C×1)を Codex built-in `image_gen`(headless `codex exec -s workspace-write -c approval_policy=never -c sandbox_workspace_write.network_access=true`、prompt=stdin、生成物 `~/.codex/generated_images/<session>/*.png` を cp)で生成し追加。五国合従の失敗と楚の壽春遷都の年(241 BCE)。`hangu`=「函谷関の敗走——楚・趙・魏・韓・衞の五国合従軍が秦軍の出撃で総崩れとなる俯瞰図」/ `shunshinkun`=「春申君——合従失敗の咎で楚王に疎まれ、呉の封地へ赴いた楚の宰相の写意ポートレート」。§1 no-text 目視検証=2枚とも文字状描き込みなし(軍旗・幟・帯はすべて無文)、初回で合格。生成は /tmp/zzt_image_codex_j006_y15/ で実施しリポジトリに中間PNGなし(1セッションで2枚、tokens≒35k)。`image_sync.py` で 1536x1024 / ≤289KB・758x1600 / ≤109KB に圧縮配置 → `illustrations[]` 登録(`translation_full` 無改変・anchor 各1回一致を機械確認・`git diff --numstat` で追加行が illustrations 分16行のみを確認) → `build_view.py` 再生成(163巻/1094ファイル)でリンク解決確認。§3.6 来歴: AI生成画像・engine=Codex built-in image_gen(gpt-image系)・ライセンス CC BY-NC-SA 4.0。
*   **対象**: `data/kb/卷006/j006_y15.json` + `docs/images/卷006/j006_y15_{hangu,shunshinkun}.jpg`

## [x] I22 — 卷006 始皇帝上 九年 (j006_y18) の画像追加 [Claude/agy]
結果: 水墨画2枚(B×2)を agy(nano-banana)で生成し追加。嫪毐の乱・茅焦の諫言・春申君暗殺の年(238 BCE)。`maojiao`=「茅焦の諫言——剣の柄を握り激怒する秦王政の前で、茅焦が処刑台のかたわらに端座して死を恐れず諫める場面」/ `chunshen`=「春申君の最期——棘門の内側に潜んだ李園の死士たちが門を入る春申君に両側から斬りかかる場面」。§1 no-text 目視検証=2枚とも文字状描き込みなし。chunshen は初回生成で刺客が忍者風(覆面・頭巾)となり時代性不適のため、戦国期中国武人(束髪・無覆面)を明示指定して1回再生成し合格。生成は /tmp/zzt_image_agy_j006_y18/ で実施しリポジトリに中間PNGなし。`image_sync.py` で 1376x768 / ≤136KB・1376x768 / ≤187KB に圧縮配置 → `illustrations[]` 登録(`translation_full` 無改変・anchor 各1回一致を機械確認・`git diff --numstat` で追加行が illustrations 分16行のみを確認) → `build_view.py` 再生成(167巻/1103ファイル)でリンク解決確認。§3.6 来歴: AI生成画像・engine=agy(Antigravity)・モデル=Gemini nano-banana・ライセンス CC BY-NC-SA 4.0。
*   **対象**: `data/kb/卷006/j006_y18.json` + `docs/images/卷006/j006_y18_{maojiao,chunshen}.jpg`

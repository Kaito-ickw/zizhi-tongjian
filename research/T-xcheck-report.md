# T-xcheck: Wikisource × Kanripo クロスチェック

生成日: 2026-06-21

## 方法

Kanripo を原文層(source of record)、維基文庫『資治通鑑(胡三省音注)』をセグメント層として、本文と胡三省注を別系列で照合した。標点・空白・markup を除いて CJK 統合漢字だけを抽出し、整合判定時のみ OpenCC `t2s` で fold した文字列を `SequenceMatcher(autojunk=False)` に渡した。レポートの差分は fold 前の原字である。

Kanripo の双行夾注は、括弧グループごとに `右半 + 左半` とする de-interleave 案Bで復元した。先頭 delete は `front_matter`、6字以上の delete/insert は欠落、それ以外は異読として分類した。`front_matter` は欠落集計から除外した。

## 既知の限界

長い多行注では局所的な列順転倒により偽の異読が生じうる。また、Kanripo の巻頭ボイラープレートと、維基文庫 Header 内の巻頭干支レンジ注は底本間の既知の構造差であり、先頭の差分を `front_matter` として扱う。

## 全巻集計

- 対象: 294巻（処理 294、skip 0）
- 平均 body ratio: 0.970588
- 平均 notes ratio: 0.951294
- 本文: Wikisource 欠落 39、Kanripo 欠落 21、異読 67615
- 注: Wikisource 欠落 42、Kanripo 欠落 2536、異読 62686

### 要レビュー巻

| 巻 | flag | body ratio | notes ratio |
|---:|---|---:|---:|
| 158 | LOW_NOTES | 0.966458 | 0.815419 |

### 欠落・異読サンプル

| 巻 | 系列 | 分類 | Kanripo | Wikisource |
|---:|---|---|---|---|
| 2 | body | omission_wiki | 因民而教者不勞而成功 | （空） |
| 7 | notes | omission_wiki | 惡鬼謂羣邪也 | （空） |
| 13 | body | omission_wiki | 吕禄吕產欲作亂内憚絳侯朱虚等外畏齊楚兵又恐灌嬰畔之欲待灌嬰兵與齊合而發猶豫未決 | （空） |
| 1 | notes | omission_kanripo | （空） | 章十二行本莫下有敢字乙十一行本同孔本同章十二行本二字互乙乙十一行本同孔本同 |
| 1 | notes | omission_kanripo | （空） | 章十二行本王作周乙十一行本同孔本同退齋校同 |
| 1 | notes | omission_kanripo | （空） | 章十二行本正作鬢孔本同乙十一行本作鬚 |
| 1 | body | variant_multi | 彊茍 | 強苟 |
| 1 | body | variant_multi | （空） | 子 |
| 1 | body | variant_multi | 子 | （空） |
| 1 | body | variant_single | 䖍 | 虔 |
| 1 | body | variant_single | 寜 | 寧 |
| 1 | body | variant_single | 辯 | 辨 |

## 巻1の代表的な検出例

- 注 `窟` → `窋` （variant_single、Kanripo位置 249 / Wikisource位置 232）
- 注 `安` → `其` （variant_single、Kanripo位置 476 / Wikisource位置 465）
- 注 `曰` → `（空）` （variant_multi、Kanripo位置 19 / Wikisource位置 2）
- 注 `䝉` → `蒙` （variant_single、Kanripo位置 31 / Wikisource位置 13）

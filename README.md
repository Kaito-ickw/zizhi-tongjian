# 資治通鑑 現代日本語訳プロジェクト

資治通鑑(全294巻・約300万字)を、AI エージェントを用いて現代日本語の平易な口語超訳に全訳し、全編を読めるナレッジベースとして構築する。

- 翻訳エンジン = Claude(オーケストレーター兼翻訳)/独立検証レビュー = Codex(GPT)/挿絵 = nano banana 2
- 設計の正本は [`DESIGN.md`](./DESIGN.md)。仕様変更はそこへの差分で管理
- 生成済みの閲覧用ドキュメントは [`docs/`](./docs/)

## 状態
- 設計確定(grilling 2026-06-20)。着手前検証バックログ ①②③ 完了。実装フェーズ。
- 翻訳確定レコード: 卷001〜卷010 に 167年分(すべて `pass`)。卷001〜卷005・卷008 は巻内の全年度が `pass`。

## 全体進捗
2026-06-27 時点。`data/kb/` の確定レコードと `data/staging/kb/`・`pipeline/manifests/` の全体母数から集計。

| 基準 | 進捗 | 数値 |
|---|---|---:|
| 年レコード | <progress value="167" max="1397">12.0%</progress> | 167 / 1,397 = 12.0% |
| 翻訳チャンク | <progress value="178" max="2096">8.5%</progress> | 178 / 2,096 = 8.5% |
| 全年度完了巻 | <progress value="6" max="294">2.0%</progress> | 6 / 294 = 2.0% |
| 着手済み巻 | <progress value="10" max="294">3.4%</progress> | 10 / 294 = 3.4% |
| 底本+注文字数 | <progress value="198273" max="6244451">3.18%</progress> | 198,273 / 6,244,451 = 3.18% |

年数ベースでは約12%、作業量(底本+注文字数)ベースでは約3%完了。序盤は短い年が多いため、実作業量感は文字数・チャンク基準を優先して見る。

## 底本・データソース(非商用方針)
| 層 | ソース | ライセンス |
|---|---|---|
| 原文 / 胡三省注 | Kanripo `KR2b0007` | CC BY-SA 4.0 |
| 標点・セグメント | 維基文庫「資治通鑒 (胡三省音注)」 | CC BY-SA 4.0 |
| 人物・官職辞書 | CBDB | CC BY-NC-SA 4.0 |
| 地名辞書 | CHGIS / TGAZ | 要確認(内部利用) |
| 補完 | Wikidata | CC0 |
| 検証 | NCL-01723 影印 | public domain |

成果物は CC BY-NC-SA 系(帰属 + 非商用 + 継承)で公開する前提。詳細は `DESIGN.md §10`。

## ディレクトリ
```
DESIGN.md            設計正本
research/            着手前検証レポート(①ctext ②orchestration ③entity-dict)
data/raw/            外部コーパスの取得物(gitignore、manifest で pin)
data/staging/        正規化途中(gitignore)
data/kb/             成果物ナレッジベース(年=ファイル)
docs/                閲覧用 Markdown ビュー
pipeline/            取り込み・正規化・翻訳/レビュー パイプライン
dict/                エンティティ辞書
```

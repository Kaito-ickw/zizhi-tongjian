# エンティティ辞書の初期ソース調査

- 調査日: 2026-06-20
- 対象時代: 前403年〜後959年
- 調査方法: Web 検索エンジンは使わず、公式サイト、公開 API、Harvard Dataverse、配布リポジトリへ `curl` で直接アクセスした。CBDB SQLite、TGAZ CSV、DILA TEI/XML は実ファイルを取得して集計した。
- 結論: 人物・地名・官職の三カテゴリとも初期 seed は作れる。ただし、人物の戦国〜三国、地名の戦国前半、官職の漢〜隋・五代は本文抽出による補完が必須である。また、CBDB/CHGIS/TGAZ は非商用・再配布条件を取り込み前に確定する必要がある。

## 調査上の前提

このプロジェクトで必要なのは単純な語彙リストではなく、同じ表記が複数の人物・場所・官職を指し得ることを前提とした同定辞書である。そのため、以下を評価した。

1. 永続的な典拠 ID があるか。
2. 正規名と異名が分離されているか。
3. 生存・存続・使用時代を表せるか。
4. 一括取得または API による再現可能な取得ができるか。
5. 翻訳成果物と辞書を公開・再配布できるライセンスか。

集計値は取得したスナップショットに対する値であり、史料上の全人物・全地名・全官職を分母とする「真の網羅率」ではない。以下では「収録件数・時代分布」と「実用上の評価」を区別する。

## 1. 人物

### 1.1 CBDB の対象時代と収録密度

**確認済み。** CBDB 公式説明は、収録の中心を7世紀から20世紀初頭とし、唐・五代・遼・宋以後を継続拡充中としている。2019年版 User's Guide も「90%以上が唐から20世紀初頭」と明記している。したがって、対象時代を形式上はカバーするが、戦国・秦漢・三国を均等にカバーするデータベースではない。

- [CBDB Coverage](https://cbdb.hsites.harvard.edu/coverage-cbdb)
- [CBDB User's Guide: Preface](https://github.com/cbdb-project/cbdb-user-guide/blob/main/docs/preface.md)
- [CBDB 公式ダウンロードページ](https://cbdb.hsites.harvard.edu/download-cbdb-standalone-database)

2026-06-13 版 SQLite (`cbdb_20260613.sqlite3`) を取得し、`BIOG_MAIN.c_dy` で対象王朝を集計した結果は次のとおりである。王朝分類は重複しないコードの合算であるが、「漢前」は戦国以前も含む。

| 時代群 | 人物数 | 異名あり人物 | 異名レコード | 評価 |
|---|---:|---:|---:|---|
| 漢前（戦国以前を含む） | 111 | 36 | 46 | 非常に疎。戦国全体の seed には不足 |
| 秦漢 | 995 | 73 | 126 | 主要人物の一部はあるが低密度 |
| 三国 | 357 | 41 | 72 | 低密度 |
| 晋・十六国 | 918 | 73 | 147 | 低〜中密度 |
| 南北朝 | 4,634 | 337 | 489 | 人名 seed として有用だが異名は薄い |
| 隋 | 741 | 105 | 138 | 中程度 |
| 唐・武周 | 57,937 | 6,404 | 8,020 | 高密度。主力にできる |
| 五代十国（関連諸国） | 2,589 | 355 | 588 | 実用的だが本文補完は必要 |

別の見方として `c_index_year` が対象区間に入る人物数は、戦国10、前漢〜新329、後漢184、三国65、晋340、南北朝3,948、隋3,734、唐37,415、五代2,758だった。ただし `c_index_year` は CBDB が分析用に推定する場合があり、未設定者もいる。たとえば取得版では劉備に `c_index_year` がなく、単純な年フィルタでは落ちる。取り込み対象の選別には、`c_dy`、生没年、活動年、index year を併用する必要がある。

**判断:** 唐は十分に強い。五代・南北朝・隋は有用な seed。戦国〜三国は主要人物の候補集合としてのみ使い、本文から抽出した人物を CBDB/Wikidata/DILA へ照合する方式にする。

### 1.2 別名テーブルと人物同定への利用

**確認済み。** SQLite には以下の正規化テーブルがある。

- `BIOG_MAIN`: `c_personid` を主キーとし、`c_name_chn`、生没年、活動年、王朝コード、index year 等を持つ。
- `ALTNAME_DATA`: `(c_alt_name_chn, c_alt_name_type_code, c_personid)` が複合主キー。`c_personid`、中国語異名、異名種別、出典 ID、頁、注記を持つ。
- `ALTNAME_CODES`: 異名種別辞書。

実データの異名種別には、`字`、`室名・別號`、`諡號`、`封爵`、`小名`、`小字`、`賜號`、`廟號`、`尊號`、`本姓`、`法號`、`道號`、`俗名`、`其他譯名` 等がある。対象時代の index year 範囲に限っても、字4,979、諡648、別名・旧名486、廟号97を確認した。

したがって、`ALTNAME_DATA.c_alt_name_chn -> BIOG_MAIN.c_personid` は表記から人物候補を引く用途に直接使える。ただし同じ字・諡・廟号・封爵が複数人物に使われるため、**一意な辞書として扱ってはいけない**。戻り値は候補集合とし、王朝・生存期間・親族・官職・同一チャンク内の共起で絞る。

確認用 SQL の骨格:

```sql
SELECT
  b.c_personid,
  b.c_name_chn,
  a.c_alt_name_chn,
  t.c_name_type_desc_chn,
  b.c_birthyear,
  b.c_deathyear,
  b.c_fl_earliest_year,
  b.c_fl_latest_year,
  b.c_dy
FROM BIOG_MAIN b
LEFT JOIN ALTNAME_DATA a USING (c_personid)
LEFT JOIN ALTNAME_CODES t
  ON t.c_name_type_code = a.c_alt_name_type_code;
```

CBDB API でも `PersonAliases` として異名種別・異名を返すことを確認した。王安石 `Q319618/CBDB 1762` では、字「介甫」、別号「半山老人」、諡「文」、小字「獾郎」、封爵「王荊公」が返った。

- [CBDB API 説明](https://cbdb.fas.harvard.edu/cbdbapi/)
- [CBDB API JSON 例: person 1762](https://cbdb.fas.harvard.edu/cbdbapi/person.php?id=1762&o=json)
- [CBDB User's Guide: テーブル一覧](https://github.com/cbdb-project/cbdb-user-guide/blob/main/docs/chapter_2_summary_of_tables_in_cbdb.md)

### 1.3 入手形態、更新、ライセンス

**確認済み。** 現在の推奨一括取得は SQLite である。

| 形態 | 状態 | 用途 |
|---|---|---|
| SQLite | Hugging Face の `latest.zip` と履歴版を公開。今回の展開後 DB は659,236人物、207,441異名 | 初期 seed の主経路 |
| Microsoft Access | 公式ページで interface MDB + data MDB を配布。2026-06-02版は649,533人物と説明 | Windows GUI 利用向け。ETL には SQLite を優先 |
| MySQL/MariaDB | CBDB 内部・変換用リポジトリは存在するが、現在の公式一括配布の主経路として MySQL dump は確認できなかった | SQLite から自前変換する。公開 dump の有無は未確認 |
| REST API | `id` または `name` で JSON を返す。匿名 `curl` が成功 | 個別照会・差分確認。全件取得には不向き |

- [cbdb_sqlite リポジトリ](https://github.com/cbdb-project/cbdb_sqlite)
- [CBDB SQLite 配布データセット](https://huggingface.co/datasets/cbdb/cbdb-sqlite)
- [Access/MySQL 変換リポジトリ](https://github.com/cbdb-project/accessAndMySQLTransfer)
- [CBDB Swagger](https://github.com/cbdb-project/cbdb-swagger/blob/master/swagger.yaml)

更新については、Hugging Face に 2026-06-06、2026-06-13 の SQLite 履歴があり、少なくともこの期間は週次生成だった。公式 Access ページは、学術版への新規人物公開が商用版より約1年遅れるとも説明している。つまり「ファイル生成頻度」と「新規人物データの反映遅延」は別である。

運用上の注意として、GitHub の `latest.json` は調査時点で2026-03-14を指していた一方、`latest.zip` は2026-06-13版だった。`latest.json` を無条件に正本とせず、Hugging Face API の commit、ZIP 内 JSON、SHA-256、展開後ファイル名を記録して pin する。

**ライセンスは CC BY-NC-SA 4.0。** Hugging Face dataset card、Swagger、公式サイトで一致した。帰属表示、非商用、継承条件がある。公開する翻訳 KB や辞書が「Adapted Material」に当たる範囲は要確認であり、商用化可能性があるなら CBDB 由来データを分離するか別途ライセンスを得る必要がある。

### 1.4 フォールバック

#### Wikidata

**確認済み。** MediaWiki API、EntityData JSON、SPARQL、週次 JSON/RDF dump が使える。王安石 `Q319618` で中国語・繁体字・日本語ラベル、中国語異名「王荊公」「介甫」「半山老人」「獾郎」および生没日を取得できた。

- [EntityData: Q319618](https://www.wikidata.org/wiki/Special:EntityData/Q319618.json)
- [Wikidata Query Service](https://query.wikidata.org/)
- [Wikidata database download](https://www.wikidata.org/wiki/Wikidata:Database_download)
- [Wikidata licensing](https://www.wikidata.org/wiki/Wikidata:Licensing)

構造化データは CC0 であり、CBDB より再利用しやすい。ただし異名の種別が CBDB ほど精密でなく、古代中国人物の網羅性・典拠品質は項目ごとの差が大きい。CBDB ID が Wikidata の外部識別子として入っている場合は相互リンクし、なければ姓名・生没年・王朝・役職の一致を人手確認して `same_as` を付ける。ラベル一致だけで自動マージしない。

#### DILA Buddhist Studies Authority Databases

**確認済み。** DILA は人物・地名典拠を API と TEI/XML で公開しており、仏教史人物の補完に有用である。2026-06版人物 XML は49,028人物、52,706異名、唐4,377、五代十国848、隋668、劉宋471、東晋398、北魏335等を含んでいた。API は正規名、異名、王朝、生没日の可能範囲、出身地 ID を JSON で返す。

- [DILA Authority](https://authority.dila.edu.tw/)
- [ダウンロード](https://authority.dila.edu.tw/docs/open_content/download.php)
- [人物 API 仕様](https://authority.dila.edu.tw/docs/services/person_query.php)
- [配布リポジトリ](https://github.com/DILA-edu/Authority-Databases)

配布リポジトリは CC BY-SA 3.0。主題が仏教に偏るため一般人物の主典拠にはしない。なお、取得した2026-06人物 XMLは少なくとも1箇所で XML parser が不正トークンを検出したため、取り込み前に well-formedness 検査と修復ログが必要である。

## 2. 地名

### 2.1 CHGIS V6 のカバーと構造

**確認済み。** CHGIS は中国歴代の地名・歴史行政単位を提供し、V6 は time-series の府級 polygon/point と県級 point を配布する。各歴史的地名インスタンスは開始・終了年、行政種別、座標、親行政区を持つ。

- [CHGIS 公式サイト](https://chgis.fas.harvard.edu/)
- [CHGIS V6](https://chgis.fas.harvard.edu/data/chgis/v6/)
- [V6 Time Series datasets](https://dataverse.harvard.edu/dataverse/chgis_v6_time)
- [V6 Data Dictionary](https://doi.org/10.7910/DVN/SNCEAU)

公式 dataset description は、府級・県級とも1350〜1911年は概ね完全、前221〜1350年は空白が残ると明記する。TGAZ/CHGIS CSV には前221年以前の断片も実在するが、戦国全体を系統的にカバーするとは判断できない。

取得した2016-07-06版 CHGIS CSV 71,647行について、各時点で有効な歴史地名インスタンス数は前403年18、前300年53、前221年417、西暦0年1,426、200年1,138、500年1,597、600年1,827、700年2,059、900年1,832、950年1,845だった。対象区間と重なるレコード数は次のとおりである。

| 区間 | 重なる地名インスタンス | 異なる表記数 | 評価 |
|---|---:|---:|---|
| 戦国 | 472 | 450 | 前半は極めて疎。断片的 |
| 前漢・秦・新 | 3,142 | 2,137 | 実用 seed になる |
| 後漢 | 1,872 | 1,529 | 実用 seed になる |
| 三国 | 1,348 | 1,207 | 実用 seed になる |
| 晋 | 1,915 | 1,541 | 実用 seed になる |
| 南北朝 | 3,667 | 2,687 | 強い |
| 隋 | 3,583 | 2,674 | 強い |
| 唐 | 5,381 | 3,434 | 強い |
| 五代 | 2,250 | 2,019 | 実用的 |

ここで「重なる」は `BEG <= 区間末 AND END >= 区間始` であり、期間の長い同一インスタンスを各時代に重複計上している。史料中の自然地名、俗称、宮殿名、戦場名を完全に覆う数字ではない。

### 2.2 TGAZ の API、異名、現代地名対応

**確認済み。** 旧 `maps.cga.harvard.edu/tgaz/` は新しい `chgis.hudci.org/tgaz/` へ移転している。現行 API は読み取り専用で、次を受け付ける。

- 正規 ID: `/tgaz/placename/json/hvd_32180`
- 表記検索: `/tgaz/placename?fmt=json&n=洛陽`
- 表記 + 年: `/tgaz/placename?fmt=json&n=Luoyang&yr=500`
- 追加 facet: feature type、data source、immediate parent

- [TGAZ API 仕様](https://chgis.hudci.org/tgaz/)
- [年付き検索例](https://chgis.hudci.org/tgaz/placename?fmt=json&n=Luoyang&yr=500)
- [正規レコード例](https://chgis.hudci.org/tgaz/placename/json/hvd_32180)

年500の `Luoyang` 検索は、洛陽県（265〜604）と別地域の羅陽県2件を返した。この挙動は同名異地の候補生成に適している。正規レコードは次を返す。

- `sys_id`
- 繁体字・簡体字・拼音の `spellings`
- `feature_type`
- `temporal.begin/end`
- 緯度・経度
- `present_location`（例: `今浙江金华市`）
- 年代区間付きの親行政区、下位単位、前身・後継

したがって、「歴史地名表記 -> 時点付き場所 ID -> 現代位置説明・座標」の経路を作れる。ただし modern mapping は自由記述の `present_location.text` であり、現代行政区の永続 ID へ常に正規化されているわけではない。座標近傍と Wikidata/現代行政コードを使って別途 `modern_place_id` を付ける。

### 2.3 入手形態とライセンス

**確認済み。** 入手形態は以下のとおり。

| ソース | 形態 | 特徴 |
|---|---|---|
| CHGIS V6 | ESRI Shapefile、data dictionary、年代表 | GIS 一括処理向け |
| TGAZ | REST JSON/XML/HTML/RDF | 名前・年・親行政区で個別検索 |
| TGAZ GitHub | 71,647行CSV、RDF、MySQL DDL/コード | seed の一括生成に最も簡単 |
| Harvard Dataverse TGAZ | 2018年 MySQL dump（展開後約123MB） | 完全な関係構造をローカル復元可能 |

- [TGAZ GitHub](https://github.com/cga-harvard/tgaz)
- [TGAZ Dataverse](https://doi.org/10.7910/DVN/H3OB28)

**ライセンスは表示が矛盾しており、未解決。**

1. CHGIS V6 EULA は学術・教育目的の非商用利用に限定し、全レイヤの再配布・再パッケージを禁止する。
2. 現行 TGAZ API の個別レコードは `CC BY-NC 4.0` と返す。
3. TGAZ GitHub README は TGAZ を GPLv3 とする。これは少なくともコードには適用できるが、CHGIS 由来レコードまで GPL で再許諾できるかは不明。
4. Harvard Dataverse の TGAZ dataset metadata は CC0 と表示する。

- [CHGIS V6 EULA](https://doi.org/10.7910/DVN/FDLFJ3)
- [TGAZ GitHub README](https://github.com/cga-harvard/tgaz/blob/master/README.md)

安全側では、CHGIS 由来データは CHGIS EULA/API の非商用条件に従う。プロジェクト内部の研究用 seed として利用し、公開辞書へ全量再配布する前に CHGIS/TGAZ 管理者へ、(a) API 個別レコード、(b) CSV/MySQL dump、(c) そこから作る表記辞書、の適用ライセンスを確認する。Dataverse の CC0 表示だけを根拠に再配布しない。

### 2.4 その他の歴史地名典拠

#### CBDB `ADDR_CODES`

**確認済み。** CBDB SQLite に30,100地名があり、`c_name_chn`、`c_firstyear`、`c_lastyear`、行政種別、座標、`CHGIS_PT_ID`、`c_alt_names` を持つ。人物と場所を同じ DB 内で結べるため、人物の籍貫・任地の候補強化に使える。ただし `c_alt_names` は非正規化文字列で、時代別件数にも偏りがあるため、地名の主典拠は TGAZ とし、CBDB は crosswalk とする。

#### DILA Place Authority

**確認済み。** 2026-06 TEI/XML は59,260 `place`、14,524 alternative name を含み、API は正規名・異名・座標を返す。仏教寺院・仏典関連地名の補完に向く。配布リポジトリは CC BY-SA 3.0 だが、公式説明では DILA 作成分約19,000に加え Academia Sinica 提供分約38,000をオンライン DB が含むとしている一方、取得 XML の件数は約59,000だった。**どのレコードまで CC BY-SA で再配布可能かは未確認**なので、出典 provenance で DILA 作成分を分離できるまで全量 seed にはしない。

- [DILA Place API 仕様](https://authority.dila.edu.tw/docs/services/place_query.php)
- [DILA 配布リポジトリ](https://github.com/DILA-edu/Authority-Databases)

#### Wikidata

CC0、QID、異言語ラベル・alias、座標、`located in administrative entity`、各種外部 ID を利用できる。現代地名への crosswalk と、TGAZ にない自然地名・宮殿・建築物の補完に向く。ただし歴史行政区の存続期間・境界は一貫して構造化されていないため、対象時代の主典拠にはしない。

#### 「中國歷史地名」等

Academia Sinica GIS Center のサイトと、DILA が同センター由来の追加地名を持つことは確認した。しかし、今回の直接 HTTP 調査では、対象期を一括取得でき、個別レコードの再利用条件まで明示した独立の「中國歷史地名」配布 API/ダンプを確認できなかった。良質な検索 UI が存在することと、seed に合法的に一括取り込みできることは別であるため、現段階では採用しない。

## 3. 官職

### 3.1 CBDB 官職テーブル

**確認済み。** CBDB SQLite は次を持つ。

- `OFFICE_CODES`: 34,062官職。`c_office_id`、王朝コード、正規中国語名、異表記、英訳、出典、頁、注記。
- `POSTED_TO_OFFICE_DATA`: 588,808任官関係。人物、官職、開始・終了年、任命種別、出典を持つ。
- `OFFICE_TYPE_TREE`、`OFFICE_CODE_TYPE_REL`、`OFFICE_CATEGORIES`: 官職階層・分類。

機械可読性は高く、`c_office_chn` と `c_office_chn_alt` を正規・異名に分けて `c_office_id` へ対応できる。人物の実任官レコードを使えば、同一チャンクの人物・官職の整合性チェックもできる。

ただし王朝別の `OFFICE_CODES` 件数は、漢前1,675、唐4,205、宋6,611、遼3,182、金1,670、元5,771、明2,853、清8,095で、秦漢・三国・晋・南北朝・隋・五代に直接割り当てられた官職コードは0だった。隋・南北朝・五代人物の任官が唐コードを参照する例は多数あるため、コード0件は「官職情報が皆無」ではなく、名称体系が唐コードへ寄せられていることを意味する。しかし、これを王朝横断の同一官職概念と無条件に解釈するのは危険である。

CBDB User's Guide 自体も、同じ官職名の職掌が漢から清までに変化し、同じ職掌でも名称が変わること、官職名と官職機能を分離する将来課題を明記している。

- [CBDB User's Guide: Offices and Postings](https://github.com/cbdb-project/cbdb-user-guide/blob/main/docs/chapter_2_the_structure_of_cbdb.md#6-offices-and-postings)

**取り込み方:** `c_office_id` は source-local ID として保持する。`c_office_chn_alt` が `;` 区切りの場合は分割するが、正規化ログに元文字列を残す。`POSTED_TO_OFFICE_DATA` の実年代から各表記の観測区間を集計し、王朝コードだけで期間を決めない。

### 3.2 Hucker の機械可読性と権利

**確認済み。** CBDB 公式 GitHub に2026年公開の作業版リポジトリがあり、OCR Markdown と JSONL 相当の `webapp/data.json` を公開している。実ファイルは8,291レコードで、以下を持つ。

- 中国語 headword
- Wade-Giles、拼音
- 王朝リスト
- 英訳・本文
- `normalized/candidate/uncertain/pending` 状態
- LLM confidence、issue tags、OCR/編集注記

- [CBDB Hucker working dataset](https://github.com/cbdb-project/hucker-dictionary)
- [machine-readable data](https://github.com/cbdb-project/hucker-dictionary/blob/main/webapp/data.json)

機械可読ではあるが、README は「作業中」「OCR ノイズ」「LLM による復元」「王朝ラベル不統一」「引用級には原著確認」と明記する。8,291件中 title status は normalized 900、candidate 6,278、uncertain 1,113だった。したがって品質フラグを落として seed に直入れしてはいけない。

**権利は未確認であり、現時点では取り込まない。** 原著は Charles O. Hucker, *A Dictionary of Official Titles in Imperial China*, Stanford University Press, 1985。公開リポジトリには LICENSE ファイルも明示的なデータライセンスもなかった。OCR・翻刻・英訳本文を公開辞書へ転記する権利が確認できない。書名・出版年は書誌情報で確認できるが、オープンライセンスは確認できなかった。CBDB/Stanford University Press から明示許諾を得るまでは、Hucker 作業版は人手照合用の検索索引に限定し、英訳・本文・レコード全体を成果物へ複製しない。

- [Stanford University Press title page（調査時 HTTP 429で本文未確認）](https://www.sup.org/books/asian-studies/dictionary-official-titles-imperial-china)

### 3.3 王朝ごとの官職体系変化への対処

平坦な `表記 -> 官職ID` は採用しない。最低でも次の二層に分ける。

1. `office_name_instance`: 史料に現れる具体的な名称と使用区間。例として同じ「太守」でも王朝・行政単位・職掌が異なるインスタンスを許す。
2. `office_concept`: 翻訳時にまとめて説明できる上位概念。異なる王朝インスタンスを必要な場合だけ `broader/narrower/successor/roughly_equivalent` で結ぶ。

同じ漢字列でも王朝が違えばデフォルトでは別候補とし、同一視には典拠が必要である。訳語は `canonical_name_ja` とは別に、`translation_ja` と `translation_policy` を期間付きで持つ。たとえば固有官職名を残すのか、現代語説明を添えるのかを辞書の同定と混同しない。

本文から抽出した未知官職は、以下の順に処理する。

1. CBDB `OFFICE_CODES.c_office_chn/c_office_chn_alt` を完全一致。
2. 対象年に任官例があるコードを優先。
3. 前後の人物と `POSTED_TO_OFFICE_DATA` を照合。
4. 一意にならなければ新規 provisional instance を発行し、根拠チャンクを保存。
5. Hucker は権利許諾後、または内部の人手確認にのみ利用。

## 4. 実装評価の比較

| カテゴリ | 推奨 primary seed | 対象期の実用カバー | 機械可読性 | ライセンス上の主な問題 | 本文抽出の必要性 |
|---|---|---|---|---|---|
| 人物 | CBDB SQLite | 唐は高、五代・南北朝・隋は有用、戦国〜三国は低 | 高 | CC BY-NC-SA 4.0 | 前唐、とくに戦国〜三国で必須 |
| 地名 | TGAZ API/CSV + CHGIS crosswalk | 秦漢以後は有用、戦国前半は疎、自然地名等は別途 | 高 | CHGIS EULA、API CC BY-NC、GitHub GPL、Dataverse CC0が矛盾 | 戦国前半・自然地名・俗称で必須 |
| 官職 | CBDB `OFFICE_CODES` + 任官表 | 唐は強いが漢〜隋・五代の王朝別体系は不足 | 高 | CBDB CC BY-NC-SA。Hucker 作業版は権利不明 | 漢〜隋・五代で必須 |

### seed 生成の具体的な順序

1. CBDB SQLite と TGAZ CSV/SQL をバージョン・SHA-256付きで raw staging に固定する。
2. CBDB から人物、異名、官職、任官、地名 crosswalk を抽出する。
3. TGAZ から `BEG <= 959 AND END >= -403` の CHGIS レコードを抽出し、完全レコードは API または MySQL dump から補う。
4. Wikidata は CBDB/TGAZ にある外部 ID を優先して QID を結合し、ラベル一致だけの自動マージは禁止する。
5. DILA は仏教人物・寺院地名の補完 source とし、provenance とライセンスをレコード単位で保持する。
6. 本文 NER で未登録表記を抽出し、既存候補へ照合できないものだけ provisional entity にする。
7. 人手で確定した merge/split を辞書の正本へ反映し、参照チャンクを再処理する。

## 5. 確認済み事項と未確認事項

### 確認済み

- CBDB SQLite 2026-06-13版を取得・展開し、人物・異名・官職・任官・地名テーブルの schema と件数を実測した。
- CBDB API が匿名の `curl` で JSON を返し、別名・任官・住所を含むことを確認した。
- CBDB 学術版のライセンスが CC BY-NC-SA 4.0 であることを公式サイト、Swagger、配布 metadata で確認した。
- CHGIS V6 の Shapefile、data dictionary、EULA、年代カバー説明を Dataverse API で確認した。
- TGAZ の現行 API で地名+年検索、正規レコード、異表記、存続期間、親行政区、座標、現代位置を取得した。
- TGAZ CSV 71,647行、2018 MySQL dump、DILA 2026-06 TEI/XMLを取得した。
- Wikidata EntityData/SPARQL から中国史人物の異名・生没年を取得し、CC0 と週次 dump を確認した。
- CBDB Hucker 作業版が8,291件の machine-readable working data を公開していること、その品質状態を実測した。

### 未確認・要照会

- CBDB の公開 MySQL/MariaDB dump の現行公式 URL。SQLite からの変換手段はあるため blocker ではない。
- CBDB 由来 seed を翻訳 KB に組み込んだ場合の ShareAlike 適用範囲と、将来の商用利用可否。
- TGAZ/CHGIS の相互矛盾するライセンス表示の優先順位、および派生した異名辞書の再配布可否。
- DILA place XML に含まれる Academia Sinica 由来レコードの再配布条件。
- Hucker 作業版の OCR、翻刻、英訳、JSON データに対する権利者の明示許諾。
- 史料上の全エンティティを分母にした厳密なカバー率。これは資治通鑑本文を全巻 NER して照合しない限り算出できない。

## 判定

### 人物: 使える初期ソース + 取り込み方法あり

- **推奨:** CBDB SQLite の `BIOG_MAIN + ALTNAME_DATA + ALTNAME_CODES`。
- **アクセス:** [Hugging Face](https://huggingface.co/datasets/cbdb/cbdb-sqlite) の versioned ZIP を取得し、SHA-256を固定。個別確認は [CBDB API](https://cbdb.fas.harvard.edu/cbdbapi/)。
- **補完:** Wikidata QID/aliases（CC0）、仏教人物は DILA TEI/API（CC BY-SA 3.0）。
- **注意:** CBDB は CC BY-NC-SA 4.0。戦国〜三国は疎なので、本文 NER からの provisional person 作成を必須とする。

### 地名: 使える初期ソース + 取り込み方法あり

- **推奨:** TGAZ の時代付き CHGIS レコード。`name + yr` API と CSV/MySQL dumpを併用する。
- **アクセス:** [TGAZ API](https://chgis.hudci.org/tgaz/)、[GitHub CSV/SQL](https://github.com/cga-harvard/tgaz)、[Dataverse dump](https://doi.org/10.7910/DVN/H3OB28)。
- **補完:** CBDB `ADDR_CODES` で人物・任地 crosswalk、Wikidata で現代 QID・自然地名、DILA で仏教地名。
- **注意:** CHGIS EULA、APIの CC BY-NC 4.0、GitHub GPLv3、Dataverse CC0 が矛盾する。内部 seed は作れるが、全量を公開する前に書面確認が必要。戦国前半は本文抽出で補う。

### 官職: 部分的に使える初期ソース + 取り込み方法あり

- **推奨:** CBDB `OFFICE_CODES + POSTED_TO_OFFICE_DATA + OFFICE_*`。
- **アクセス:** 人物と同じ SQLite から抽出し、異表記、王朝コード、実任官年代、出典を保持する。
- **補完:** 漢〜隋・五代は本文から自動抽出し、CBDB の唐コードへ無理に統合せず provisional `office_name_instance` として起票する。
- **注意:** CBDB は CC BY-NC-SA 4.0。Hucker 作業版は machine-readable だが、品質が暫定かつ権利表示がないため、許諾までは内部照合専用とする。

### 初期辞書スキーマ案

平坦な `alias -> canonical_name` では同名異人・同名異地・時代で意味が変わる官職を扱えない。最小構成を次とする。

```yaml
entity:
  entity_id: "person:cbdb:25403"      # プロジェクト内の安定ID
  entity_type: "person"               # person | place | office_name_instance
  canonical_name_zh: "諸葛亮"
  canonical_name_ja: "諸葛亮"
  valid_from: 181                      # BCEは負数。未知はnull
  valid_to: 234
  dynasty_codes: ["三國蜀"]
  status: "seed"                      # seed | provisional | verified | rejected

names:
  - surface: "孔明"
    name_type: "courtesy_name"        # primary | courtesy | posthumous | temple | alias...
    script: "Hant"
    valid_from: null
    valid_to: null
    source_assertion_id: "srcassert:..."

authority_ids:
  - authority: "CBDB"
    id: "25403"
    same_as_status: "exact"
  - authority: "Wikidata"
    id: "Q..."
    same_as_status: "reviewed"

source_assertions:
  - source: "CBDB"
    source_version: "2026-06-13"
    source_url: "https://huggingface.co/datasets/cbdb/cbdb-sqlite"
    license: "CC-BY-NC-SA-4.0"
    source_record_id: "25403"
    retrieved_at: "2026-06-20"
    confidence: "source_asserted"

place_detail:                       # placeのみ
  feature_type: "県"
  parent_entity_id: "place:tgaz:hvd_..."
  longitude: 112.59631
  latitude: 34.73157
  modern_place_id: "wikidata:Q..."
  modern_place_text: "今..."

office_detail:                      # office_name_instanceのみ
  office_concept_id: "office-concept:..."
  jurisdiction_level: null
  translation_ja: null
  predecessor_ids: []
  successor_ids: []
```

検索用には別テーブル `name_index(entity_type, normalized_surface, entity_id, valid_from, valid_to, name_type)` を作り、1表記から複数候補を返す。`source_assertions` を独立させることで、同じ正規名・年代・同一関係について典拠間の矛盾を保持でき、ライセンス別 export も可能になる。

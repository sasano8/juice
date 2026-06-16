# 用語集（Glossary）

juice で「カタログ」前後の語が重なりやすいので、正式な意味をここに固定する。
特に **catalog**（juice のコア概念）と **okf_catalog_cache**（OKF 由来の周辺機能）は別物で、
混同しないこと。

## catalog（コア概念）＝ 成果物の構造インベントリ

**catalog = 成果物（asset）がどう organize されているかの標準化モデル。** 次の 3 階層からなり、
**成果物ディレクトリがメインオブジェクト**で、上位 2 軸に「属する」かたちで分類される。

| 階層 | 役割 | 例 | 物理対応 |
|------|------|----|----------|
| レイヤー1 | namespace（リソース空間の区画） | `default` | `namespaces/<namespace>/` |
| レイヤー2 | layer（= **1 つの registry**。成果物の種類） | `tools` / `skills` / `bundles` / `python_packages` / … | `…/<namespace>/<layer>/` |
| 成果物ディレクトリ | **name（主役の資産＝1パッケージ=1ディレクトリ）** | `weather` | `…/<layer>/<name>/` |

物理レイアウトは `namespaces/<namespace>/<layer>/<name>/` で、**Kubernetes の API パス
`/namespaces/<ns>/<kind>/<name>`（namespace × kind × name）と同型**（[config.py](../src/core/config.py) 冒頭コメント）。
最上位は `namespaces/`（容器）。その下に namespace、さらに**各 layer = 1 つの registry**（フォーマット別の
パッケージ索引）が並ぶ。local の bucket は既定 `.`（カレント）なので最上位がそのまま `namespaces/` になる。

```
namespaces/                      ← 最上位（namespace の容器）
└── default/                     ← namespace（レイヤー1）
    ├── tools/                   ← layer = registry（レイヤー2）
    │   └── weather/             ← 成果物ディレクトリ（name・主役）
    │       └── index.md         ← entry file
    ├── skills/ └ report-weather/SKILL.md
    ├── subagents/ └ forecaster/index.md
    ├── bundles/                 ← bundle レイヤ（juice の bundle 形式）
    │   └── mcp_weather-bot/ ├ bundle.yml  └ vendor/ …（生成物）
    ├── workflows/ └ weather-service/index.md
    ├── schedules/ └ morning-brief/index.md
    ├── instances/ └ tokyo-weather-bot/index.yml
    └── python_packages/  …      ← (将来) PyPI 様の registry（bundles と同列。構造のみ・未実装）
```

> **layer = registry:** 各 layer ディレクトリそれ自体が 1 つの registry（パッケージ索引）。`bundles` /
> `tools` と同じ粒度で、将来 `datasets` / `python_packages` を**同列に**足せる。`python_packages/` に wheel を
> 置けば juice の registry を PyPI のように使える、という拡張余地（現状は構造のみ・未実装）。
>
> **命名規約:** レイヤキー（CLI コマンド・manifest 上の概念名）は単数形 `bundle` だが、registry 上の
> ディレクトリ名は他レイヤと揃えて複数形 **`bundles`**（`config.LAYERS["bundle"] = "bundles"`）。

- **registry** … **1 つの layer = 1 つの registry**（あるフォーマットのパッケージ索引。`tools` / `bundles` /
  将来 `python_packages` …）。物理的なストア（local / s3 …）の上に乗る。`Registry` クラスが 1 layer を、
  `RegistryArray` が 1 namespace の全 registry を束ねる。catalog（成果物の構造＝論理）と registry（その置き場）は
  同じものの両面で、衝突ではない。
- **catalog の閲覧口** … `juice all list`（全 registry を依存順に横断一覧）。

## okf_catalog_cache（周辺機能・AI 連携用）＝ OKF メタデータの派生キャッシュ

**okf_catalog_cache = 各ドキュメントの frontmatter から収集した [OKF](https://github.com/GoogleCloudPlatform/knowledge-catalog)
メタデータを標準スキーマへ射影して束ねた派生ビュー。** 主に **AI が資産を探す/参照する**ための材料で、
**システムの主概念ではない**。OKF は正式な管理対象ではなく不安定なので、コアの語「catalog」を避けて
`okf_catalog_cache` と呼んで区別する。

- 実装: [src/core/okf_catalog_cache.py](../src/core/okf_catalog_cache.py)（`build_okf_catalog_cache` /
  `filter_okf_catalog_cache`）。CLI は `juice okf-cache [--type <concept type>] [--tag <tag>]`。
- データ源: [index.py](../src/core/index.py) の集約（`juice.index.yml`）＝メタデータの一般キャッシュを土台にする
  （再発明しない）。標準スキーマ＝identity（`name` / `layer`）＋ OKF `type` ＋ OKF 推奨フィールド
  （`title` / `description` / `tags` / `resource` / `timestamp`、任意・欠落は省略）。
- 注意: **OKF の用語では「catalog」がこの収集物を指す**（リポジトリ名 `knowledge-catalog`）。juice では
  「catalog」を上記コア概念に予約し、OKF の収集物は `okf_catalog_cache` と呼ぶ。OKF を読むときは語の向きが
  逆になる点に注意。

## 関連する近接語

| 語 | 意味 | 実装 |
|----|------|------|
| **index** | registry 全 frontmatter の**一般メタデータ・キャッシュ**（高速化・drift 検出用）。`juice.index.yml` は生成物 | `index.py` / `juice registry index` |
| **registry verify** | registry の健全性検査（name=dir 一致・OKF 適合・index drift の 3 点） | `metadata.py` / `index.py` / `juice registry verify` |

> 一言でいうと: **catalog＝在庫の構造**（コア）、**registry＝在庫の置き場**、**index＝メタデータの一般キャッシュ**、
> **okf_catalog_cache＝OKF メタデータの AI 向け派生ビュー**（周辺）。

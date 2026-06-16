# 用語集（Glossary）

juice で「カタログ」前後の語が重なりやすいので、正式な意味をここに固定する。
特に **catalog**（juice のコア概念）と **okf_catalog_cache**（OKF 由来の周辺機能）は別物で、
混同しないこと。

## catalog（コア概念）＝ 成果物の構造インベントリ

**catalog = 成果物（asset）がどう organize されているかの標準化モデル。** 次の 3 階層からなり、
**成果物ディレクトリがメインオブジェクト**で、上位 2 軸に「属する」かたちで分類される。

| 階層 | 役割 | 例 | 物理対応 |
|------|------|----|----------|
| レイヤー1 | namespace（リソース空間の区画） | `default` | `registries/<bucket>/<namespace>/` |
| レイヤー2 | kind / layer（成果物の種類） | `tools` / `skills` / `subagents` / … | `…/<namespace>/<layer>/` |
| 成果物ディレクトリ | **name（主役の資産＝1パッケージ=1ディレクトリ）** | `weather` | `…/<layer>/<name>/` |

物理的な位置は `(bucket, namespace, layer/name)` で決まり、**Kubernetes の namespace × kind × name と
同じリソースモデル**（[config.py](../src/core/config.py) 冒頭コメント）。

- **registry** … catalog を**物理的に保持するストア**（local / s3 …）。catalog（中身の論理）と registry
  （容れ物）は同じものの両面で、衝突ではない。実装は `RegistryArray`。
- **catalog の閲覧口** … `juice all list`（全レイヤを依存順に横断一覧）。

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

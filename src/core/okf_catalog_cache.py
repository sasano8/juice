"""OKF カタログ・キャッシュ（AI 連携用の周辺機能）。

**用語の区別（重要）:**
- **catalog**（juice のコア概念）… 成果物の**構造インベントリ**＝レイヤー1(namespace) /
  レイヤー2(kind) / 成果物ディレクトリ(name=主役) の標準化モデル。registry が物理的に保持し、
  `juice all list` が閲覧口。**本モジュールは catalog ではない。**
- **okf_catalog_cache**（本モジュール）… 各ドキュメントの frontmatter から収集した OKF メタデータを
  標準スキーマへ射影して束ねた**派生キャッシュ**。OKF は正式管理対象でなく不安定なため、コアの語
  「catalog」を避けて `okf_catalog_cache` と呼んで区別する。**主に AI が資産を探す/参照する**ための
  ビューで、システムの主概念ではない。glossary は [docs/glossary.md](../../docs/glossary.md)。

データは [index.py](index.py) の集約（`juice.index.yml` がそのキャッシュ）を土台にし、各資産の
メタデータを標準フィールドへ射影する。再発明せず index を使う（設計原則）。

**標準スキーマ:** identity（`name` / `layer`）＋ OKF（`type` 必須・実装済）＋ OKF 推奨フィールド
（`title` / `description` / `tags` / `resource` / `timestamp`）。推奨フィールドは
**任意**で欠落を許容（verify を壊さない＝報告のみ）。あるものだけ射影する。
"""

from __future__ import annotations

from .index import build_index
from .registry import RegistryArray

# OKF 推奨フィールド（任意）。`type` は OKF 必須で別途 verify 済み。
OKF_RECOMMENDED: tuple[str, ...] = ("title", "description", "tags", "resource", "timestamp")

# OKF カタログ・キャッシュの標準スキーマ（出力に現れうるキー）。identity ＋ type ＋ OKF 推奨。
OKF_CACHE_FIELDS: tuple[str, ...] = ("name", "layer", "type", *OKF_RECOMMENDED)


def build_okf_catalog_cache(registries: RegistryArray) -> list[dict]:
    """全資産を OKF 標準スキーマへ射影した list[dict]（AI 連携用の派生キャッシュ）を返す。

    index の集約（ALL_ORDER 順・名前昇順）が土台なので決定的。各エントリは
    `name` / `layer` を必ず持ち、`type` と OKF 推奨フィールドは**存在すれば**含める（欠落は省略）。
    """
    entries: list[dict] = []
    for pkg in build_index(registries)["packages"]:
        meta = pkg["metadata"]
        entry: dict = {"name": pkg["dir"], "layer": pkg["layer"]}
        for field in ("type", *OKF_RECOMMENDED):
            value = meta.get(field)
            if value not in (None, "", [], {}):
                entry[field] = value
        entries.append(entry)
    return entries


def filter_okf_catalog_cache(
    entries: list[dict], *, type_: str | None = None, tag: str | None = None
) -> list[dict]:
    """キャッシュを type / tag で絞り込む（指定が無い軸はそのまま）。"""
    out = entries
    if type_ is not None:
        out = [e for e in out if e.get("type") == type_]
    if tag is not None:
        out = [e for e in out if tag in (e.get("tags") or [])]
    return out

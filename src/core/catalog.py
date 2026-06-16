"""資産カタログ（横断ビュー）。

**catalog = 資産のメタデータを標準スキーマで束ね、レイヤ横断で一覧・検索する概念。**
catalog は新しい registry レイヤ（資産の種類）ではなく、全レイヤを横断する**ビュー**。
データは [index.py](index.py) の集約（`juice.index.yml` がそのキャッシュ）を土台にし、
各資産のメタデータを**標準フィールド**へ射影する。再発明せず index を使う（設計原則）。

**標準スキーマ:** identity（`name` / `layer`）＋ OKF（`type` 必須・実装済）＋ OKF 推奨フィールド
（`title` / `description` / `tags` / `resource` / `timestamp`）。推奨フィールドは
**任意**で欠落を許容（verify を壊さない＝報告のみ）。あるものだけ射影する。
"""

from __future__ import annotations

from .index import build_index
from .registry import RegistryArray

# OKF 推奨フィールド（任意）。`type` は OKF 必須で別途 verify 済み。
OKF_RECOMMENDED: tuple[str, ...] = ("title", "description", "tags", "resource", "timestamp")

# カタログ標準スキーマ（出力に現れうるキー）。identity ＋ type ＋ OKF 推奨。
CATALOG_FIELDS: tuple[str, ...] = ("name", "layer", "type", *OKF_RECOMMENDED)


def build_catalog(registries: RegistryArray) -> list[dict]:
    """全資産を標準スキーマへ射影したカタログ（list[dict]）を返す。

    index の集約（ALL_ORDER 順・名前昇順）が土台なので決定的。各エントリは
    `name` / `layer` を必ず持ち、`type` と OKF 推奨フィールドは**存在すれば**含める（欠落は省略）。
    """
    catalog: list[dict] = []
    for pkg in build_index(registries)["packages"]:
        meta = pkg["metadata"]
        entry: dict = {"name": pkg["dir"], "layer": pkg["layer"]}
        for field in ("type", *OKF_RECOMMENDED):
            value = meta.get(field)
            if value not in (None, "", [], {}):
                entry[field] = value
        catalog.append(entry)
    return catalog


def filter_catalog(
    entries: list[dict], *, type_: str | None = None, tag: str | None = None
) -> list[dict]:
    """カタログを type / tag で絞り込む（指定が無い軸はそのまま）。"""
    out = entries
    if type_ is not None:
        out = [e for e in out if e.get("type") == type_]
    if tag is not None:
        out = [e for e in out if tag in (e.get("tags") or [])]
    return out

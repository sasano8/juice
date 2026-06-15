"""registry メタデータインデックスの生成と drift 検出（E004 要件 4）。

各パッケージの md/yml frontmatter（[metadata.py](metadata.py)）から抽出したメタデータを
**リポジトリトップの 1 ファイル**（既定 `juice.index.yml`）に集約する。毎回 frontmatter を
パースするコストを下げる狙い（高速化）。

**source of truth は registry の md/yml**。インデックスは**生成物**で、`build_index` で再生成して
同期する。整合性は `digest`（内容ハッシュ）で担保し、md 変更との **drift を検出**する
（C005 の `manifest_digest` / `lock_status` と同型）。
設計原則「宣言的＝唯一の正」「生成物を焼かず再生成で同期」に従う。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from .config import ALL_ORDER
from .metadata import parse_metadata
from .registry import RegistryArray

# インデックスのフォーマット版。スキーマを変えたら上げる。
INDEX_VERSION = 1

# 生成物であることを示すヘッダ（手編集を抑止）。
_INDEX_HEADER = "# juice.index.yml — 生成物。手で編集しない（`juice registry index` で再生成）。\n"


def index_digest(packages: list[dict]) -> str:
    """インデックスの packages から決定的な `sha256:...` を作る（drift 検出用）。"""
    canonical = json.dumps(packages, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_index(registries: RegistryArray) -> dict:
    """全レイヤを走査し、各パッケージの抽出メタデータを集めたインデックス dict を返す。

    決定的: レイヤは ALL_ORDER 順、パッケージは名前昇順。同じ registry からは常に同じ index。
    """
    packages: list[dict] = []
    for layer in ALL_ORDER:
        for dir_name in sorted(registries.list(layer)):
            metadata = parse_metadata(registries.read(layer, dir_name))
            packages.append({"layer": layer, "dir": dir_name, "metadata": metadata})
    return {
        "indexVersion": INDEX_VERSION,
        "namespace": registries.namespace,
        "digest": index_digest(packages),
        "packages": packages,
    }


def dump_index(index: dict) -> str:
    """インデックスを juice.index.yml のテキスト（YAML＋ヘッダ）に決定的に直列化する。"""
    body = yaml.safe_dump(index, sort_keys=False, allow_unicode=True, default_flow_style=False)
    return _INDEX_HEADER + body


def write_index(registries: RegistryArray, out_path: str) -> dict:
    """インデックスを生成して out_path に書き出す。要約 dict を返す（冪等）。"""
    index = build_index(registries)
    Path(out_path).write_text(dump_index(index), encoding="utf-8")
    return {"out": out_path, "digest": index["digest"], "count": len(index["packages"])}


def read_index(path: str) -> dict | None:
    """juice.index.yml を読み dict で返す。ファイルが無ければ None。"""
    p = Path(path)
    if not p.exists():
        return None
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def index_status(registries: RegistryArray, path: str) -> dict:
    """registry の現状とインデックスファイルの整合状態を返す。

    `{present, drift, expected, found}`:
    - present … インデックスファイルが存在するか
    - drift   … 記録された digest が現在の registry と食い違うか（present のときのみ意味を持つ）
    - expected… registry から再生成した現在の digest
    - found   … インデックスに記録された digest（無ければ None）
    """
    expected = build_index(registries)["digest"]
    index = read_index(path)
    if index is None:
        return {"present": False, "drift": False, "expected": expected, "found": None}
    found = index.get("digest")
    return {"present": True, "drift": found != expected, "expected": expected, "found": found}

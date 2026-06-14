"""mcp_bundled のバンドル。

2 段階:
- `register`: bundle 宣言ファイルを成果物名のスロット（`<name>/bundle.yml`）へ保存する（登録）。
- `build`: 保存済み `bundle.yml`（include 等）と `index.md`（定義）を参照し、内包物
  （subagent / skill / tool）を registry から解決・収集して 1 つの成果物にまとめる（実体化）。

宣言は「何を内包するか」をパイプライン的に宣言したもので、ここではそれを読み取って再現するだけ。
"""

from __future__ import annotations

from typing import Any

import yaml

from .config import ENTRY_FILES, LAYERS
from .registry import RegistryArray

# bundle 宣言の保存ファイル名（mcp_bundled パッケージ配下）
SPEC_FILE = "bundle.yml"

# vendoring 先ディレクトリ（mcp_bundled パッケージ配下）。registry と同じ構造でミラーする。
VENDOR_DIR = "vendor"

# include 未指定時の既定（内包物を上から順に解決する）
DEFAULT_INCLUDE = ["subagent", "skills", "tools"]


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """`---` で囲った YAML frontmatter と本文に分割する。

    fence が無ければ全体を本文（meta は空）として扱う。
    """
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            meta = yaml.safe_load(parts[1]) or {}
            return meta, parts[2].lstrip("\n")
    return {}, text


def _load(registries: RegistryArray, layer: str, name: str) -> dict:
    meta, body = parse_frontmatter(registries.read(layer, name))
    return {"layer": layer, "name": name, "meta": meta, "body": body}


def _deps(meta: dict, include: list[str]) -> list[tuple[str, str]]:
    """mcp_bundled の frontmatter から (layer, name) の内包物一覧を include 順に返す。"""
    deps: list[tuple[str, str]] = []
    if "subagent" in include and meta.get("subagent"):
        deps.append(("subagent", meta["subagent"]))
    if "skills" in include and meta.get("skills"):
        deps += [("skill", s) for s in meta["skills"]]
    if "tools" in include and meta.get("tools"):
        tools = meta["tools"]
        names = list(tools.keys()) if isinstance(tools, dict) else list(tools)
        deps += [("tool", t) for t in names]
    return deps


def collect(registries: RegistryArray, name: str, include: list[str] | None = None) -> dict:
    """mcp_bundled `name` とその内包物を（コピーせず）収集した構造を返す。"""
    include = include or DEFAULT_INCLUDE
    root = _load(registries, "mcp_bundled", name)
    included: dict[str, Any] = {
        f"{layer}:{dep}": _load(registries, layer, dep)
        for layer, dep in _deps(root["meta"], include)
    }
    return {"kind": "bundle", "mcp_bundled": name, "meta": root["meta"], "body": root["body"], "included": included}


def _vendor(registries: RegistryArray, name: str, include: list[str]) -> list[str]:
    """`<name>/vendor/` をクリーンしてから内包物を registry と同じ構造でコピーする。"""
    registries.remove("mcp_bundled", name, VENDOR_DIR)  # 旧 vendor を一掃
    meta, _ = parse_frontmatter(registries.read("mcp_bundled", name))
    vendored: list[str] = []
    for layer, dep in _deps(meta, include):
        raw = registries.read(layer, dep)
        rel = f"{VENDOR_DIR}/{LAYERS[layer]}/{dep}/{ENTRY_FILES[layer]}"
        registries.write("mcp_bundled", name, rel, raw)
        vendored.append(f"mcp_bundled/{name}/{rel}")
    return vendored


def build(registries: RegistryArray, name: str) -> dict:
    """登録済み `bundle.yml` を参照し vendor を最新化する（refresh）。

    内包物を `vendor/<layer 複数形>/<dep>/<entry>` に registry と同じ構造でミラーする。
    """
    spec = yaml.safe_load(registries.read("mcp_bundled", name, SPEC_FILE)) or {}
    vendored = _vendor(registries, name, spec.get("include") or DEFAULT_INCLUDE)
    return {"kind": "build", "mcp_bundled": name, "vendored": vendored}


def bundle(registries: RegistryArray, name: str, spec_text: str) -> dict:
    """フル実行: クリーンアップ → bundle.yml 再配置 → build。

    生成物（vendor/ と既存 bundle.yml）を削除してから宣言を置き直し、build まで通す。
    定義 `index.md` は残す（ビルドの入力）。
    """
    registries.remove("mcp_bundled", name, VENDOR_DIR)
    registries.remove("mcp_bundled", name, SPEC_FILE)
    registries.write("mcp_bundled", name, SPEC_FILE, spec_text)
    return build(registries, name)

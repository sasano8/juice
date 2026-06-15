"""外部パッケージの digest 解決（C002 の積み残し）。

`juice.lock` の `digest` 欄を埋めるための **副作用の境界**。ネットワーク I/O をこのモジュールに
隔離し、`lock.build_lock` には「resolver（純関数として注入する callable）」だけを渡す
（依存注入）。これにより lock の生成ロジックは純粋なまま保ち、テストは resolver を stub できる。

digest の形式は npm registry の **Subresource Integrity（SRI, 例 `sha512-...`）** をそのまま採用する
（独自正規化を避ける＝設計原則「標準フォーマット準拠」）。OCI 等は必要になってから（YAGNI）。

resolver の規約:
- シグネチャは `(package: str | None, version: str | None) -> str | None`。
- 解決できない（package 不在 / npm 形式でない / ネットワーク不可 / 取得失敗）場合は **None** を返す
  （例外は投げない）。None は「digest 未解決」を意味し、lock は従来どおり `digest: null` になる。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable

# resolver の型。lock.build_lock がこの shape の callable を受け取る。
DigestResolver = Callable[[str | None, str | None], str | None]

# npm registry のベース URL。package メタデータを GET する。
NPM_REGISTRY = "https://registry.npmjs.org"
_DEFAULT_TIMEOUT = 5.0


def null_resolver(package: str | None, version: str | None) -> None:
    """常に None を返す resolver（digest を解決しない既定動作）。"""
    return None


def _looks_like_npm(package: str | None) -> bool:
    """package が npm パッケージ名らしいか（`@scope/name` か単純名）。URL や path は除外。"""
    if not package:
        return False
    if "://" in package or package.startswith((".", "/")):
        return False
    # スコープ付き（@scope/name）か、スラッシュを含まない単純名のみを npm とみなす。
    if package.startswith("@"):
        return package.count("/") == 1
    return "/" not in package


def npm_digest(
    package: str | None,
    version: str | None,
    *,
    fetch: Callable[[str], bytes] | None = None,
    timeout: float = _DEFAULT_TIMEOUT,
) -> str | None:
    """npm registry から package の SRI integrity（`sha512-...`）を解決する。

    - `version` 指定時はその版、未指定なら `dist-tags.latest` を使う。
    - `fetch` を注入するとネットワークを差し替えられる（テスト用）。既定は urllib。
    - 取得・解析に失敗したら None（呼び出し側は従来どおり digest 未解決として扱う）。
    """
    if not _looks_like_npm(package):
        return None
    fetcher = fetch if fetch is not None else lambda url: _http_get(url, timeout)
    try:
        raw = fetcher(f"{NPM_REGISTRY}/{package}")
        meta = json.loads(raw)
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return None
    ver = version or meta.get("dist-tags", {}).get("latest")
    if not ver:
        return None
    dist = meta.get("versions", {}).get(ver, {}).get("dist", {})
    integrity = dist.get("integrity")
    if isinstance(integrity, str) and integrity:
        return integrity
    # 古い package は integrity が無く shasum（sha1 hex）のみ持つことがある。
    shasum = dist.get("shasum")
    if isinstance(shasum, str) and shasum:
        return f"sha1-hex:{shasum}"
    return None


def _http_get(url: str, timeout: float) -> bytes:
    """URL を GET して本文を返す（失敗時は例外。呼び出し側が None に丸める）。"""
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (https 固定)
        return resp.read()

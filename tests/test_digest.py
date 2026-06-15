"""外部パッケージ digest 解決（digest.py）と lock 連携のテスト。

ネットワークには出ない: npm registry へのアクセスは `fetch` 注入で stub する。
"""

from __future__ import annotations

import json

from src.core.digest import npm_digest, null_resolver
from src.core.lock import build_lock, lock_to_dict
from src.core.manifest import parse_manifest

# stub する npm registry 応答（@example/mcp-weather の最小メタデータ）。
_NPM_META = {
    "dist-tags": {"latest": "2.1.0"},
    "versions": {
        "2.0.0": {"dist": {"integrity": "sha512-OLD=="}},
        "2.1.0": {"dist": {"integrity": "sha512-NEW=="}},
    },
}


def _fetch_ok(url: str) -> bytes:
    return json.dumps(_NPM_META).encode("utf-8")


def _fetch_boom(url: str) -> bytes:
    raise OSError("network down")


def test_npm_digest_uses_latest_when_version_absent() -> None:
    assert npm_digest("@example/mcp-weather", None, fetch=_fetch_ok) == "sha512-NEW=="


def test_npm_digest_uses_requested_version() -> None:
    assert npm_digest("@example/mcp-weather", "2.0.0", fetch=_fetch_ok) == "sha512-OLD=="


def test_npm_digest_unknown_version_returns_none() -> None:
    assert npm_digest("@example/mcp-weather", "9.9.9", fetch=_fetch_ok) is None


def test_npm_digest_network_failure_returns_none() -> None:
    # 取得失敗は例外を投げず None（従来どおり digest 未解決）。
    assert npm_digest("@example/mcp-weather", None, fetch=_fetch_boom) is None


def test_npm_digest_falls_back_to_shasum() -> None:
    meta = {"dist-tags": {"latest": "1.0.0"}, "versions": {"1.0.0": {"dist": {"shasum": "abc123"}}}}
    digest = npm_digest("old-pkg", None, fetch=lambda url: json.dumps(meta).encode())
    assert digest == "sha1-hex:abc123"


def test_npm_digest_rejects_non_npm_package() -> None:
    # URL や path 形式は npm とみなさない（fetch を呼ばずに None）。
    called = []
    fetch = lambda url: called.append(url) or b"{}"  # noqa: E731
    assert npm_digest("https://example.com/x", None, fetch=fetch) is None
    assert npm_digest("./local/path", None, fetch=fetch) is None
    assert npm_digest(None, None, fetch=fetch) is None
    assert called == []  # ネットワークに触れていない


def test_null_resolver_always_none() -> None:
    assert null_resolver("@example/x", "1.0.0") is None


_MANIFEST = """\
apiVersion: juice/v1
mcp_servers:
  - name: weather
    package: "@example/mcp-weather"
    version: 2.1.0
"""


def test_build_lock_without_resolver_keeps_digest_none() -> None:
    lock = build_lock(parse_manifest(_MANIFEST))
    assert lock.mcp_servers[0].digest is None  # 既定は未解決（後方互換）


def test_build_lock_with_resolver_records_digest() -> None:
    def resolver(package, version):
        return f"sha512-{package}@{version}"

    lock = build_lock(parse_manifest(_MANIFEST), digest_resolver=resolver)
    assert lock.mcp_servers[0].digest == "sha512-@example/mcp-weather@2.1.0"
    assert lock_to_dict(lock)["mcp_servers"][0]["digest"] == "sha512-@example/mcp-weather@2.1.0"


def test_resolver_does_not_affect_manifest_digest() -> None:
    # digest は解決値であって spec ではない → manifestDigest（drift 検出）には影響しない。
    base = build_lock(parse_manifest(_MANIFEST)).manifest_digest
    with_digest = build_lock(
        parse_manifest(_MANIFEST), digest_resolver=lambda p, v: "sha512-X=="
    ).manifest_digest
    assert base == with_digest


def test_build_lock_with_resolver_is_idempotent() -> None:
    resolver = lambda p, v: "sha512-STABLE=="  # noqa: E731
    a = build_lock(parse_manifest(_MANIFEST), digest_resolver=resolver)
    b = build_lock(parse_manifest(_MANIFEST), digest_resolver=resolver)
    assert lock_to_dict(a) == lock_to_dict(b)

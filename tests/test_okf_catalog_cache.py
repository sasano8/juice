"""OKF カタログ・キャッシュ（okf_catalog_cache.py / AI 連携用の派生ビュー）のテスト。"""

from __future__ import annotations

from pathlib import Path

from src.core import create_registries
from src.core.okf_catalog_cache import (
    OKF_CACHE_FIELDS,
    build_okf_catalog_cache,
    filter_okf_catalog_cache,
)


def test_cache_fields_include_identity_and_okf() -> None:
    # identity（name/layer）＋ type ＋ OKF 推奨フィールド。
    assert OKF_CACHE_FIELDS[:3] == ("name", "layer", "type")
    for f in ("title", "description", "tags", "resource", "timestamp"):
        assert f in OKF_CACHE_FIELDS


def test_build_cache_projects_standard_fields(registries) -> None:
    cache = build_okf_catalog_cache(registries)
    by_name = {e["name"]: e for e in cache}
    weather = by_name["weather"]
    assert weather["layer"] == "tool"
    assert weather["type"] == "mcp-server"  # OKF concept type
    # 欠落フィールドは省略される（title 等は最小レジストリに無い）。
    assert "title" not in weather


def test_build_cache_includes_optional_okf_fields(bucket: str) -> None:
    # tags / description を持つ資産はキャッシュに射影される。
    asset = Path(bucket) / "namespaces" / "default" / "skills" / "tagged" / "SKILL.md"
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_text(
        "---\nkind: skill\nname: tagged\ntype: skill\n"
        "description: タグ付き\ntags: [alpha, beta]\n---\n",
        encoding="utf-8",
    )
    cache = build_okf_catalog_cache(create_registries(bucket=bucket, namespace="default"))
    tagged = next(e for e in cache if e["name"] == "tagged")
    assert tagged["description"] == "タグ付き"
    assert tagged["tags"] == ["alpha", "beta"]


def test_filter_cache_by_type(registries) -> None:
    cache = build_okf_catalog_cache(registries)
    tools = filter_okf_catalog_cache(cache, type_="mcp-server")
    assert tools and all(e["type"] == "mcp-server" for e in tools)
    assert all(e["layer"] == "tool" for e in tools)


def test_filter_cache_by_tag(bucket: str) -> None:
    asset = Path(bucket) / "namespaces" / "default" / "tools" / "humidity" / "index.md"
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_text(
        "---\nkind: tool\nname: humidity\ntype: mcp-server\ntags: [weather]\n---\n",
        encoding="utf-8",
    )
    cache = build_okf_catalog_cache(create_registries(bucket=bucket, namespace="default"))
    weather_tagged = filter_okf_catalog_cache(cache, tag="weather")
    assert {e["name"] for e in weather_tagged} == {"humidity"}


def test_filter_cache_no_filters_returns_all(registries) -> None:
    cache = build_okf_catalog_cache(registries)
    assert filter_okf_catalog_cache(cache) == cache

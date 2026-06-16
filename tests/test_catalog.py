"""資産カタログ（catalog.py / 横断ビュー）のテスト。"""

from __future__ import annotations

from pathlib import Path

from src.core import create_registries
from src.core.catalog import CATALOG_FIELDS, build_catalog, filter_catalog


def test_catalog_fields_include_identity_and_okf() -> None:
    # identity（name/layer）＋ type ＋ OKF 推奨フィールド。
    assert CATALOG_FIELDS[:3] == ("name", "layer", "type")
    for f in ("title", "description", "tags", "resource", "timestamp"):
        assert f in CATALOG_FIELDS


def test_build_catalog_projects_standard_fields(registries) -> None:
    catalog = build_catalog(registries)
    by_name = {e["name"]: e for e in catalog}
    weather = by_name["weather"]
    assert weather["layer"] == "tool"
    assert weather["type"] == "mcp-server"  # OKF concept type
    # 欠落フィールドは省略される（title 等は最小レジストリに無い）。
    assert "title" not in weather


def test_build_catalog_includes_optional_okf_fields(bucket: str) -> None:
    # tags / description を持つ資産は catalog に射影される。
    asset = Path(bucket) / "default" / "skills" / "tagged" / "SKILL.md"
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_text(
        "---\nkind: skill\nname: tagged\ntype: skill\n"
        "description: タグ付き\ntags: [alpha, beta]\n---\n",
        encoding="utf-8",
    )
    catalog = build_catalog(create_registries(bucket=bucket, namespace="default"))
    tagged = next(e for e in catalog if e["name"] == "tagged")
    assert tagged["description"] == "タグ付き"
    assert tagged["tags"] == ["alpha", "beta"]


def test_filter_catalog_by_type(registries) -> None:
    catalog = build_catalog(registries)
    tools = filter_catalog(catalog, type_="mcp-server")
    assert tools and all(e["type"] == "mcp-server" for e in tools)
    assert all(e["layer"] == "tool" for e in tools)


def test_filter_catalog_by_tag(bucket: str) -> None:
    asset = Path(bucket) / "default" / "tools" / "humidity" / "index.md"
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_text(
        "---\nkind: tool\nname: humidity\ntype: mcp-server\ntags: [weather]\n---\n",
        encoding="utf-8",
    )
    catalog = build_catalog(create_registries(bucket=bucket, namespace="default"))
    weather_tagged = filter_catalog(catalog, tag="weather")
    assert {e["name"] for e in weather_tagged} == {"humidity"}


def test_filter_catalog_no_filters_returns_all(registries) -> None:
    catalog = build_catalog(registries)
    assert filter_catalog(catalog) == catalog

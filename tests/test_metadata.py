"""メタデータ抽出と name 検証（metadata.py / E004）のテスト。"""

from __future__ import annotations

from pathlib import Path

from src.core import create_registries
from src.core.metadata import (
    OKF_MD_LAYERS,
    extract_name,
    parse_metadata,
    verify_names,
    verify_okf,
)

_FRONTMATTER = """\
---
kind: tool
name: weather
type: mcp-server
---

# weather
本文。
"""

_PLAIN_YAML = """\
# bundle.yml — 純 YAML（frontmatter ではない）
apiVersion: juice/v1
kind: mcp_bundled
name: weather-bot
"""


def test_parse_metadata_frontmatter() -> None:
    md = parse_metadata(_FRONTMATTER)
    assert md["kind"] == "tool"
    assert md["name"] == "weather"


def test_parse_metadata_plain_yaml() -> None:
    md = parse_metadata(_PLAIN_YAML)
    assert md["name"] == "weather-bot"


def test_parse_metadata_no_frontmatter_returns_empty() -> None:
    # 本文だけ（メタデータ無し）の md は空 dict。
    assert parse_metadata("# 見出しだけ\n本文のみ。\n") == {}


def test_parse_metadata_unclosed_frontmatter_returns_empty() -> None:
    assert parse_metadata("---\nname: x\n本文（閉じフェンス無し）\n") == {}


def test_extract_name() -> None:
    assert extract_name(_FRONTMATTER) == "weather"
    assert extract_name("本文のみ\n") is None


def test_verify_names_clean_registry_has_no_issues(bucket: str) -> None:
    registries = create_registries(bucket=bucket, namespace="default")
    assert verify_names(registries) == []


def _write(bucket: str, rel: str, text: str) -> None:
    target = Path(bucket) / "default" / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def test_verify_names_detects_mismatch(bucket: str) -> None:
    # ディレクトリ名 'humidity' に対し name は 'weather'（コピー流用の想定）。
    _write(bucket, "tools/humidity/index.md", "---\nkind: tool\nname: weather\n---\n")
    issues = verify_names(create_registries(bucket=bucket, namespace="default"))
    mismatches = [i for i in issues if i.dir_name == "humidity"]
    assert len(mismatches) == 1
    assert mismatches[0].reason == "mismatch"
    assert mismatches[0].declared == "weather"
    assert "一致しません" in mismatches[0].message()


def test_verify_names_detects_missing(bucket: str) -> None:
    _write(bucket, "skills/lonely/SKILL.md", "---\nkind: skill\ndescription: no name\n---\n")
    issues = verify_names(create_registries(bucket=bucket, namespace="default"))
    missing = [i for i in issues if i.dir_name == "lonely"]
    assert len(missing) == 1
    assert missing[0].reason == "missing"
    assert missing[0].declared is None
    assert "name がありません" in missing[0].message()


def test_okf_md_layers_are_md_backed() -> None:
    # OKF 対象は .md concept document のレイヤのみ（純 YAML マニフェストは対象外）。
    assert set(OKF_MD_LAYERS) == {"tool", "skill", "subagent", "workflow", "schedule"}
    assert "mcp_bundled" not in OKF_MD_LAYERS
    assert "instance" not in OKF_MD_LAYERS


def test_verify_okf_clean_registry_has_no_issues(bucket: str) -> None:
    # 最小レジストリの .md は全て type を持つ（conftest フィクスチャ）。
    registries = create_registries(bucket=bucket, namespace="default")
    assert verify_okf(registries) == []


def test_verify_okf_detects_missing_type(bucket: str) -> None:
    # type 欠落の skill を注入すると OKF 非準拠として報告される。
    _write(bucket, "skills/typeless/SKILL.md", "---\nkind: skill\nname: typeless\n---\n")
    issues = verify_okf(create_registries(bucket=bucket, namespace="default"))
    bad = [i for i in issues if i.dir_name == "typeless"]
    assert len(bad) == 1
    assert bad[0].layer == "skill"
    assert bad[0].declared_type is None
    assert "OKF" in bad[0].message()


def test_verify_okf_empty_type_is_non_conformant(bucket: str) -> None:
    # 空文字の type は非空要件を満たさない＝報告対象。
    _write(bucket, "tools/blank/index.md", "---\nname: blank\ntype: '   '\n---\n")
    issues = verify_okf(create_registries(bucket=bucket, namespace="default"))
    assert any(i.dir_name == "blank" for i in issues)


def test_verify_okf_ignores_yaml_manifests(bucket: str) -> None:
    # mcp_bundled の bundle.yml は type を持たないが OKF 対象外なので報告されない。
    issues = verify_okf(create_registries(bucket=bucket, namespace="default"))
    assert all(i.layer != "mcp_bundled" for i in issues)

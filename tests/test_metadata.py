"""メタデータ抽出と name 検証（metadata.py / E004）のテスト。"""

from __future__ import annotations

from pathlib import Path

from src.core import create_registries
from src.core.metadata import extract_name, parse_metadata, verify_names

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

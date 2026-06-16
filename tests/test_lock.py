"""juice.lock 生成（lock）のテスト。"""

from __future__ import annotations

import pytest

from src.core import build_lock, dump_lock
from src.core.lock import LOCK_VERSION, lock_manifest_text, lock_to_dict
from src.core.manifest import parse_manifest

VALID = """\
apiVersion: juice/v1
namespace: default

mcp_servers:
  - name: weather
    package: "@example/mcp-weather"
    command: npx -y @example/mcp-weather
    env: [WEATHER_API_KEY]

subagents:
  - name: forecaster
    allow_tools: [weather]

skills:
  - name: report-weather

bundles:
  - name: mcp_weather-bot
    subagent: forecaster
    skills: [report-weather]
    tools:
      - bind: weather
        from: mcp_server:weather

instances:
  - name: tokyo-weather-bot
    bundle: mcp_weather-bot
    defaults:
      city: "Tokyo"
"""


def test_build_lock_structure():
    lock = build_lock(parse_manifest(VALID))
    assert lock.lock_version == LOCK_VERSION
    assert lock.api_version == "juice/v1"
    assert lock.namespace == "default"
    assert lock.manifest_digest.startswith("sha256:")

    assert [s.name for s in lock.mcp_servers] == ["weather"]
    server = lock.mcp_servers[0]
    assert server.package == "@example/mcp-weather"

    assert len(lock.instances) == 1
    inst = lock.instances[0]
    assert inst.name == "tokyo-weather-bot"
    assert inst.bundle == "mcp_weather-bot"
    assert inst.subagent == "forecaster"
    assert inst.skills == ["report-weather"]
    assert inst.mcp_servers == ["weather"]  # tool binding の from_name から解決


def test_lock_to_dict_key_order_is_fixed():
    d = lock_to_dict(build_lock(parse_manifest(VALID)))
    assert list(d.keys()) == [
        "lockVersion",
        "apiVersion",
        "namespace",
        "manifestDigest",
        "mcp_servers",
        "instances",
    ]


def test_dump_lock_is_idempotent():
    # 同じ manifest からは毎回バイト単位で同一の lock になる（冪等）。
    a = dump_lock(lock_manifest_text(VALID))
    b = dump_lock(lock_manifest_text(VALID))
    assert a == b
    assert a.startswith("# juice.lock")


def test_digest_changes_when_manifest_changes():
    base = build_lock(parse_manifest(VALID)).manifest_digest
    changed_text = VALID.replace('city: "Tokyo"', 'city: "Osaka"')
    changed = build_lock(parse_manifest(changed_text)).manifest_digest
    assert base != changed


def test_digest_stable_across_formatting():
    # コメントや空行の違いは digest に影響しない（構造を正規化してハッシュするため）。
    a = build_lock(parse_manifest(VALID)).manifest_digest
    b = build_lock(parse_manifest("# comment\n\n" + VALID)).manifest_digest
    assert a == b


def test_dedup_servers_in_instance_closure():
    text = """\
apiVersion: juice/v1
mcp_servers:
  - name: weather
bundles:
  - name: bot
    tools:
      - bind: w1
        from: mcp_server:weather
      - bind: w2
        from: mcp_server:weather
instances:
  - name: inst
    bundle: bot
"""
    inst = build_lock(parse_manifest(text)).instances[0]
    assert inst.mcp_servers == ["weather"]  # 重複は出現順を保って 1 つに


def test_lock_records_server_version():
    text = """\
apiVersion: juice/v1
mcp_servers:
  - name: weather
    package: "@example/mcp-weather"
    version: 2.1.0
"""
    lock = build_lock(parse_manifest(text))
    assert lock.mcp_servers[0].version == "2.1.0"
    d = lock_to_dict(lock)
    assert d["mcp_servers"][0]["version"] == "2.1.0"


def test_digest_changes_with_version():
    base = """\
apiVersion: juice/v1
mcp_servers:
  - name: weather
    version: 1.0.0
"""
    bumped = base.replace("1.0.0", "1.0.1")
    assert build_lock(parse_manifest(base)).manifest_digest != (
        build_lock(parse_manifest(bumped)).manifest_digest
    )


def test_invalid_manifest_propagates():
    from src.core import ManifestError

    with pytest.raises(ManifestError):
        lock_manifest_text("apiVersion: juice/v2\n")

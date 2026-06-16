"""juice plan / apply の lock 連携（drift 検出）テスト（C005）。

facade（Juice）に tmp バケットを渡し、実レジストリを汚さずに検証する。
"""

from __future__ import annotations

import pytest

from src.core import Juice, LockError, lock_status, write_lock
from src.core.lock import build_lock
from src.core.manifest import parse_manifest

MANIFEST = """\
apiVersion: juice/v1
mcp_servers:
  - name: weather
    command: npx -y @example/mcp-weather
subagents:
  - name: forecaster
    allow_tools: [weather]
bundles:
  - name: mcp_weather-bot
    subagent: forecaster
    tools:
      - bind: weather
        from: mcp_server:weather
instances:
  - name: tokyo-weather-bot
    bundle: mcp_weather-bot
    defaults:
      city: "Tokyo"
"""


@pytest.fixture
def juice(tmp_path):
    """tmp バケットを指す Juice ファサード。"""
    return Juice(bucket=str(tmp_path / "reg"), namespace="default")


@pytest.fixture
def manifest_file(tmp_path):
    p = tmp_path / "juice.yaml"
    p.write_text(MANIFEST, encoding="utf-8")
    return p


def test_plan_does_not_write(juice, manifest_file, tmp_path):
    r = juice.plan(str(manifest_file))
    assert r["dry_run"] is True
    assert "tool/weather" in r["written"]
    # 実際には何も書かれていない。
    assert juice.list("tool") == []


def test_apply_without_lock_has_no_warning(juice, manifest_file):
    r = juice.apply(str(manifest_file), lock_path="does-not-exist.lock")
    assert "warning" not in r


def test_apply_with_matching_lock_has_no_warning(juice, manifest_file, tmp_path):
    lock = tmp_path / "juice.lock"
    write_lock(str(manifest_file), str(lock))
    r = juice.apply(str(manifest_file), lock_path=str(lock))
    assert "warning" not in r


def test_apply_warns_on_drift(juice, manifest_file, tmp_path):
    lock = tmp_path / "juice.lock"
    write_lock(str(manifest_file), str(lock))
    # manifest を変更 → lock と drift。
    manifest_file.write_text(MANIFEST.replace("Tokyo", "Osaka"), encoding="utf-8")
    r = juice.apply(str(manifest_file), lock_path=str(lock))
    assert "drift" in r["warning"]


def test_frozen_raises_on_drift(juice, manifest_file, tmp_path):
    lock = tmp_path / "juice.lock"
    write_lock(str(manifest_file), str(lock))
    manifest_file.write_text(MANIFEST.replace("Tokyo", "Osaka"), encoding="utf-8")
    with pytest.raises(LockError):
        juice.apply(str(manifest_file), lock_path=str(lock), frozen=True)


def test_require_lock_raises_when_missing(juice, manifest_file):
    with pytest.raises(LockError):
        juice.apply(str(manifest_file), lock_path="missing.lock", require_lock=True)


def test_lock_status_helper(manifest_file, tmp_path):
    manifest = parse_manifest(MANIFEST)
    # lock 不在。
    st = lock_status(manifest, str(tmp_path / "none.lock"))
    assert st == {
        "present": False,
        "drift": False,
        "expected": build_lock(manifest).manifest_digest,
        "found": None,
    }
    # 一致する lock。
    lock = tmp_path / "juice.lock"
    write_lock(str(manifest_file), str(lock))
    st2 = lock_status(manifest, str(lock))
    assert st2["present"] is True and st2["drift"] is False

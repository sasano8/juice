"""juice apply（宣言を registries へ冪等反映）のテスト。

実レジストリを汚さないよう、空の tmp バケットに対して apply する。
"""

from __future__ import annotations

import pytest

from src.core import apply_manifest, create_registries
from src.core.manifest import parse_manifest

MANIFEST = """\
apiVersion: juice/v1
namespace: default

mcp_servers:
  - name: weather
    package: "@example/mcp-weather"
    command: npx -y @example/mcp-weather
    env: [WEATHER_API_KEY]

subagents:
  - name: forecaster
    model: claude-opus-4-8
    allow_tools: [weather]
    prompt: |
      あなたは天気予報アシスタントです。

skills:
  - name: report-weather
    description: 天気を要約する

mcp_bundled:
  - name: weather-bot
    subagent: forecaster
    skills: [report-weather]
    tools:
      - bind: weather
        from: mcp_server:weather
        env: [WEATHER_API_KEY]

instances:
  - name: tokyo-weather-bot
    mcp_bundled: weather-bot
    defaults:
      city: "Tokyo"
    secrets:
      WEATHER_API_KEY: env:WEATHER_API_KEY
"""

# skill とその参照を取り除いた版（prune 検証用。参照が消えるので validate も通る）。
MANIFEST_NO_SKILL = """\
apiVersion: juice/v1
mcp_servers:
  - name: weather
    command: npx -y @example/mcp-weather
subagents:
  - name: forecaster
    allow_tools: [weather]
mcp_bundled:
  - name: weather-bot
    subagent: forecaster
    tools:
      - bind: weather
        from: mcp_server:weather
instances:
  - name: tokyo-weather-bot
    mcp_bundled: weather-bot
"""


@pytest.fixture
def regs(tmp_path):
    """空の tmp バケットを指す RegistryArray。"""
    return create_registries(bucket=str(tmp_path), namespace="default")


def test_apply_creates_all_layers(regs):
    r = apply_manifest(regs, parse_manifest(MANIFEST))
    assert set(r["written"]) == {
        "tool/weather",
        "skill/report-weather",
        "subagent/forecaster",
        "mcp_bundled/weather-bot",
        "instance/tokyo-weather-bot",
    }
    assert r["pruned"] == []
    # 各レイヤのエントリが実在する。
    assert regs.exists("tool", "weather")
    assert regs.exists("subagent", "forecaster")
    assert regs.exists("skill", "report-weather")
    assert regs.exists("mcp_bundled", "weather-bot")
    assert regs.exists("instance", "tokyo-weather-bot")


def test_apply_is_idempotent(regs):
    m = parse_manifest(MANIFEST)
    apply_manifest(regs, m)
    r2 = apply_manifest(regs, m)  # 2 回目は no-op
    assert r2["written"] == []
    assert r2["pruned"] == []


def test_apply_prunes_undeclared(regs):
    apply_manifest(regs, parse_manifest(MANIFEST))  # report-weather を作る
    r = apply_manifest(regs, parse_manifest(MANIFEST_NO_SKILL))
    assert "skill/report-weather" in r["pruned"]
    assert not regs.exists("skill", "report-weather")
    # 宣言に残るものは保持される。
    assert regs.exists("subagent", "forecaster")


def test_apply_no_prune_keeps_undeclared(regs):
    apply_manifest(regs, parse_manifest(MANIFEST))
    r = apply_manifest(regs, parse_manifest(MANIFEST_NO_SKILL), prune=False)
    assert r["pruned"] == []
    assert regs.exists("skill", "report-weather")  # prune しないので残る


def test_apply_dry_run_does_not_write(regs):
    r = apply_manifest(regs, parse_manifest(MANIFEST), dry_run=True)
    assert r["dry_run"] is True
    assert "tool/weather" in r["written"]
    assert not regs.exists("tool", "weather")  # 実際には書かれていない


def test_materialized_tool_content(regs):
    apply_manifest(regs, parse_manifest(MANIFEST))
    text = regs.read("tool", "weather")
    assert "kind: tool" in text
    assert "command: npx" in text  # command 文字列の先頭がコマンド
    assert "@example/mcp-weather" in text  # 残りは args
    assert "WEATHER_API_KEY" in text


def test_materialized_subagent_keeps_prompt(regs):
    apply_manifest(regs, parse_manifest(MANIFEST))
    text = regs.read("subagent", "forecaster")
    assert "kind: subagent" in text
    assert "あなたは天気予報アシスタントです。" in text

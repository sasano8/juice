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
    assert "type: mcp-server" in text  # OKF 必須の concept type（tool は mcp-server）
    assert "command: npx" in text  # command 文字列の先頭がコマンド
    assert "@example/mcp-weather" in text  # 残りは args
    assert "WEATHER_API_KEY" in text


def test_materialized_subagent_keeps_prompt(regs):
    apply_manifest(regs, parse_manifest(MANIFEST))
    text = regs.read("subagent", "forecaster")
    assert "kind: subagent" in text
    assert "type: subagent" in text  # OKF 必須の concept type
    assert "あなたは天気予報アシスタントです。" in text


def test_materialized_skill_has_okf_type(regs):
    apply_manifest(regs, parse_manifest(MANIFEST))
    text = regs.read("skill", "report-weather")
    assert "kind: skill" in text
    assert "type: skill" in text  # OKF 必須の concept type


# workflow（常駐サービス群）を加えた manifest。base の weather-bot bundle を協調する。
MANIFEST_WITH_WORKFLOW = (
    MANIFEST
    + """
workflows:
  - name: weather-service
    steps:
      - mcp_bundled: weather-bot
        input:
          city: "Tokyo"
"""
)


def test_apply_materializes_workflow(regs):
    r = apply_manifest(regs, parse_manifest(MANIFEST_WITH_WORKFLOW))
    assert "workflow/weather-service" in r["written"]
    assert regs.exists("workflow", "weather-service")
    text = regs.read("workflow", "weather-service")
    assert "kind: workflow" in text
    assert "type: workflow" in text  # OKF 必須の concept type
    assert "schedule:" not in text  # schedule は workflow の持ち物ではない（別概念）
    assert "mcp_bundled: weather-bot" in text
    assert "city: Tokyo" in text


def test_apply_workflow_is_idempotent(regs):
    m = parse_manifest(MANIFEST_WITH_WORKFLOW)
    apply_manifest(regs, m)
    r2 = apply_manifest(regs, m)
    assert r2["written"] == []
    assert r2["pruned"] == []


# schedule（定期実行＝ワークロード・ジョブ）を registry レイヤとして materialize する。
MANIFEST_WITH_SCHEDULE = (
    MANIFEST
    + """
schedules:
  - name: morning-brief
    schedule: "0 7 * * *"
    steps:
      - mcp_bundled: weather-bot
        input:
          city: "Tokyo"
"""
)


def test_apply_materializes_schedule(regs):
    r = apply_manifest(regs, parse_manifest(MANIFEST_WITH_SCHEDULE))
    assert "schedule/morning-brief" in r["written"]
    assert regs.exists("schedule", "morning-brief")
    text = regs.read("schedule", "morning-brief")
    assert "kind: schedule" in text
    assert "type: schedule" in text  # OKF 必須の concept type
    assert "schedule:" in text  # cron を持つ（workflow との違い）
    assert "mcp_bundled: weather-bot" in text


def test_apply_schedule_is_idempotent(regs):
    m = parse_manifest(MANIFEST_WITH_SCHEDULE)
    apply_manifest(regs, m)
    r2 = apply_manifest(regs, m)
    assert r2["written"] == []
    assert r2["pruned"] == []

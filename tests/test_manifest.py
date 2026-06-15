"""manifest（juice.yaml）パーサのテスト。"""

from __future__ import annotations

import pytest

from src.core import ManifestError, load_manifest, parse_manifest
from src.core.manifest import API_VERSION

# workspace.md の例に沿った完全な manifest。
VALID = """\
apiVersion: juice/v1
namespace: default

mcp_servers:
  - name: weather
    package: "@example/mcp-weather"
    command: npx -y @example/mcp-weather
    env: [WEATHER_API_KEY]
    tools: [get_forecast]

subagents:
  - name: forecaster
    model: claude-opus-4-8
    allow_tools: [weather]
    prompt: |
      あなたは天気予報アシスタントです。

skills:
  - name: report-weather
    description: 都市の天気を取得し一言で要約する

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


def test_parse_valid_full_manifest():
    m = parse_manifest(VALID)
    assert m.api_version == API_VERSION
    assert m.namespace == "default"

    assert m.names("mcp_servers") == ["weather"]
    server = m.mcp_servers[0]
    assert server.package == "@example/mcp-weather"
    assert server.env == ["WEATHER_API_KEY"]
    assert server.tools == ["get_forecast"]

    sa = m.subagents[0]
    assert sa.model == "claude-opus-4-8"
    assert sa.allow_tools == ["weather"]
    assert sa.prompt.strip().startswith("あなたは")

    bundle = m.mcp_bundled[0]
    assert bundle.subagent == "forecaster"
    assert bundle.skills == ["report-weather"]
    assert len(bundle.tools) == 1
    binding = bundle.tools[0]
    assert binding.bind == "weather"
    assert binding.from_kind == "mcp_server"
    assert binding.from_name == "weather"
    assert binding.env == ["WEATHER_API_KEY"]

    inst = m.instances[0]
    assert inst.mcp_bundled == "weather-bot"
    assert inst.defaults == {"city": "Tokyo"}
    assert inst.secrets == {"WEATHER_API_KEY": "env:WEATHER_API_KEY"}


def test_namespace_defaults_to_default():
    m = parse_manifest("apiVersion: juice/v1\n")
    assert m.namespace == "default"
    assert m.names("mcp_servers") == []


def test_empty_manifest_errors():
    with pytest.raises(ManifestError, match="空です"):
        parse_manifest("")


def test_non_mapping_root_errors():
    with pytest.raises(ManifestError, match="マッピング"):
        parse_manifest("- a\n- b\n")


def test_missing_api_version_errors():
    with pytest.raises(ManifestError, match="apiVersion が必要"):
        parse_manifest("namespace: default\n")


def test_unsupported_api_version_errors():
    with pytest.raises(ManifestError, match="未対応の apiVersion"):
        parse_manifest("apiVersion: juice/v2\n")


def test_layer_must_be_list():
    with pytest.raises(ManifestError, match="リストである必要"):
        parse_manifest("apiVersion: juice/v1\nmcp_servers:\n  name: x\n")


def test_item_requires_name():
    with pytest.raises(ManifestError, match="name（文字列）が必要"):
        parse_manifest("apiVersion: juice/v1\nskills:\n  - description: no name\n")


def test_duplicate_name_errors():
    text = """\
apiVersion: juice/v1
skills:
  - name: dup
  - name: dup
"""
    with pytest.raises(ManifestError, match="重複した name"):
        parse_manifest(text)


def test_subagent_allow_tools_unknown_reference():
    text = """\
apiVersion: juice/v1
subagents:
  - name: forecaster
    allow_tools: [ghost]
"""
    with pytest.raises(ManifestError, match="未定義の mcp_server"):
        parse_manifest(text)


def test_bundled_unknown_subagent_reference():
    text = """\
apiVersion: juice/v1
mcp_bundled:
  - name: bot
    subagent: ghost
"""
    with pytest.raises(ManifestError, match="未定義の subagent"):
        parse_manifest(text)


def test_bundled_unknown_skill_reference():
    text = """\
apiVersion: juice/v1
mcp_bundled:
  - name: bot
    skills: [ghost]
"""
    with pytest.raises(ManifestError, match="未定義の skill"):
        parse_manifest(text)


def test_bundled_tool_unknown_server_reference():
    text = """\
apiVersion: juice/v1
mcp_bundled:
  - name: bot
    tools:
      - bind: w
        from: mcp_server:ghost
"""
    with pytest.raises(ManifestError, match="未定義の mcp_server"):
        parse_manifest(text)


def test_tool_binding_requires_bind():
    text = """\
apiVersion: juice/v1
mcp_bundled:
  - name: bot
    tools:
      - from: mcp_server:weather
"""
    with pytest.raises(ManifestError, match="bind"):
        parse_manifest(text)


def test_tool_binding_from_format():
    text = """\
apiVersion: juice/v1
mcp_bundled:
  - name: bot
    tools:
      - bind: w
        from: weather
"""
    with pytest.raises(ManifestError, match="<kind>:<name>"):
        parse_manifest(text)


def test_tool_binding_unsupported_kind():
    text = """\
apiVersion: juice/v1
mcp_bundled:
  - name: bot
    tools:
      - bind: w
        from: skill:weather
"""
    with pytest.raises(ManifestError, match="未対応"):
        parse_manifest(text)


def test_instance_requires_mcp_bundled():
    text = """\
apiVersion: juice/v1
instances:
  - name: inst
"""
    with pytest.raises(ManifestError, match="mcp_bundled（文字列）が必要"):
        parse_manifest(text)


def test_instance_unknown_bundled_reference():
    text = """\
apiVersion: juice/v1
instances:
  - name: inst
    mcp_bundled: ghost
"""
    with pytest.raises(ManifestError, match="未定義の mcp_bundled"):
        parse_manifest(text)


def test_version_field_is_parsed():
    text = """\
apiVersion: juice/v1
mcp_servers:
  - name: weather
    version: 1.2.3
skills:
  - name: report-weather
    version: 0.1.0-rc.1
"""
    m = parse_manifest(text)
    assert m.mcp_servers[0].version == "1.2.3"
    assert m.skills[0].version == "0.1.0-rc.1"


def test_invalid_version_errors():
    text = """\
apiVersion: juice/v1
mcp_servers:
  - name: weather
    version: 1.2
"""
    with pytest.raises(ManifestError, match="version が不正"):
        parse_manifest(text)


def _bundle_with_from(from_ref: str, server_version: str | None = None) -> str:
    ver = f"\n    version: {server_version}" if server_version else ""
    return f"""\
apiVersion: juice/v1
mcp_servers:
  - name: weather{ver}
mcp_bundled:
  - name: bot
    tools:
      - bind: w
        from: {from_ref}
"""


def test_constraint_satisfied():
    m = parse_manifest(_bundle_with_from("mcp_server:weather@>=1.0.0", "1.2.0"))
    binding = m.mcp_bundled[0].tools[0]
    assert binding.from_name == "weather"
    assert binding.constraint == ">=1.0.0"


def test_constraint_without_at_is_backward_compatible():
    m = parse_manifest(_bundle_with_from("mcp_server:weather"))
    binding = m.mcp_bundled[0].tools[0]
    assert binding.from_name == "weather"
    assert binding.constraint is None


def test_constraint_unsatisfied_errors():
    with pytest.raises(ManifestError, match="満たしません"):
        parse_manifest(_bundle_with_from("mcp_server:weather@>=2.0.0", "1.2.0"))


def test_constraint_without_declared_version_errors():
    with pytest.raises(ManifestError, match="version が宣言されていません"):
        parse_manifest(_bundle_with_from("mcp_server:weather@>=1.0.0"))


def test_constraint_empty_errors():
    with pytest.raises(ManifestError, match="version 制約がありません"):
        parse_manifest(_bundle_with_from("mcp_server:weather@", "1.0.0"))


def test_constraint_invalid_errors():
    with pytest.raises(ManifestError, match="制約が不正"):
        parse_manifest(_bundle_with_from("mcp_server:weather@>=bad", "1.0.0"))


def test_load_manifest_from_file(tmp_path):
    p = tmp_path / "juice.yaml"
    p.write_text(VALID, encoding="utf-8")
    m = load_manifest(p)
    assert m.names("instances") == ["tokyo-weather-bot"]


def test_load_manifest_missing_file(tmp_path):
    with pytest.raises(ManifestError, match="見つかりません"):
        load_manifest(tmp_path / "nope.yaml")


# --- workflow（E001 第一歩） ---------------------------------------------------

_WORKFLOW = """\
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
workflows:
  - name: morning-brief
    schedule: "0 7 * * *"
    steps:
      - mcp_bundled: weather-bot
        input:
          city: "Tokyo"
"""


def test_parse_workflow():
    m = parse_manifest(_WORKFLOW)
    assert m.names("workflows") == ["morning-brief"]
    wf = m.workflows[0]
    assert wf.schedule == "0 7 * * *"
    assert len(wf.steps) == 1
    assert wf.steps[0].mcp_bundled == "weather-bot"
    assert wf.steps[0].input == {"city": "Tokyo"}


def test_workflow_step_requires_mcp_bundled():
    text = "apiVersion: juice/v1\nworkflows:\n  - name: w\n    steps:\n      - input: {a: 1}\n"
    with pytest.raises(ManifestError, match="mcp_bundled（文字列）が必要"):
        parse_manifest(text)


def test_workflow_unknown_bundle_reference():
    text = "apiVersion: juice/v1\nworkflows:\n  - name: w\n    steps:\n      - mcp_bundled: ghost\n"
    with pytest.raises(ManifestError, match="未定義の mcp_bundled"):
        parse_manifest(text)


def test_workflow_step_input_must_be_mapping():
    text = (
        "apiVersion: juice/v1\nmcp_bundled:\n  - name: weather-bot\n"
        "workflows:\n  - name: w\n    steps:\n"
        "      - mcp_bundled: weather-bot\n        input: not-a-map\n"
    )
    with pytest.raises(ManifestError, match="input はマッピング"):
        parse_manifest(text)


def test_workflow_duplicate_name_errors():
    text = (
        "apiVersion: juice/v1\nworkflows:\n  - name: w\n    steps: []\n  - name: w\n    steps: []\n"
    )
    with pytest.raises(ManifestError, match="重複した name"):
        parse_manifest(text)

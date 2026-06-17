"""bundle モジュール（init / bundle / build / run）のテスト。"""

from __future__ import annotations

import json

import pytest

from src.core import Juice
from src.core import bundle as _bundle


def test_parse_frontmatter_splits_yaml_and_body() -> None:
    text = "---\nkind: tool\nname: x\n---\n\n本文です。\n"
    meta, body = _bundle.parse_frontmatter(text)
    assert meta == {"kind": "tool", "name": "x"}
    assert body.startswith("本文です。")


def test_parse_frontmatter_without_fence_is_all_body() -> None:
    meta, body = _bundle.parse_frontmatter("fence なし本文")
    assert meta == {}
    assert body == "fence なし本文"


def test_init_creates_template(juice: Juice) -> None:
    result = juice.init("new-bot")
    assert result["kind"] == "init"
    assert result["bundle"] == "new-bot"
    # 生成された雛形に name/namespace が埋まる
    spec = juice.registries.read("bundle", "new-bot")
    assert "name: new-bot" in spec
    assert "namespace: default" in spec


def test_init_existing_without_clean_raises(juice: Juice) -> None:
    with pytest.raises(FileExistsError):
        juice.init("mcp_weather-bot")


def test_init_clean_preserves_spec_and_clears_vendor(juice: Juice) -> None:
    # 先に bundle で vendor/ を作る
    juice.bundle("mcp_weather-bot")
    assert juice.registries.exists("bundle", "mcp_weather-bot", "vendor/graph.py")
    before = juice.registries.read("bundle", "mcp_weather-bot")
    # clean は既存 spec を残して生成物を一掃する
    juice.init("mcp_weather-bot", clean=True)
    assert juice.registries.read("bundle", "mcp_weather-bot") == before
    assert not juice.registries.exists("bundle", "mcp_weather-bot", "vendor/graph.py")


def test_bundle_vendors_deps_and_generates_files(juice: Juice) -> None:
    result = juice.bundle("mcp_weather-bot")
    assert result["kind"] == "bundle"
    # 依存（subagent/skill/tool）がパッケージ丸ごと vendoring される
    vendored = result["vendored"]
    assert any("vendor/tools/weather/server.py" in v for v in vendored)
    assert any("vendor/subagents/forecaster/index.md" in v for v in vendored)
    assert any("vendor/skills/report-weather/SKILL.md" in v for v in vendored)
    # build コンテキスト一式が生成される
    generated = {g.rsplit("/", 1)[-1] for g in result["generated"]}
    assert {"requirements.txt", "graph.py", "api.py", "Dockerfile", "agent.json"} <= generated


def test_bundle_agent_json_resolves_config(juice: Juice) -> None:
    juice.bundle("mcp_weather-bot")
    raw = juice.registries.read("bundle", "mcp_weather-bot", "vendor/agent.json")
    agent_json = json.loads(raw)
    assert agent_json["name"] == "mcp_weather-bot"
    assert agent_json["model"] == "claude-opus-4-8"
    # subagent 本文が system prompt に入る
    assert "天気予報アシスタント" in agent_json["system"]
    # tool の MCP server 起動定義が解決され、.py が vendor 相対へ prefix される
    weather = agent_json["mcp_servers"]["weather"]
    assert weather["command"] == "python"
    assert weather["args"] == ["tools/weather/server.py"]
    assert weather["transport"] == "stdio"


_REMOTE_TOOL = """\
---
kind: tool
name: ext
type: mcp-server
transport: sse
url: https://mcp.example.com/sse
env:
  API_TOKEN: ${API_TOKEN}
---

# ext
"""

_REMOTE_BUNDLE = """\
apiVersion: juice/v1
kind: bundle
name: remote-bot
namespace: default
image: juice/remote-bot
version: 0.0.1
tools:
  ext:
    env:
      API_TOKEN: ${API_TOKEN}
include:
  - tools
"""


def test_remote_tool_connection_and_not_vendored(juice: Juice) -> None:
    # remote tool（url 参照）は url 接続定義になり、vendoring されない（E002）。
    juice.registries.write("tool", "ext", "index.md", _REMOTE_TOOL)
    juice.registries.write("bundle", "remote-bot", "bundle.yml", _REMOTE_BUNDLE)
    result = juice.bundle("remote-bot")
    # remote tool は黒箱なので vendor/ に入らない
    assert not any("vendor/tools/ext" in v for v in result["vendored"])
    # agent.json の接続定義は transport/url（command/args を持たない）
    agent_json = json.loads(juice.registries.read("bundle", "remote-bot", "vendor/agent.json"))
    ext = agent_json["mcp_servers"]["ext"]
    assert ext == {"transport": "sse", "url": "https://mcp.example.com/sse"}
    assert "command" not in ext


def test_build_command(juice: Juice, bucket: str) -> None:
    result = juice.build("mcp_weather-bot")
    assert result["image"] == "juice/mcp_weather-bot:latest"
    assert result["version"] == "0.0.1"
    expected_ctx = f"{bucket}/namespaces/default/bundles/mcp_weather-bot/vendor"
    assert result["context"] == expected_ctx
    assert result["command"] == f"docker build -t juice/mcp_weather-bot:latest {expected_ctx}"


def test_build_custom_image_tag(juice: Juice) -> None:
    result = juice.build("mcp_weather-bot", image="myreg/foo:1.2.3")
    assert result["image"] == "myreg/foo:1.2.3"
    assert result["command"].startswith("docker build -t myreg/foo:1.2.3 ")


@pytest.mark.parametrize(
    ("mode", "fragment"),
    [
        ("api", "-p 8000:8000"),
        ("ui", "-p 8000:8000"),
        ("mcp_server", "-i"),
    ],
)
def test_run_command_per_mode(juice: Juice, mode: str, fragment: str) -> None:
    result = juice.run("mcp_weather-bot", mode=mode)
    assert result["mode"] == mode
    assert fragment in result["command"]
    assert result["command"].endswith(f"juice/mcp_weather-bot:latest {mode}")
    assert "-e ANTHROPIC_API_KEY" in result["command"]


def test_run_unknown_mode_raises(juice: Juice) -> None:
    with pytest.raises(ValueError, match="unknown mode"):
        juice.run("mcp_weather-bot", mode="nope")


def test_run_with_env_file(juice: Juice) -> None:
    result = juice.run("mcp_weather-bot", mode="api", env_file=".env.test")
    assert "--env-file .env.test" in result["command"]

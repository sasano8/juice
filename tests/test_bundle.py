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
    assert result["mcp_bundled"] == "new-bot"
    # 生成された雛形に name/namespace が埋まる
    spec = juice.registries.read("mcp_bundled", "new-bot")
    assert "name: new-bot" in spec
    assert "namespace: default" in spec


def test_init_existing_without_clean_raises(juice: Juice) -> None:
    with pytest.raises(FileExistsError):
        juice.init("weather-bot")


def test_init_clean_preserves_spec_and_clears_vendor(juice: Juice) -> None:
    # 先に bundle で vendor/ を作る
    juice.bundle("weather-bot")
    assert juice.registries.exists("mcp_bundled", "weather-bot", "vendor/graph.py")
    before = juice.registries.read("mcp_bundled", "weather-bot")
    # clean は既存 spec を残して生成物を一掃する
    juice.init("weather-bot", clean=True)
    assert juice.registries.read("mcp_bundled", "weather-bot") == before
    assert not juice.registries.exists("mcp_bundled", "weather-bot", "vendor/graph.py")


def test_bundle_vendors_deps_and_generates_files(juice: Juice) -> None:
    result = juice.bundle("weather-bot")
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
    juice.bundle("weather-bot")
    raw = juice.registries.read("mcp_bundled", "weather-bot", "vendor/agent.json")
    agent_json = json.loads(raw)
    assert agent_json["name"] == "weather-bot"
    assert agent_json["model"] == "claude-opus-4-8"
    # subagent 本文が system prompt に入る
    assert "天気予報アシスタント" in agent_json["system"]
    # tool の MCP server 起動定義が解決され、.py が vendor 相対へ prefix される
    weather = agent_json["mcp_servers"]["weather"]
    assert weather["command"] == "python"
    assert weather["args"] == ["tools/weather/server.py"]
    assert weather["transport"] == "stdio"


def test_build_command(juice: Juice, bucket: str) -> None:
    result = juice.build("weather-bot")
    assert result["image"] == "juice/weather-bot:latest"
    assert result["version"] == "0.0.1"
    expected_ctx = f"{bucket}/default/mcp_bundled/weather-bot/vendor"
    assert result["context"] == expected_ctx
    assert result["command"] == f"docker build -t juice/weather-bot:latest {expected_ctx}"


def test_build_custom_image_tag(juice: Juice) -> None:
    result = juice.build("weather-bot", image="myreg/foo:1.2.3")
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
    result = juice.run("weather-bot", mode=mode)
    assert result["mode"] == mode
    assert fragment in result["command"]
    assert result["command"].endswith(f"juice/weather-bot:latest {mode}")
    assert "-e ANTHROPIC_API_KEY" in result["command"]


def test_run_unknown_mode_raises(juice: Juice) -> None:
    with pytest.raises(ValueError, match="unknown mode"):
        juice.run("weather-bot", mode="nope")


def test_run_with_env_file(juice: Juice) -> None:
    result = juice.run("weather-bot", mode="api", env_file=".env.test")
    assert "--env-file .env.test" in result["command"]

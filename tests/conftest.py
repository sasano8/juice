"""テスト共通フィクスチャ。

実レジストリを汚さないよう、tmp_path 上に最小構成のレジストリを組み立てて
そこを指す RegistryArray / Juice を提供する。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core import Juice, create_registries

# 最小レジストリのファイル群（パス -> 内容）。実 registries/default を模した構成。
_TOOL_INDEX = """\
---
kind: tool
name: weather
type: mcp-server
command: python
args: [server.py]
---

# weather

天気を取得する MCP server。
"""

_TOOL_SERVER = "# mock mcp server\nprint('weather server')\n"

_SUBAGENT_INDEX = """\
---
kind: subagent
name: forecaster
description: 天気予報アシスタント
model: claude-sonnet-4-6
tools: [weather]
---

あなたは天気予報アシスタントです。
"""

_SKILL = """\
---
kind: skill
name: report-weather
description: 天気を要約して伝える
---

# report-weather
"""

_BUNDLE_YML = """\
apiVersion: juice/v1
kind: mcp_bundled
name: weather-bot
namespace: default
image: juice/weather-bot
version: 0.0.1
llm:
  provider: anthropic
  model: claude-opus-4-8
  api_key_env: ANTHROPIC_API_KEY
subagent: forecaster
skills:
  - report-weather
tools:
  weather:
    env:
      WEATHER_API_KEY: ${WEATHER_API_KEY}
include:
  - subagent
  - skills
  - tools
"""

_LAYOUT = {
    "tools/weather/index.md": _TOOL_INDEX,
    "tools/weather/server.py": _TOOL_SERVER,
    "subagents/forecaster/index.md": _SUBAGENT_INDEX,
    "skills/report-weather/SKILL.md": _SKILL,
    "mcp_bundled/weather-bot/bundle.yml": _BUNDLE_YML,
}


@pytest.fixture
def bucket(tmp_path: Path) -> str:
    """default namespace に最小構成を書き出した bucket パスを返す。"""
    ns = tmp_path / "default"
    for rel, content in _LAYOUT.items():
        target = ns / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return str(tmp_path)


@pytest.fixture
def registries(bucket: str):
    return create_registries(bucket=bucket, namespace="default")


@pytest.fixture
def juice(bucket: str) -> Juice:
    return Juice(bucket=bucket, namespace="default")

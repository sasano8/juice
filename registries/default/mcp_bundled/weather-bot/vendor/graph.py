"""LangGraph グラフ（自動生成）。

bundled MCP server を langchain-mcp-adapters で取り込み、Claude（langchain-anthropic）と
create_react_agent で結ぶ。langgraph.json はこの make_graph を参照する（Studio / dev / API 共通）。
"""

from __future__ import annotations

import json
import os
import pathlib

from langchain_anthropic import ChatAnthropic
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent

HERE = pathlib.Path(__file__).parent
CONFIG = json.loads((HERE / "agent.json").read_text(encoding="utf-8"))


def resolve_api_key() -> str | None:
    """api_key_file / api_key_env から API キーを解決して返す（無ければ None）。"""
    path = CONFIG.get("api_key_file")
    if path and os.path.exists(path):
        return pathlib.Path(path).read_text(encoding="utf-8").strip()
    env = CONFIG.get("api_key_env") or "ANTHROPIC_API_KEY"
    return os.environ.get(env)


def _ensure_api_key() -> None:
    """解決したキーを ANTHROPIC_API_KEY に設定する（ChatAnthropic が読む）。"""
    key = resolve_api_key()
    if key:
        os.environ["ANTHROPIC_API_KEY"] = key


def _connections() -> dict:
    conns = {}
    for name, c in CONFIG.get("mcp_servers", {}).items():
        args = [str(HERE / a) if isinstance(a, str) and a.endswith(".py") else a for a in c.get("args", [])]
        conns[name] = {"transport": c.get("transport", "stdio"), "command": c["command"], "args": args}
    return conns


async def make_graph():
    """MCP tool を取り込んだ ReAct エージェントグラフを返す（langgraph.json のエントリ）。"""
    _ensure_api_key()
    client = MultiServerMCPClient(_connections())
    tools = await client.get_tools()
    model = ChatAnthropic(model=CONFIG["model"])
    return create_react_agent(model, tools, prompt=CONFIG.get("system") or None)

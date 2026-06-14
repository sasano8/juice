"""モック MCP server（自動生成・FastMCP）。

get_forecast(city) を MCP の tool として stdio で公開する。実 server に差し替えるまでの
tool バックエンド。langchain-mcp-adapters はこれを stdio で起動して tool を取り込む。
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("mock-weather")


@mcp.tool()
def get_forecast(city: str) -> str:
    """指定都市の天気予報を返す（モック）。"""
    return f"{city}: 晴れ 80C（モック予報）"


if __name__ == "__main__":
    mcp.run()  # stdio transport

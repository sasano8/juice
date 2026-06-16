"""weather ツールの MCP server（モック・FastMCP）。

`get_forecast(city)` を MCP の tool として stdio で公開する。実 server に差し替えるまでの
ツール実体。bundle 時に vendor/tools/weather/ 配下へコピーされ、agent.json から起動される。
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("weather")


@mcp.tool()
def get_forecast(city: str) -> str:
    """指定都市の天気予報を返す（モック）。"""
    return f"{city}: 晴れ 80C（モック予報）"


if __name__ == "__main__":
    mcp.run()  # stdio transport

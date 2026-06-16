---
kind: tool
name: weather
type: mcp-server
description: 天気を取得する MCP server（同梱モック）
tags: [weather, mock]
# このパッケージ同梱の MCP server を起動する（args の .py は bundle 時に
# vendor/tools/weather/ 配下へ解決される）。実 server に差し替える時はここを変える。
command: python
args: [server.py]
env:
  WEATHER_API_KEY: ${WEATHER_API_KEY}
---

# weather

天気を取得する MCP server（同梱モック `server.py` / `get_forecast(city)`）。

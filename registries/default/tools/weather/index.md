---
kind: tool
name: weather
type: mcp-server
command: npx
args: ["-y", "@example/mcp-weather"]
env:
  WEATHER_API_KEY: ${WEATHER_API_KEY}
---

# weather

天気を取得する MCP server。`get_forecast(city)` を提供する。

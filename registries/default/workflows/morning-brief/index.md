---
kind: workflow
name: morning-brief
type: workflow
schedule: "0 7 * * *"
steps:
  - mcp_bundled: weather-bot
    input: { city: "Tokyo" }
---

# morning-brief

毎朝 7 時に `weather-bot` を起動し、東京の天気を要約させる。

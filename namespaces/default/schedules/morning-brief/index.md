---
kind: schedule
name: morning-brief
type: schedule
schedule: "0 7 * * *"
steps:
  - mcp_bundled: weather-bot
    input: { city: "Tokyo" }
---

# morning-brief

毎朝 7 時に `weather-bot` を定期実行し、東京の天気を要約させる schedule（定期実行のトリガ）。
`juice schedule build morning-brief --target k8s` で CronJob を生成できる。

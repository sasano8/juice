---
kind: workflow
name: weather-service
type: workflow
steps:
  - bundle: mcp_weather-bot
    input: { city: "Tokyo" }
---

# weather-service

`mcp_weather-bot` を常駐サービスとして動かす workflow（時間非依存の定義）。
定期実行したい場合は別概念 `schedules:`（cron を持つトリガ）で参照する。

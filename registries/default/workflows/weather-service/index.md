---
kind: workflow
name: weather-service
type: workflow
steps:
  - mcp_bundled: weather-bot
    input: { city: "Tokyo" }
---

# weather-service

`weather-bot` を常駐サービスとして動かす workflow（時間非依存の定義）。
定期実行したい場合は別概念 `schedules:`（cron を持つトリガ）で参照する。

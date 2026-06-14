---
kind: actor
name: weather-bot
subagent: forecaster
skills: [report-weather]
tools:
  weather:
    env:
      WEATHER_API_KEY: ${WEATHER_API_KEY}
---

# weather-bot

`forecaster` に `report-weather` を結線し、`weather` ツールを secret 注入で具象化した実行可能エージェント。

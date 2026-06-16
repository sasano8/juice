---
kind: workflow
name: langfuse
type: workflow
vendored: compose
---

# langfuse

LLM 可観測性スタック（[langfuse](https://langfuse.com) v3）の **vendored workflow**。

juice bundle を steps で組む生成型 workflow とは違い、**外部スタックの `docker-compose.yml` を
そのまま同梱する終端ノード**。依存物（juice の bundle）を持たないので dependency closure は空。
`juice workflow build langfuse` は steps から生成せず、同梱 compose を `deploy/langfuse/` へ
そのまま passthrough する（`docker compose up` でそのまま起動できる）。

- 実体: 同ディレクトリの `docker-compose.yml`（web/worker + postgres + clickhouse + redis + minio）。
  langfuse 公式 v3 構成を distill したもので、シークレットは開発用の固定値。**本番は公式 compose を正**:
  <https://github.com/langfuse/langfuse/blob/main/docker-compose.yml>。
- `mcp_weather-bot` とは別スタック。アプリ側のトレースを送るなら bundle に langfuse SDK を足し
  `LANGFUSE_*`（host `http://localhost:3000`／public・secret key）を env 参照で注入する。

# build：bundle.yml から会話エージェントを起動するまで

juice の実用ガイド。`bundle.yml`（mcp_bundled の定義）から **init → bundle → build → run** で
**LangGraph 製の会話エージェント**（Claude × MCP server）を docker 起動するまでを説明する。
概念は [architecture.md](architecture.md)、全体像は [README](../README.md) を参照。

## パイプライン

```
bundle.yml ──init──▶ 雛形生成 ──bundle──▶ vendor/（依存同梱＋LangGraph一式）──build──▶ dockerイメージ ──run──▶ 起動(api/ui/mcp_server)
```

| 段階 | 何をする |
|------|----------|
| `init`   | `bundle.yml` の雛形を生成（`--clean` で定義を残してディレクトリ一掃） |
| `bundle` | 内包物（subagent/skill/tool）を `vendor/` へ丸ごとコピー＋ LangGraph 一式と `agent.json` を生成 |
| `build`  | `vendor/` を docker build context にしてイメージをビルド |
| `run`    | mode（api / ui / mcp_server）でコンテナ起動 |

## bundle.yml（mcp_bundled の定義）

`registries/<namespace>/mcp_bundled/<name>/bundle.yml` が単一のソース（instance の index.yml に相当）。

```yaml
apiVersion: juice/v1
kind: mcp_bundled
name: weather-bot
namespace: default

image: juice/weather-bot     # build するイメージ名（タグなし）
version: 0.0.1

# 会話に使う LLM。API キーは環境変数 or ファイルで注入（値は書かない）
llm:
  provider: anthropic
  model: claude-opus-4-8
  api_key_env: ANTHROPIC_API_KEY
  # api_key_file: /run/secrets/anthropic_api_key

# 結線（定義）
subagent: forecaster          # 脳（system プロンプト＝subagent 本文）
skills: [report-weather]      # 手順
tools:                        # 使う tool（= MCP server）
  weather:
    env: { WEATHER_API_KEY: ${WEATHER_API_KEY} }

include: [subagent, skills, tools]   # vendoring 対象（省略時はこの 3 つ）
```

## コマンド

```bash
# 初期化（bundle.yml 雛形）。既存があれば --clean が必要
juice mcp_bundled init weather-bot [-n default] [--clean]

# vendoring ＋ LangGraph 一式生成（vendor/ を作る）
juice mcp_bundled bundle weather-bot [-n default]

# docker イメージビルド（実行する）
juice mcp_bundled build weather-bot [-n default] [-t juice/weather-bot:latest]

# 起動。mode = api / ui / mcp_server（既定 api）
juice mcp_bundled run weather-bot [api|ui|mcp_server] \
  [-n default] [-t TAG] [--build] [--bundle] [--env-file .env.agent]
```

`run` のフラグ:
- `--build` … run 前に build も実行（build→run）。
- `--bundle` … run 前に bundle からやり直す（bundle→build→run）。
- `--env-file` / `--env PATH` … docker の `--env-file` で .env を読む（無ければスキップ）。
- `-t/--tag` … イメージタグ上書き。`-n/--namespace` … namespace。

## run モード

| mode | 起動 | エンドポイント |
|------|------|----------------|
| `api` | `uvicorn api:app` | `/chat`（簡易チャットUI）・`/v1/chat/completions`（OpenAI互換）・`/docs` |
| `ui`  | `langgraph dev`（Studio）＋ api 相乗り | `/chat`（同上）＋ Studio（`https://smith.langchain.com/studio/?baseUrl=http://localhost:8000`） |
| `mcp_server` | tool の MCP server を stdio 起動 | stdio（JSON-RPC） |

どのモードでも `http://localhost:8000/chat` でチャットできる（`langgraph.json` の `http.app` で
ui モードにも `api.py` を相乗りさせている）。

## 生成物（vendor/）と agent.json

`bundle` は `vendor/` に docker build context 一式を出力する（生成物なので `.gitignore` 済み）:

```
vendor/
  subagents/forecaster/index.md     # vendoring（パッケージ丸ごと）
  skills/report-weather/SKILL.md
  tools/weather/index.md
  tools/weather/server.py           # tool の MCP server 実体もここから同梱
  agent.json        # 解決済み設定（model/system/api_key/mcp_servers）。graph.py が読む
  graph.py          # MCP tool 取込＋ChatAnthropic＋create_react_agent → make_graph
  api.py            # FastAPI: /chat, /v1/chat/completions
  entrypoint.py     # mode 分岐（api/ui/mcp_server）
  langgraph.json    # graphs: graph.py:make_graph, http.app: api.py:app
  requirements.txt  # langgraph / langchain-anthropic / langchain-mcp-adapters / mcp / fastapi …
  Dockerfile
  .env
```

`agent.json` は **juice が生成する派生物**（手編集しても再 bundle で上書き）。由来:

| agent.json | ソース |
|------------|--------|
| `model` / `provider` / `api_key_*` | bundle.yml の `llm`（無ければ subagent の `model`） |
| `system` | subagent（`subagents/<name>/index.md`）の本文 |
| `mcp_servers` | 各 tool（`tools/<name>/index.md`）の `command`/`args` |

読むのは juice の `graph.py`（→ LangChain/LangGraph オブジェクトに変換）。LangChain が直接読むわけではない。

## tool の MCP server はどこから来るか

tool パッケージ `tools/<name>/` が **定義(index.md) と実体(server.py) を同梱**する。`index.md` の
`command`/`args` が起動方法（`.py` 引数は `vendor/tools/<name>/` 配下へ解決）。`bundle` がパッケージを
丸ごと vendoring し、`agent.json.mcp_servers` がそれを指す。実 server へ差し替えるときは
`tools/<name>/index.md` の `command/args`（と server 実体）を変えるだけ。

## LLM と API キー注入

- LLM は `bundle.yml` の `llm`（既定 Claude `claude-opus-4-8`）。
- キーは **環境変数 or ファイル**で注入し、bundle.yml に値は書かない:
  - `api_key_env`（既定 `ANTHROPIC_API_KEY`）or `api_key_file`。
  - docker へは `run --env .env.agent`（`--env-file`）か `-e ANTHROPIC_API_KEY` で渡る。
- 未設定時は `/v1/chat/completions` が 400 JSON（`missing_api_key`）を返し、UI に「API キー未設定」と表示。

## Makefile ショートカット

```bash
make juice-run-ui          # bundle→build→ui（Studio + /chat）。--env .env.agent 込み
make juice-run-api         # 同 api
make juice-run-mcp_server  # 同 mcp_server
make juice-all             # registry 全パッケージ一覧
```

## registry レイアウト

```
registries/<namespace>/
  tools/<name>/index.md        # + server.py 等（MCP server 単位）
  skills/<name>/SKILL.md
  subagents/<name>/index.md
  mcp_bundled/<name>/bundle.yml # + vendor/（生成物）
```

`<layer> list` / `all list` で一覧:
```bash
juice mcp_bundled list
juice all list
```

## 宣言系コマンド（juice.yaml ライフサイクル）

`bundle.yml`（mcp_bundled 単位）とは別に、`juice.yaml`（宣言的ワークスペース manifest）から
レジストリを組み立てる宣言系コマンドがある（設計は [workspace.md](workspace.md)）。典型フロー:

```bash
juice manifest validate -f juice.yaml    # 構文・参照・version 制約を検証
juice lock -f juice.yaml -o juice.lock   # 解決して juice.lock を冪等生成
juice plan -f juice.yaml                 # 反映の差分を確認（書き込まない）
juice apply -f juice.yaml                # registries/ へ反映（lock と drift 検査）
```

- **validate** … name の必須/重複・レイヤ間参照・`version`（SemVer）・`from: name@<制約>` を検査。
- **lock** … manifest の解決結果＋`manifestDigest` を冪等に pin（外部 digest は未実装の TODO）。
- **plan** … `apply --dry-run` 相当。`written`/`pruned` の差分のみ表示。
- **apply** … 依存順に materialize し、宣言にない既存パッケージは prune（冪等）。
  `--no-prune` / `--dry-run` / `--frozen`（drift でエラー）/ `--require-lock`（lock 必須）。

各コマンドの例は `juice <cmd> -h`、全体像は `juice -h` で確認できる。

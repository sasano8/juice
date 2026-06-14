# juice タスク
# JUICE はインストール済みなら `juice` に上書き可:  make juice-all JUICE=juice
JUICE ?= uv run python -m src
BUNDLE_NAME ?= weather-bot
# api | mcp_server | ui
RUN_MODE ?= api
# docker --env-file で読み込む .env（無ければ自動スキップ）
ENV_FILE ?= .env.agent

.PHONY: juice-all
## 全レイヤを依存順（instance→tool）に一覧表示する
juice-all:
	@$(JUICE) all list

.PHONY: juice-init
## 成果物名（BUNDLE_NAME）の bundle.yml 雛形を生成して初期化する（テスト用）
juice-init:
	@$(JUICE) mcp_bundled init $(BUNDLE_NAME) --clean

.PHONY: juice-bundle
## 内包物を vendoring し build コンテキスト（requirements/Dockerfile/entrypoint）を生成する（テスト用）
juice-bundle:
	@$(JUICE) mcp_bundled bundle $(BUNDLE_NAME)

.PHONY: juice-build
## docker build コマンドを生成・表示する（テスト用。実行は JUICE ... build --run）
juice-build:
	@$(JUICE) mcp_bundled build $(BUNDLE_NAME)

.PHONY: juice-run-ui
juice-run-ui:
	@$(JUICE) mcp_bundled run --bundle --env $(ENV_FILE) $(BUNDLE_NAME) ui

.PHONY: juice-run-api
juice-run-api:
	@$(JUICE) mcp_bundled run --bundle --env $(ENV_FILE) $(BUNDLE_NAME) api

.PHONY: juice-run-mcp_server
juice-run-mcp_server:
	@$(JUICE) mcp_bundled run --bundle --env $(ENV_FILE) $(BUNDLE_NAME) mcp_server

.PHONY: juice-run-mcp_server-test
juice-run-mcp_server-test:
	@echo '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_forecast","arguments":{"city":"Tokyo"}}}' \
  | $(JUICE) mcp_bundled run --bundle --env $(ENV_FILE) $(BUNDLE_NAME) mcp_server

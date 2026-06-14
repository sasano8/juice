# juice タスク
# JUICE はインストール済みなら `juice` に上書き可:  make juice-all JUICE=juice
JUICE ?= uv run python -m src
BUNDLE_NAME ?= weather-bot
# api | mcp_server | ui
RUN_MODE ?= api
# docker --env-file で読み込む .env（無ければ自動スキップ）
ENV_FILE ?= .env.agent
# ruff は uvx で都度実行（dev 依存に入れない）。
# 再現性のためバージョンを固定する（未固定だと uvx が毎回最新を取得し format/lint がドリフトする）。
RUFF ?= uvx ruff@0.15.17

# ===== 開発用定形タスク（format → lint → test を再現性をもって一括実行）=====

.PHONY: format
## ruff でコードを自動整形する（import 整理 + format）
format:
	@$(RUFF) check --select I --fix .
	@$(RUFF) format .

.PHONY: lint
## ruff で lint する（整形差分も検出。CI と同じ判定）
lint:
	@$(RUFF) check .
	@$(RUFF) format --check .

.PHONY: test
## pytest を実行する
test:
	@uv run pytest

.PHONY: check
## CI と同じ静的検査一式（lint + test）。コミット前に通すこと
check: lint test

.PHONY: dev
## 開発ループの定形: 整形してから検査一式（format → lint → test）
dev: format lint test

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

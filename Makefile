# juice タスク
# JUICE はインストール済みなら `juice` に上書き可:  make juice-all JUICE=juice
JUICE ?= uv run python -m src
BUNDLE_NAME ?= weather-bot

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

.PHONY: juice-run
## docker run コマンド（mcp_server を起動）を生成・表示する（テスト用。実行は ... run --run）
juice-run:
	@$(JUICE) mcp_bundled run $(BUNDLE_NAME) --build

.PHONY: juice-run
## docker run コマンド（mcp_server を起動）を生成・表示する（テスト用。実行は ... run --run）
juice-test:
	@echo '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_forecast","arguments":{"city":"Tokyo"}}}' \
  | $(JUICE) mcp_bundled run $(BUNDLE_NAME) --build

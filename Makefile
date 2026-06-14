# juice タスク
# JUICE はインストール済みなら `juice` に上書き可:  make juice-all JUICE=juice
JUICE ?= uv run python -m src
BUNDLE_FILE ?= bundle.yml
BUNDLE_NAME ?= weather-bot

.PHONY: juice-all
## 全レイヤを依存順（instance→tool）に一覧表示する
juice-all:
	@$(JUICE) all list

.PHONY: juice-bundle
## bundle 宣言（BUNDLE_FILE）を成果物名（BUNDLE_NAME）へ登録する（テスト用）
juice-bundle:
	@$(JUICE) mcp_bundled bundle -f $(BUNDLE_FILE) $(BUNDLE_NAME)

.PHONY: juice-build
## 登録済み宣言を参照して成果物名（BUNDLE_NAME）をビルド（収集）する（テスト用）
juice-build:
	@$(JUICE) mcp_bundled build $(BUNDLE_NAME)

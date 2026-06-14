# juice タスク
# JUICE はインストール済みなら `juice` に上書き可:  make juice-all JUICE=juice
JUICE ?= PYTHONPATH=src python3 -m juice.cli

.PHONY: juice-all
## 全レイヤを依存順（instance→tool）に一覧表示する
juice-all:
	@$(JUICE) all

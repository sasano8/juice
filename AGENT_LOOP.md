# AGENT_LOOP: 継続的改善ループ

> このドキュメントは AI エージェントが自律的にプロジェクトを改善するための指示書です。
> エージェントはこのファイルを読み、タスクを選び、実装し、次のエージェントへ引き継ぎます。

---

## 現在の状態（State）

### プロジェクト概要
**juice** は AI エージェントのパッケージマネージャー。tool（MCP server）・skill・subagent を
`mcp_bundled` として宣言し、LangGraph で LLM と MCP server を連携した会話エージェントを
`bundle → build → run` で組み上げて起動する。

### 実装済み
- [x] 基本的なレイヤ構造（tool / skill / subagent / mcp_bundled）
- [x] `bundle.yml` による宣言
- [x] `init / bundle / build / run` コマンド
- [x] LangGraph 連携（api / ui / mcp_server モード）
- [x] Docker コンテナ化

### 未実装・課題
- [~] `juice.yaml` による宣言的ワークスペース（workspace.md 参照）※パーサ実装済み（C001）。lock/apply は未
- [ ] `juice lock` / `juice apply` コマンド
- [ ] バージョニングと依存解決
- [ ] workflow（複数 instance の協調）
- [x] テストカバレッジ（pytest 基盤・36 ケース。`make test`）
- [x] CI/CD パイプライン（GitHub Actions: lint + test）
- [x] lint/format 統一（ruff。`make format` / `make lint`）
- [ ] ドキュメントの整備

---

## 改善ループ（Loop）

エージェントは以下のサイクルを繰り返します：

```
┌─────────────────────────────────────────────────────────┐
│  1. ASSESS: 現状を評価                                   │
│     - このファイルを読む                                 │
│     - バックログから優先タスクを選ぶ                     │
│     - 実装可能か判断する                                 │
├─────────────────────────────────────────────────────────┤
│  2. PLAN: 計画を立てる                                   │
│     - 実装方針を決める                                   │
│     - 影響範囲を特定する                                 │
│     - テスト方法を決める                                 │
├─────────────────────────────────────────────────────────┤
│  3. IMPLEMENT: 実装する                                  │
│     - コードを書く                                       │
│     - テストを書く                                       │
│     - ドキュメントを更新する                             │
├─────────────────────────────────────────────────────────┤
│  4. VERIFY: 検証する                                     │
│     - テストを実行する                                   │
│     - 動作確認する                                       │
│     - lint / format を通す                               │
│     - サンプルデプロイの E2E 確認（下記。可能な限り常に）│
├─────────────────────────────────────────────────────────┤
│  5. UPDATE: 状態を更新                                   │
│     - このファイルの State を更新                        │
│     - バックログを更新                                   │
│     - 次のエージェントへの引き継ぎを書く                 │
└─────────────────────────────────────────────────────────┘
```

---

## サンプルデプロイの E2E 確認（VERIFY 補足）

Makefile にはサンプル（`weather-bot`）の **デプロイフロー** が含まれる
（`make juice-run-api` ＝ bundle→build→run を api モードで起動。`juice-run-ui` / `juice-run-mcp_server` /
`juice-run-mcp_server-test` も同様）。エージェントは VERIFY 工程で、**可能な限り常に**この会話 API を
起動して以下の 3 点を確認すること（API キーや docker が無い等で起動できない場合のみスキップし、
その旨を引き継ぎに残す）。

**起動と接続:**
- `make juice-run-api`（既定 `BUNDLE_NAME=weather-bot`、`--env .env.agent`）で
  `http://localhost:8000` に api モードで起動。会話は OpenAI 互換の
  `POST /v1/chat/completions`（`{"messages":[...]}`）か、簡易 UI の `GET /chat`。
- LLM 呼び出しに `ANTHROPIC_API_KEY` が必要（`.env.agent` か環境変数で注入）。
  未設定だと `/v1/chat/completions` は 400 `missing_api_key` を返す → その場合はスキップ扱い。

**確認する 3 点:**
1. **ハロー → システムプロンプトの意図に沿うか。** 挨拶（例: 「こんにちは」）を送り、応答が
   subagent `forecaster` の system プロンプト（*天気予報アシスタント。簡潔で親切に、要点だけ*）の
   意図に沿っているかを確認する（天気の手伝いを申し出る／冗長でない 等）。
2. **東京の気温を確認できるか。** 「東京の気温は？」を送り、エージェントが weather tool
   （`get_forecast(city="Tokyo")`）を呼んで東京の予報・気温を返答に含めるかを確認する。
3. **モックの結果が含まれるか。** 上記応答に**モック値が混入していないか**を必ず確認する。
   同梱の weather server はモック実装で `get_forecast` は `"<city>: 晴れ 80C（モック予報）"` を返す。
   応答に `モック予報` / `80C` / 非現実的な値が出たら、**実 server 未差し替え（モック稼働中）**である旨を
   明示して引き継ぎに記録する（実データではないことを取り違えない）。

> tool 単体だけ素早く確かめたい場合は `make juice-run-mcp_server-test`
> （`get_forecast(Tokyo)` を JSON-RPC で直接叩く）でもモック応答を確認できる。
> ただし会話 API 経由（1〜3）が本筋で、subagent の意図適合まで見られるのはこちら。

---

## バックログ（Backlog）

優先度順。エージェントは上から順に取り組むこと。

### P0: 基盤整備（今すぐ）
| ID | タスク | 状態 | 備考 |
|----|--------|------|------|
| B001 | pytest によるテスト基盤構築 | ✅完了 | `tests/`（storage/registry/bundle/cli、36 ケース）。`make test` |
| B002 | CI（GitHub Actions）セットアップ | ✅完了 | `.github/workflows/ci.yml`（push/PR で lint + test） |
| B003 | ruff による lint/format 統一 | ✅完了 | pyproject に設定。`make format`/`make lint`/`make check`/`make dev` |

### P1: コア機能（次に）
| ID | タスク | 状態 | 備考 |
|----|--------|------|------|
| C001 | `juice.yaml` パーサ実装 | ✅完了 | `src/core/manifest.py`（パース＋構造/相互参照検証）。`juice manifest validate -f juice.yaml`。20 ケース |
| C002 | `juice lock` コマンド | 未着手 | 依存解決と lock ファイル生成。C001 の Manifest を入力にする |
| C003 | `juice apply` コマンド | 未着手 | 宣言的な reconcile |
| C004 | バージョニング機構 | 未着手 | SemVer 対応 |

### P2: 拡張機能（その後）
| ID | タスク | 状態 | 備考 |
|----|--------|------|------|
| E001 | workflow 実装 | 未着手 | 複数 instance の協調 |
| E002 | remote mcp_server 対応 | 未着手 | 外部サーバーの参照 |
| E003 | skill ライブラリ | 未着手 | 再利用可能な skill 集 |

### P3: 品質・UX（継続）
| ID | タスク | 状態 | 備考 |
|----|--------|------|------|
| Q001 | エラーメッセージの改善 | 未着手 | ユーザーフレンドリーに |
| Q002 | CLI ヘルプの充実 | 未着手 | 各コマンドの例を追加 |
| Q003 | ドキュメント整備 | 未着手 | architecture.md の更新 |

---

## 設計原則（Principles）

エージェントが実装時に守るべき原則：

### 1. 宣言的を優先
- 命令的なビルド手順より宣言的な spec を重視
- `juice.yaml` が唯一の正（source of truth）
- 再現性は spec + lock が担保

### 2. 標準フォーマットに準拠
- MCP（Model Context Protocol）に準拠
- Claude Code skill/subagent 形式に準拠
- 独自拡張は最小限に

### 3. 層の分離
- tool / skill / subagent / mcp_bundled / workflow の責務を明確に
- 上位層は下位層に依存、逆は禁止
- 各層は独立してテスト可能に

### 4. シンプルさを保つ
- 過度な抽象化を避ける
- 必要になるまで実装しない（YAGNI）
- コードよりドキュメントを先に書く

---

## 技術スタック（Stack）

| 領域 | 技術 | 再現性のための固定 |
|------|------|------|
| 言語 | Python | `.python-version` = **3.14**（uv が解決。CI も `uv python install` で同値） |
| パッケージ管理 | uv | `uv.lock` で依存を pin（`uv run`/`uv sync` で固定環境） |
| フレームワーク | LangGraph | （生成物 vendor/ 側。lint/test 対象外） |
| コンテナ | Docker | — |
| Lint/Format | ruff | `uvx ruff@0.15.17`（Makefile の `RUFF`。版を固定して整形ドリフトを防ぐ） |
| テスト | pytest | `uv.lock` で版 pin（`make test` = `uv run pytest`） |
| CI | GitHub Actions | `make lint` + `make test`。ローカルの `make check` と同一判定 |

> **再現性の方針:** 「同じ入力なら誰がどこで実行しても同じ結果」を保つため、ツールの版を固定する。
> Python は `.python-version`（単一の正、CI もこれを読む）、ruff は Makefile の `RUFF`、
> 依存は `uv.lock`。版を上げるときは固定箇所（`.python-version` / `RUFF`）を更新し、`make check` を
> 通してから commit すること。

---

## 引き継ぎ（Handoff）

> 最後に作業したエージェントがここに状況を記録する

### 最終更新: 2026-06-15（C001 完了）

**完了した作業:**
- C001（`juice.yaml` パーサ）を実装。`src/core/manifest.py` を新設。
  - workspace.md のスキーマ（mcp_servers / subagents / skills / mcp_bundled / instances）を
    型付き dataclass（`Manifest` ほか）へパースする `parse_manifest(text)` / `load_manifest(path)`。
  - 検証は **構造**（apiVersion=juice/v1、各要素の name 必須・重複禁止、型チェック）＋
    **相互参照**（mcp_bundled→subagent/skill/mcp_server、instance→mcp_bundled、
    subagent.allow_tools→mcp_server、tool の `from: <kind>:<name>` 形式）。不正は `ManifestError`。
  - CLI に `juice manifest validate -f juice.yaml` を追加（ok 要約 or `invalid manifest: ...`）。
  - core `__init__` に `Manifest / ManifestError / parse_manifest / load_manifest` を公開。
  - tests/test_manifest.py（20 ケース）＋ CLI 2 ケースを追加。計 58 ケース。`make check` 緑。
- テスト/フォーマットの**再現性を固定**（環境差による揺れを排除）:
  - ruff を `uvx ruff@0.15.17` に固定（Makefile の `RUFF`）。未固定だと毎回最新を取得し整形がドリフトする。
  - `.python-version` = 3.14 を追加。`uv run` がローカルでも 3.14 を使い、CI（`uv python install` が
    `.python-version` を読む）と一致。版の単一の正は `.python-version`。
  - pytest は `uv.lock` で pin 済み（`make test` = `uv run pytest`）。→ 確認は Python 3.14 / ruff 0.15.17 で 58 緑。
- （以前）P0 基盤整備（B001 / B002 / B003）完了：pytest 基盤・GitHub Actions CI・ruff 統一。

**次のエージェントへ:**
- C002（`juice lock`）へ。C001 の `Manifest` を入力に、参照パッケージ（mcp_server の npm 版など）と
  registry 解決を pin する juice.lock を生成する設計（docs/workspace.md「再現性のモデル」参照）。
  digest 取得元（npm / OCI / 独自）は未決の論点なので、まず lock のスキーマと冪等な書き出しから固めると良い。
- 着手前に必ず `make check` が緑であることを確認し、変更後も緑を保つこと（再現性のため）。
- 新規コードには tests/ に対応テストを追加。tmp レジストリは conftest の
  `bucket` / `registries` / `juice` フィクスチャを使う（manifest 系は文字列 fixture で十分）。

**注意点:**
- docs/ 内の design.md と workspace.md は旧設計（SUPERSEDED）だが、`juice.yaml` 系（C001〜）の
  出発点は workspace.md の宣言設計。bundle.yml ベースの現行パイプライン（build.md）とは別系統で、
  manifest.py は registry/storage に依存しない独立モジュールにしてある（層の分離）。
- manifest.py の error メッセージは E501 を避けるため簡潔化済み（bundle.py のみ per-file-ignore）。
  メッセージ文言を変える場合は test_manifest.py の `match=` も合わせて更新する。
- ruff の E501 は `src/core/bundle.py` のみ per-file-ignore（生成コードを文字列で埋め込むため）。
- CLI の list 系テストはリポジトリ同梱の実レジストリ（registries/default）に依存している。
  実レジストリの中身を変えるとテストの期待値も更新が必要。

---

## エージェント実行コマンド

このループを開始するには：

```bash
# Claude Code で実行
claude "AGENT_LOOP.md を読んで、バックログから1つタスクを選び、実装してください"

# または継続的に
claude "AGENT_LOOP.md のループを1サイクル実行してください"
```

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
│  5. UPDATE: 状態更新・引き継ぎ（運用ルール参照）         │
│     - ドキュメント更新／課題の書き出し                   │
│     - 作業中→直前の作業へ移し結果をまとめる              │
│     - 次の作業を計画し「作業中」に書く → commit          │
└─────────────────────────────────────────────────────────┘
```

---

## 運用ルール（UPDATE & HANDOFF の手順）

ステップ 5（UPDATE）は、**毎サイクル必ず次の順で実行する**。これにより「いま何が終わって・
次に何をするか」が常に [作業状態](#作業状態work-state) に表れ、どのエージェントでも引き継げる。

1. **直前の作業を仕上げる。** IMPLEMENT / VERIFY を終える（`make check` 緑・E2E 確認）。
2. **ドキュメント更新・課題の書き出し。** 仕様変更を docs に反映し、気づいた課題・TODO を
   バックログ or 「作業中」に書き出す（忘れる前に文章化する）。
3. **作業中 → 直前の作業 へ移す。** これまで「作業中」だった項目を「直前の作業」に移動し、
   **結果をまとめる**（何を変えたか・検証結果・関連 commit）。
4. **次の作業を計画して「作業中」に書く。** バックログから次の 1 つを選び、「作業中」に
   **概要（ゴール）とタスク（チェックリスト）／完了条件**を書き出す。
5. **ここで commit する。** 「完了した直前の作業 ＋ 次の作業の計画」を 1 コミットに残す
   （状態を書いてからコミットするのが順序。実装はまだ始めない）。
6. **作業中を参照して着手する。** 次サイクルの ASSESS は「作業中」を読むところから始め、
   そのタスクに取り掛かる。完了したら 1 に戻る。

> 要するに **「直前の作業＝直近に終えた成果」「作業中＝いま/次に取り組む計画」** の 2 つを
> 常に最新に保ち、その更新を commit の単位にする。

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

## 作業状態（Work State）

> [運用ルール](#運用ルールupdate--handoff-の手順)に従い毎サイクル更新する。
> commit は「直前の作業（完了）＋作業中（次の計画）」を書いてから行う。

### 直前の作業（Just Done） — 最終更新: 2026-06-15

- **C001（`juice.yaml` パーサ）を実装。** `src/core/manifest.py` を新設。
  - workspace.md のスキーマ（mcp_servers / subagents / skills / mcp_bundled / instances）を
    型付き dataclass（`Manifest` ほか）へパースする `parse_manifest(text)` / `load_manifest(path)`。
  - 検証は **構造**（apiVersion=juice/v1、各要素の name 必須・重複禁止、型チェック）＋
    **相互参照**（mcp_bundled→subagent/skill/mcp_server、instance→mcp_bundled、
    subagent.allow_tools→mcp_server、tool の `from: <kind>:<name>` 形式）。不正は `ManifestError`。
  - CLI に `juice manifest validate -f juice.yaml` を追加。core に `Manifest / ManifestError /
    parse_manifest / load_manifest` を公開。tests/test_manifest.py（20）＋ CLI 2 ケース。
- **テスト/フォーマットの再現性を固定**（環境差による揺れを排除）。
  - ruff を `uvx ruff@0.15.17` に固定（Makefile の `RUFF`）。`.python-version` = 3.14 を追跡し
    ローカル/CI を統一（CI は `uv python install` が読む）。pytest は `uv.lock` で pin。
- **このループ運用自体を明文化。** 「運用ルール（UPDATE & HANDOFF の手順）」と本「作業状態
  （直前の作業／作業中）」を AGENT_LOOP.md に追加。
- **結果:** `make check` 緑（計 58 ケース、Python 3.14.2 / ruff 0.15.17）。
- **関連 commit:** `2eaea6b`（C001＋P0 確定）/ `2f6990a`（再現性固定）/ `f56d022`（Python 3.14）/ 本コミット（運用ルール明文化）。

### 作業中（In Progress / Next） — C002: `juice lock`

**概要（ゴール）:** C001 の `Manifest` を入力に、参照を解決して `juice.lock` を**冪等に生成**する
`juice lock` コマンドを実装する。再現性の本体（spec＋lock）の lock 側を用意する
（docs/workspace.md「再現性のモデル」参照）。まずは registry 内の名前参照解決と lock スキーマを
固め、外部パッケージ（npm / OCI）の digest 取得は TODO として切り出す（YAGNI）。

**タスク（チェックリスト）:**
- [ ] `juice.lock` のスキーマ設計（例: `lockVersion` / `namespace` / レイヤ別の解決済みエントリ）。
- [ ] 解決ロジック: `Manifest` の名前参照を registry 上で解決（存在確認）。`src/core/lock.py` 新設想定。
- [ ] 外部パッケージの digest（npm / OCI / 独自）は未決の論点 → まずは「参照名の解決と pin の枠」だけ作り
      digest 欄は保留（取得元を決めてから埋める）。
- [ ] CLI `juice lock [-f juice.yaml] [-o juice.lock]`。再実行で**同一出力＝冪等**（キー順を固定）。
- [ ] tests/test_lock.py（解決成功・冪等性・未解決参照のエラー）。tmp レジストリ fixture を使う。
- [ ] docs 更新（workspace.md の lock 記述を実装に追従、必要なら build.md からリンク）。

**完了条件:** `juice lock -f juice.yaml` が `juice.lock` を冪等生成し、未解決参照は明確なエラー。
`make check` 緑（新規テスト含む）。

### 着手の手引き

- 着手前に必ず `make check` が緑であることを確認し、変更後も緑を保つ（再現性のため）。
- 新規コードには tests/ に対応テストを追加。tmp レジストリは conftest の
  `bucket` / `registries` / `juice` フィクスチャを使う（manifest 系は文字列 fixture で十分）。

### 注意点
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

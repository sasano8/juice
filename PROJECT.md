# PROJECT: juice の概要・課題・作業状態

> juice プロジェクトの **現状・バックログ（課題）・設計原則・スタック・作業状態** をまとめる。
> 開発サイクルの回し方（ループ手順・運用ルール）は **[AGENT_LOOP.md](AGENT_LOOP.md)** を参照。
> エージェントは毎サイクル、本書の「[作業状態](#作業状態work-state)」を起点に着手し、終了時に更新する。

---

## プロジェクト概要

**juice** は AI エージェントのパッケージマネージャー。tool（MCP server）・skill・subagent を
`mcp_bundled` として宣言し、LangGraph で LLM と MCP server を連携した会話エージェントを
`bundle → build → run` で組み上げて起動する。

### 実装済み
- [x] 基本的なレイヤ構造（tool / skill / subagent / mcp_bundled）
- [x] `bundle.yml` による宣言
- [x] `init / bundle / build / run` コマンド
- [x] LangGraph 連携（api / ui / mcp_server モード）
- [x] Docker コンテナ化
- [x] `juice.yaml` パーサ（C001。`juice manifest validate`）
- [x] `juice lock`（C002。manifest を解決し juice.lock を冪等生成）
- [x] `juice apply`（C003。宣言を registries へ冪等 reconcile＋prune）
- [x] `juice plan` ＋ apply の lock drift 検出（C005。lock → plan → apply の連携）
- [x] バージョニングの足場（C004。SemVer util＋manifest の version＋lock 記録）
- [x] version 制約参照（C006。`from: name@<制約>` を validate で充足チェック）
- [x] CLI ヘルプ・使い方（Q002。各コマンドに例＋宣言系の docs）
- [x] テスト基盤・CI・lint/format 統一（P0）

### 未実装・課題
- [x] `juice.yaml` による宣言的ワークスペース（parser/lock/apply/plan 揃い、lock 連携も実装）
- [~] バージョニング（C004 足場＋C006 制約参照済み）※範囲マッチ・複数版共存の依存解決は未
- [ ] 依存解決（範囲マッチ・複数版共存・レジストリ横断）— 必要になってから
- [ ] エラーメッセージの改善（Q001）/ architecture.md の整備（Q003）
- [ ] 外部パッケージの digest 取得（npm / OCI）— lock の `digest` 欄は現状 null（C002 の TODO）
- [ ] workflow（複数 instance の協調）
- [ ] OKF（Open Knowledge Format）を registries の md に自動適用＋name 検証（E004。要 OKF 調査）
- [ ] ドキュメントの整備

---

## バックログ（Backlog）

優先度順。エージェントは上から順に取り組むこと。

### P0: 基盤整備（今すぐ）
| ID | タスク | 状態 | 備考 |
|----|--------|------|------|
| B001 | pytest によるテスト基盤構築 | ✅完了 | `tests/`（storage/registry/bundle/cli/manifest）。`make test` |
| B002 | CI（GitHub Actions）セットアップ | ✅完了 | `.github/workflows/ci.yml`（push/PR で lint + test） |
| B003 | ruff による lint/format 統一 | ✅完了 | pyproject に設定。`make format`/`make lint`/`make check`/`make dev` |

### P1: コア機能（次に）
| ID | タスク | 状態 | 備考 |
|----|--------|------|------|
| C001 | `juice.yaml` パーサ実装 | ✅完了 | `src/core/manifest.py`（パース＋構造/相互参照検証）。`juice manifest validate -f juice.yaml` |
| C002 | `juice lock` コマンド | ✅完了 | `src/core/lock.py`。manifest 解決＋manifestDigest を冪等生成。`juice lock -f juice.yaml -o juice.lock` |
| C003 | `juice apply` コマンド | ✅完了 | `src/core/apply.py`。宣言を registries へ冪等 reconcile＋prune。`juice apply [--dry-run] [--no-prune]` |
| C005 | 宣言ライフサイクルの統合 | ✅完了 | `juice plan`＋apply の lock drift 検出（`--frozen`/`--require-lock`）。`lock_status` |
| C004 | バージョニング機構（足場） | ✅完了 | `src/core/semver.py`＋manifest の `version`＋lock 記録。`satisfies` まで |
| C006 | version 制約参照 | ✅完了 | `from: name@<制約>` を validate で充足チェック（後方互換） |

### P2: 拡張機能（その後）
| ID | タスク | 状態 | 備考 |
|----|--------|------|------|
| E001 | workflow 実装 | 未着手 | 複数 instance の協調 |
| E002 | remote mcp_server 対応 | 未着手 | 外部サーバーの参照 |
| E003 | skill ライブラリ | 未着手 | 再利用可能な skill 集 |
| E004 | OKF を registries の md に自動適用 | 未着手（要調査） | Google 公開の OKF 適用＋name 検証＋メタデータ抽出。下記「課題メモ」参照 |

### P3: 品質・UX（継続）
| ID | タスク | 状態 | 備考 |
|----|--------|------|------|
| Q001 | エラーメッセージの改善 | 🚧作業中 | ユーザーフレンドリーに（→「作業中」節） |
| Q002 | CLI ヘルプの充実 | ✅完了 | 各コマンドに使用例の epilog＋宣言系コマンドの docs（build.md） |
| Q003 | ドキュメント整備 | 未着手 | architecture.md の更新 |

### 課題メモ: E004 — OKF（Open Knowledge Format）適用（要調査・検討事項あり）

> **背景/目的:** Google が公開した **OKF（Open Knowledge Format）** を、registries 内の各 `.md`
> （tool / skill / subagent のメタデータ）へ**自動適用**する機能を追加する。
> ※ OKF の仕様はまだ完全には理解できていない。**着手前に OKF の内容を調査・確定する**こと（前提）。

**要件:**
1. **命名規約（name = ファイル名に従う）:** メタデータ内の `name` は、そのパッケージのファイル／
   ディレクトリ名に従って命名する（例: `tools/<dir>/index.md` の `name` は `<dir>` に一致）。
2. **検証で一致確認:** メタデータの `name` とディレクトリ名が一致することを**検証（validate）で確認**する。
3. **不一致時はユーザーに修正を求める:** 不一致でも**自動修正しない**。コピーとして使い回されたのか、
   移動されたのかを機械的に判断できないため、人間に判断を委ね、ユーザーへ修正を依頼する。
4. **メタデータの抽出キャッシュ:** リポジトリのトップに、各 md から抽出したメタデータをまとめた
   インデックスを置く。毎回 md の frontmatter をパースするコストを下げる狙い（高速化）。

**検討事項（Open Question）:**
- 要件 4 は「md 内 frontmatter」と「トップのメタデータインデックス」の **二重管理**になりうる。
  どちらを source of truth とするか／インデックスを生成物として ignore し再生成で同期するか／
  drift 検出（C005 と同様のダイジェスト照合）を設けるか、を決める必要がある。
  → 設計原則「宣言的を優先（唯一の正）」「生成物を焼かず spec から再生成」と整合させること。

**現状との関係:** 現 manifest パーサ（C001）は name の重複・型は検証するが、**registry の md の `name` と
ディレクトリ名の一致は未検証**。E004 はそこを埋める検証＋メタデータ抽出の話。`juice manifest validate` /
`juice apply` の materialize（C003）とも近いので、実装時は重複を避けて寄せる。

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

## サンプルデプロイの E2E 確認（VERIFY 用）

Makefile にはサンプル（`weather-bot`）の **デプロイフロー** が含まれる
（`make juice-run-api` ＝ bundle→build→run を api モードで起動。`juice-run-ui` / `juice-run-mcp_server` /
`juice-run-mcp_server-test` も同様）。エージェントは [VERIFY 工程](AGENT_LOOP.md)で、**可能な限り常に**
この会話 API を起動して以下の 3 点を確認すること（API キーや docker が無い等で起動できない場合のみ
スキップし、その旨を「作業状態」に残す）。

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
   明示して「作業状態」に記録する（実データではないことを取り違えない）。

> tool 単体だけ素早く確かめたい場合は `make juice-run-mcp_server-test`
> （`get_forecast(Tokyo)` を JSON-RPC で直接叩く）でもモック応答を確認できる。
> ただし会話 API 経由（1〜3）が本筋で、subagent の意図適合まで見られるのはこちら。

---

## 作業状態（Work State）

> [AGENT_LOOP.md の運用ルール](AGENT_LOOP.md)に従い毎サイクル更新する。
> commit は「直前の作業（完了）＋作業中（次の計画）」を書いてから行う。

### 直前の作業（Just Done） — 最終更新: 2026-06-15

- **Q002（CLI ヘルプの充実）を実装。** 増えたコマンド面の UX を底上げ。
  - トップレベル parser に宣言ライフサイクル（validate → lock → plan → apply）の `epilog` を追加
    （`RawDescriptionHelpFormatter` で整形維持）。各サブコマンドにも使用例の epilog を付けた。
  - docs/build.md に「宣言系コマンド（juice.yaml ライフサイクル）」の節を追加。
  - tests/test_cli.py に help 検証 5 ケース（`-h` 出力に例文字列が含まれること）。
- **結果:** `make check` 緑（計 121 ケース、Python 3.14.2 / ruff 0.15.17）。
- **関連 commit:** `9c6113c`（C006）に続き、本コミット（Q002）。
  ※ E2E 確認（会話 API）は今回 CLI/docs 改善のため対象外（通常スキップ条件）。

### 作業中（In Progress / Next） — Q001: エラーメッセージの改善

**概要（ゴール）:** ユーザーが詰まったとき**何をすればよいか**が分かるよう、宣言系コマンドの
エラー表示を整える。具体的には (1) どのファイルで失敗したかを示す、(2) よくある失敗に次の一手の
ヒントを添える、(3) CLI のエラー出力（prefix・exit code）を統一する。挙動（成功時）は変えない。

**タスク（チェックリスト）:**
- [ ] CLI のエラーは stderr＋exit 1 で統一されているか点検（lock も LockError を拾うか等）。`_fail(msg)` に集約も検討。
- [ ] 失敗時にファイルパスを含める（例: `invalid manifest (juice.yaml): ...`）。
- [ ] よくある失敗にヒント: lock 不在/drift → 「`juice lock` を実行」、manifest 不在 → パス確認、
      未対応 apiVersion → 対応版を提示（既に一部あり。文言を揃える）。
- [ ] YAML 構文エラーは行番号を含める（PyYAML の mark を活かす。`parse_manifest` の wrap を確認）。
- [ ] tests: 代表的な失敗（不在ファイル/不正 apiVersion/drift+frozen）でメッセージにパスやヒントが出ること。

**完了条件:** 主要な失敗系でメッセージに「どこで・何が・次にどうする」が含まれ、exit code が一貫する。
`make check` 緑（メッセージ検証テスト含む）。

**留意点:** メッセージ文言を変えると既存テストの `match=` が壊れうるので、変更時は該当テストも更新する。
過剰な作り込みは避け、よくある失敗に絞る（YAGNI）。

### 着手の手引き

- 着手前に必ず `make check` が緑であることを確認し、変更後も緑を保つ（再現性のため）。
- 新規コードには tests/ に対応テストを追加。tmp レジストリは conftest の
  `bucket` / `registries` / `juice` フィクスチャを使う（manifest 系は文字列 fixture で十分）。

### 注意点
- ドキュメントは **手順（[AGENT_LOOP.md](AGENT_LOOP.md)）／状態（本書）** に分離している。
  ループの回し方を変えるなら AGENT_LOOP.md、現状・課題・作業状態を更新するなら本書。
- docs/ 内の design.md と workspace.md は旧設計（SUPERSEDED）だが、`juice.yaml` 系（C001〜）の
  出発点は workspace.md の宣言設計。bundle.yml ベースの現行パイプライン（build.md）とは別系統で、
  manifest.py は registry/storage に依存しない独立モジュールにしてある（層の分離）。
- manifest.py の error メッセージは E501 を避けるため簡潔化済み（bundle.py のみ per-file-ignore）。
  メッセージ文言を変える場合は test_manifest.py の `match=` も合わせて更新する。
- ruff の E501 は `src/core/bundle.py` のみ per-file-ignore（生成コードを文字列で埋め込むため）。
- CLI の list 系テストはリポジトリ同梱の実レジストリ（registries/default）に依存している。
  実レジストリの中身を変えるとテストの期待値も更新が必要。

# PROJECT: juice の概要・課題・作業状態

> juice プロジェクトの **現状・バックログ（課題）・設計原則・スタック・作業状態** をまとめる。
> 開発サイクルの回し方（ループ手順・運用ルール）は **[AGENT_LOOP.md](AGENT_LOOP.md)** を参照。
> エージェントは毎サイクル、本書の「[作業状態](#作業状態work-state)」を起点に着手し、終了時に更新する。

---

## プロジェクト概要

**juice** は AI エージェントのための**宣言的パッケージマネージャー＋デリバリ・パイプライン**。
1 つの spec（`juice.yaml`）から、解決 → 整合 → 生成を経て「動かせる成果物」（registries / docker image /
docker-compose・k8s manifest）まで一気通貫で組み上げる。juice 自身は実行せず、実行基盤（docker /
k8s＋ArgoCD / cron）に成果物を渡す（依存を宣言・解決・版管理する PM の口と、配備まで運ぶパイプラインの口は
同一物の両端）。リファレンス実装として LangGraph で LLM と MCP server を連携した会話エージェント
（tool / skill / subagent を `bundle` 化）を同梱。現状は AI 特化、機構は組織内資産（dataset / model /
知識）へ一般化しうる（構想）。

### 実装済み
- [x] 基本的なレイヤ構造（tool / skill / subagent / bundle）
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
- [x] エラーメッセージ（Q001。ファイルパス＋ヒント＋YAML 行情報、_fail で集約）
- [x] architecture.md に宣言系レイヤを反映（Q003。概念モデル↔juice.yaml の 2 軸＋ライフサイクル）
- [x] registry の健全性検査（E004。name=dir＋OKF 適合＋メタデータ索引 drift。`juice registry verify`/`index`）
- [x] okf_catalog_cache（OKF メタデータの AI 向け派生ビュー。`juice okf-cache`。index 集約を標準スキーマ＝identity＋OKF type＋推奨フィールドへ射影。type/tag 絞り込み）※コア概念 catalog（構造インベントリ）とは別物。[docs/glossary.md](docs/glossary.md)
- [~] workflow を宣言パイプラインに載せる（E001 第一歩。manifest/validate/apply materialize＋plan・drift 対応）
- [~] workflow / schedule のデプロイ成果物生成（E001。workflow=常駐〔compose service／k8s Deployment〕、schedule=定期実行のワークロード・ジョブ〔k8s CronJob／compose one-shot〕。生成のみ）
- [x] schedule を registry レイヤに昇格（E001。`apply` で materialize＋index／verify／list 横断）
- [x] 宣言→依存物を遡る解決（E001。`deploy.dependency_closure`。build 時に依存閉包＝build 対象を表示）
- [x] 依存の実ビルド起動（E001。`juice workflow/schedule build --build-deps` で closure を bundle→build）
- [x] step 協調の起動順（E001。workflow/compose に宣言順の直列 `depends_on`。k8s/schedule は不変）
- [x] workflow ライフサイクル・フック（E001。`hooks[]`＝pre_deploy/post_deploy。Helm 流。compose=完了待ち
  one-shot〔先頭 step が `service_completed_successfully`〕／k8s=Job。生成のみ・実行は基盤委譲）
- [x] vendored workflow（終端・外部 compose を直に同梱。`juice workflow build` が passthrough。例: `langfuse`）
- [x] remote mcp_server（E002。`url`＋`transport`〔streamable_http/sse〕で外部参照＝黒箱。command と排他、
  vendoring しない。validate/lock〔v2〕/apply materialize/bundle 接続〔agent.json・graph.py〕まで対応）
- [x] python_packages を実レイヤ化（PyPI 様の registry。`config.LAYERS`/`ENTRY_FILES`〔index.yml〕/`ALL_ORDER`
  登録で `all list`/`python_package list`/`registry verify`〔name=dir〕/`index` の横断対象。manifest 非対象＝
  apply の prune 外。wheel 格納・PEP 503 風 index 提供は未〔YAGNI〕）
- [x] storage を独立パッケージ `juice_storage` に抽出（`src/` と同列・最上位。juice の wheel に同梱。
  `src/core` は後方互換で再エクスポート継続。`factory.py` が backend→Storage の単一差し込み点）
- [ ] triggers（juice 内蔵スケジューラ＝コントロールプレーン。配備操作の定期実行）— E005。**構想・未実装**
- [x] テスト基盤・CI・lint/format 統一（P0）

### 未実装・課題
- [x] `juice.yaml` による宣言的ワークスペース（parser/lock/apply/plan 揃い、lock 連携も実装）
- [~] バージョニング（C004 足場＋C006 制約参照済み）※範囲マッチ・複数版共存の依存解決は未
- [ ] 依存解決（範囲マッチ・複数版共存・レジストリ横断）— 必要になってから
- [—] 外部パッケージの digest 取得 — **juice の責務外として撤去**。内容 pin は各エコシステムの build
  （Python は `uv.lock`、npm は `package-lock.json`）に委譲。juice は bundle/build に集中する
- [~] workflow（複数 instance の協調）— E001。**定義(workflow=常駐)とトリガ(schedule=定期実行)を分離**。宣言パイプライン（manifest/validate/apply＋plan・drift）＋デプロイ成果物生成（compose／k8s。生成のみ）は実装済。**schedule の registry レイヤ化・実起動・スケジューラ稼働・step 協調は未**
- [x] OKF を registries の md に自動適用＋name 検証（E004 完了）※name=dir 検証・OKF 適合（`type`）検証・メタデータ索引（生成・drift 検出）すべて実装済（`juice registry verify` / `index`）
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
| C002 | `juice lock` コマンド | ✅完了 | `src/core/lock.py`。manifest 解決＋manifestDigest を冪等生成。外部パッケージの内容 digest は juice の責務外として撤去（各 build に委譲） |
| C003 | `juice apply` コマンド | ✅完了 | `src/core/apply.py`。宣言を registries へ冪等 reconcile＋prune。`juice apply [--dry-run] [--no-prune]` |
| C005 | 宣言ライフサイクルの統合 | ✅完了 | `juice plan`＋apply の lock drift 検出（`--frozen`/`--require-lock`）。`lock_status` |
| C004 | バージョニング機構（足場） | ✅完了 | `src/core/semver.py`＋manifest の `version`＋lock 記録。`satisfies` まで |
| C006 | version 制約参照 | ✅完了 | `from: name@<制約>` を validate で充足チェック（後方互換） |

### P2: 拡張機能（その後）
| ID | タスク | 状態 | 備考 |
|----|--------|------|------|
| E001 | workflow 実装 | 🚧一部完了 | 定義(workflow=常駐)とトリガ(schedule=定期実行)を分離。宣言パイプライン＋デプロイ成果物生成（compose＋k8s）＋schedule の registry レイヤ昇格＋依存閉包解決（`deploy.dependency_closure`）＋依存の実ビルド起動（`build --build-deps`）＋step 起動順（compose `depends_on`）は実装済。残りは実起動(`up`/`kubectl apply`)・スケジューラ稼働・step 完了待ち/DAG |
| E002 | remote mcp_server 対応 | ✅完了 | `url`＋`transport`（streamable_http/sse）で外部参照（黒箱）。command と排他。`manifest.py`（McpServerSpec.url/transport＋`is_remote`＋検証）／`lock.py`（v2・url/transport 記録）／`apply.py`（remote materialize＝command/args 無し）／`bundle.py`（vendoring 除外＋agent.json/graph.py が url 接続）。SUPPORTED_BIND_KINDS は据え置き（remote は server の属性であり bind kind ではない） |
| E003 | skill ライブラリ | 未着手 | 再利用可能な skill 集 |
| E004 | OKF を registries の md に自動適用 | ✅完了 | name=dir 検証＋OKF 適合（`type`）検証（`src/core/metadata.py`）＋メタデータインデックス生成・drift 検出（`src/core/index.py`）。`juice registry verify`／`index`。下記「課題メモ」参照（任意の follow-up あり） |
| E005 | triggers（juice 内蔵スケジューラ） | 構想・未着手 | コントロールプレーンの定期トリガ。下記「課題メモ: E005」参照 |
| E006 | shoudou_storage 統合 | 🚧足場のみ | 物理ストレージ抽象を redis/nats/s3/local バックエンドへ拡張。下記「課題メモ: E006」参照 |

### P3: 品質・UX（継続）
| ID | タスク | 状態 | 備考 |
|----|--------|------|------|
| Q001 | エラーメッセージの改善 | ✅完了 | パス＋ヒント＋YAML 行情報、`_fail` で集約 |
| Q002 | CLI ヘルプの充実 | ✅完了 | 各コマンドに使用例の epilog＋宣言系コマンドの docs（build.md） |
| Q003 | ドキュメント整備 | ✅完了 | architecture.md に宣言系レイヤ（juice.yaml→lock→plan→apply）＋概念モデルとの対応を追記 |

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

**現状との関係:** 現 manifest パーサ（C001）は name の重複・型は検証するが、registry の md の `name` と
ディレクトリ名の一致は別。**要件 2（name=dir 検証）は実装済み**（`src/core/metadata.py` の `verify_names` /
CLI `juice registry verify`。frontmatter＋純 YAML 双方からメタデータ抽出、不一致は報告のみ＝要件 3 も満たす）。
**要件 4（メタデータインデックス）も実装済み**（`src/core/index.py` の `build_index` / `write_index` /
`index_status`、CLI `juice registry index`＋`verify` への drift 照合相乗り）。上記 Open Question は
**「md が source of truth、`juice.index.yml` は生成物。`juice registry index` で再生成して同期し、
`digest` 照合で drift 検出」**（C005 と同型）で解消。索引ファイルが無ければ verify は drift 検査をスキップ
（強制しない）。
**要件 1（OKF 準拠の frontmatter スキーマ）も実装済み＝E004 完了。** OKF v0.1（Google Cloud、
[GoogleCloudPlatform/knowledge-catalog](https://github.com/GoogleCloudPlatform/knowledge-catalog) `okf/SPEC.md`）
を一次情報で調査した。OKF は **`.md` の concept document に非空 `type` を必須**とする（推奨フィールド
title/description/resource/tags/timestamp は任意）。juice の対応（ユーザー選択＝「`type` 正式採用、`kind` 併記」）:
- `.md` レイヤ（tool / skill / subagent / workflow）に OKF 標準の `type` を持たせる。tool は既存の
  `type: mcp-server` を OKF concept type として再利用（衝突なし）。subagent/skill/workflow は `type` を追加。
  `kind`（juice のレイヤ分類）は後方互換のため併記。純 YAML マニフェスト（bundle/instance、apiVersion/kind ＝
  k8s 流儀）は OKF の `.md` concept document ではないため対象外。
- `metadata.py` の `verify_okf`（非空 `type` を検証、報告のみ・自動修正なし）＋ `juice registry verify` に相乗り
  （name=dir・OKF 適合・索引 drift の 3 点を束ねた「registry の健全性」検査）。apply の materialize（C003）も `type` を生成。
**任意の follow-up:** ①OKF 推奨フィールドの**横断ビュー**は `juice okf-cache`（`src/core/okf_catalog_cache.py`）で実装済
（index 集約を identity＋OKF type＋推奨フィールド〔title/description/tags/resource/timestamp〕へ射影、type/tag 絞り込み）。
※ユーザー整理で「OKF 由来・不安定・AI 連携用の周辺機能」と位置づけ、コア概念 catalog（構造インベントリ）と語を分離（[docs/glossary.md](docs/glossary.md)）。
推奨フィールドの**充足度の強制**（description 必須化等）は verify を壊さない方針のため引き続き未着手（報告のみ）。②OKF 予約名
`index.md`（frontmatter 無しの目次）と juice の concept 用 `index.md` の名前衝突の整理。③`log.md`（更新履歴）対応。
④`kind` を将来 `type` へ一本化する移行（現状は併記）。いずれも必要になってから。

### 課題メモ: E005 — triggers（juice 内蔵スケジューラ＝コントロールプレーン）※構想・未実装

> **背景:** ユーザーとの設計対話で「スケジューラのターゲット」を 2 種に分類した（taxonomy＝分類）。
> 「何を定期実行するか」で分かれる:
> - **(A) ワークロード・ジョブ**（データプレーン）… デプロイ済みコンテナを定期実行。**= 現 `schedules:`**
>   （→ k8s CronJob ／ docker は cron 非対応なので外部 cron＋one-shot）。**実装済（生成のみ）**。
> - **(B) パイプライン・トリガ**（コントロールプレーン）… juice の**配備操作**（apply / redeploy 等）を
>   定期実行（例: 毎日 1 時にクリア→再デプロイ）。**= 本 E005 `triggers:`**。

**方針（ユーザー決定）:** (B) は **juice 内蔵スケジューラ（デーモン）** で実現する。ArgoCD 本体が常駐して定期
sync（再 apply）するのと同型。**「juice はワークロードを実行しない」原則は (A) に適用**され、(B) は
コントロールプレーンの常駐＝ワークロードではないので矛盾しない（README の「ワークロードを実行しない」が既に
この区別を先取り）。**今は概念のみ・未実装**（将来構想）。

**未決（実装時に設計）:** 名前は `triggers:`（`{name, cron, action: apply|redeploy, scope}` 想定）。
デーモンの**状態永続化**（最終実行時刻）・**missed run** の扱い・**HA**・常駐プロセスの配置。外部委譲
（host cron / CI cron / ArgoCD 自動 sync が `juice apply` を叩く）との棲み分け。データプレーンの `schedules:`
（CronJob）とは生成物も実行主体も別概念として保つ。

### 課題メモ: E006 — shoudou_storage 統合（ストレージ機能の拡張）※足場のみ

> **背景/ゴール:** juice の物理ストレージ抽象（現 `juice_storage` ＝ `Storage`/`LocalFileStore` 系）を、
> ユーザーが追加した **`shoudou_storage`**（リポジトリ最上位の独立パッケージ。`FileStore` /
> `LocalFileStore` / `NatsObjectFileStore` / `S3FileStore` などのバックエンドを持つ）に**結合**したい。
> 将来は **shoudou_storage を別ライブラリとして抽出**する（juice はそれを利用する側になる）。

**現状（足場・このサイクルで追加。**未統合**）:**
- `shoudou_storage/__init__.py` を最上位に追加（`src` / `juice_storage` と同列）。`FileStore`（Protocol）と
  local/nats/s3 バックエンドを内包。`__init__` 直下は stdlib のみ import（redis/nats/aiobotocore/httpx は
  バックエンドで遅延 import）。
- 依存を **dependency-group `shoudou-storage`**（`redis>=5.0.0` / `nats-py>=2.0.0` / `aiobotocore>=2.0.0` /
  `httpx>=0.27.0`）に分離（juice 本体の `[project.dependencies]` には入れない）。**抽出時はこのグループを
  そのまま新ライブラリの `[project.dependencies]` へ移す**。
- `[tool.uv] default-groups = ["dev", "shoudou-storage"]` で **`uv run`/`uv sync` が自動同期**
  （Makefile の `JUICE ?= uv run python -m src` は変更不要）。
- wheel 同梱（`packages = ["src", "juice_storage", "shoudou_storage"]`）。

**制約（2026-06-20 ユーザー決定）:** shoudou_storage は別ライブラリ抽出予定のため **pristine に保つ**。
juice 都合で FileStore に `walk`/`delete` 等を足す方針は**却下**。統合するなら adapter 側で現状の
`save/get/list/exists` だけから階層 Storage を構成するか、先に doc-first で設計合意する（→「作業中」候補 4）。
なお `create_file_store` のベタ書きデフォルトパス `/app/data` は除去済（local は `local_dir` 必須化）。

**未統合（＝次にやること）:**
- juice の storage 差し込み点（`factory.py` の backend→Storage）から **shoudou_storage の FileStore を選べる**
  ようにする（`juice_storage.Storage` と `shoudou_storage.FileStore` のインターフェース整合／アダプタ）。
- `Config.backend`（local/s3 …）と shoudou_storage バックエンド（nats/s3/local）の対応付け、接続情報
  （redis/nats/s3 のエンドポイント・認証）の注入経路。
- 最終的に shoudou_storage を別 repo/ライブラリへ抽出（依存は上記グループを持ち出す）。

**注意:** 現状は**足場のみで未コミットの可能性**。`shoudou_storage` は src からまだ import されていない
（`grep shoudou_storage src/` が空）＝juice 本体の挙動には未影響。`make check` は緑（221）。

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
- tool / skill / subagent / bundle / workflow の責務を明確に
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

Makefile にはサンプル（`mcp_weather-bot`）の **デプロイフロー** が含まれる
（`make juice-run-api` ＝ bundle→build→run を api モードで起動。`juice-run-ui` / `juice-run-mcp_server` /
`juice-run-mcp_server-test` も同様）。エージェントは [VERIFY 工程](AGENT_LOOP.md)で、**可能な限り常に**
この会話 API を起動して以下の 3 点を確認すること（API キーや docker が無い等で起動できない場合のみ
スキップし、その旨を「作業状態」に残す）。

**起動と接続:**
- `make juice-run-api`（既定 `BUNDLE_NAME=mcp_weather-bot`、`--env .env.agent`）で
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

### 直前の作業（Just Done） — 最終更新: 2026-06-20

- **storage の `SafeKeyValueStore` を「唯一の KVS wrapper」に統合（パス検証＋download/キャッシュ）。**
  ユーザー方針「ラッパは 1 枚・差し替えるのは backend だけ（ネストは性能低下＋利用者ごとに挙動が割れる）」。
  - **download/キャッシュ**（PyTorch のモデル DL 様）を `SafeKeyValueStore` に吸収＝`download(key, *, force) -> Path`＋
    `cache_dir`。当初は別クラス `DownloadCache`（`download.py`）で実装したが、**1 枚ラッパー方針で統合し download.py は廃止**。
  - キャッシュ先は常にローカル FS・sync。`cache_dir` は init で絶対パス固定（cd 非依存。既定 `~/.cache/shoudou_storage`）。
    キャッシュ済み判定は存在ベース（上流更新の自動無効化は KVS に per-key メタデータが無いため未対応＝リモート backend 向け）。
  - キー検証は既存の `validate_safe_path` を流用（キャッシュ先の path traversal を防止）。`SafeFileStore` は従来どおり（download なし）。
  - **結果:** `pytest tests_storage/ -W error` 緑（40）、juice `make check` 緑（221）。
  - **関連 commit:** 本コミット（SafeKeyValueStore に download 統合）。

- **storage に接続ライフサイクル（connect/aclose ＋ `connecting` ＋ `ConnectPolicy`）を追加。**
  「init では接続せず `async with` で接続」「接続確認するか無視するか」「リトライ/timeout/deadline」をユーザー対話で設計。
  - **connect/aclose**（Protocol＋全 backend＋Safe＋sync bridge）：Local=dir 用意の体裁／S3=`head_bucket` 到達確認／
    NATS=`_get_obs` で確立＋`nc.close`。`_S3Base`/`_NatsBase` に置いたので FileStore（S3/NATS）も同ステップ。
  - **`connecting(factory, *, verify, policy)`**：実体生成と接続を `__aenter__` まで遅延（factory 包み＝接続前状態）。
    `verify=True` は接続失敗を送出（fail-fast）／`verify=False` は無視して先へ。**verify は policy と別引数**（ユーザー決定）。
  - **`ConnectPolicy`**（dataclass・改名前は RetryPolicy）：`max_retry`(=`float("inf")` で無制限・既定 inf)・`timeout`・
    `delay`・`backoff`・`max_delay`・`deadline`。**1 回の待機は timeout と残り deadline の小さい方で縛る**
    （`timeout=None` でも deadline があれば 1 回のハングで無限待機しない）。両 None のときだけ無制限。
    プリセット `default()`/`fail_fast()`/`forever()`（forever=deadline 無しで起動まで無期限・per-attempt timeout は残す）。
  - **入口** `connect_key_value_store(backend, *, verify, policy, **opts)`。
  - **結果:** `pytest tests_storage/ -W error` 緑（36）、juice `make check` 緑（221）。
  - **caveat:** 既定 policy は max_retry=inf＋deadline=60 ＝失敗時 60s 粘るので、即決させたいテストは `fail_fast`/`max_retry=0` を渡す。
  - **関連 commit:** 本コミット（接続ライフサイクル＋ConnectPolicy）。

- **storage の KeyValueStore に CRUD/保守操作を拡充（delete / cp / mv / vacuum）＋ Local 書き込みを原子的に。**
  - **delete**（Protocol＋全 backend＋Safe＋sync＋bridge）：Local は unlink のみ（**親ディレクトリは残す**＝ユーザー決定）、
    S3=delete_object、NATS=obs.delete。無いキーは無視。
  - **cp / mv**（Protocol に追加＝ユニバーサル操作）：汎用は `_kv_copy`/`_kv_move`（get→put／+delete）。Local の **mv は
    `os.replace`＝原子的 rename**、S3 cp は `copy_object`（サーバ側）。src 無しは `FileNotFoundError`。Safe は src/dst 両方検証。
  - **vacuum**（`LocalKeyValueStore` 固有・Protocol 非搭載）：空ディレクトリを bottom-up に再帰削除。delete と分離した保守操作
    （空ディレクトリは Local FS 特有＝s3/nats はフラットで概念なし、のため抽象 IF は汚さない）。
  - **アトミック書き込み**：`_atomic_write_bytes`（temp+`os.replace`）で `LocalKeyValueStore.put` を all-or-nothing 化。
    `LocalFileStore.open("wb")` は `_LocalAtomicWriter`（一時ファイルへ書き、正常 close でのみ確定・例外時は破棄）。
    **S3/NATS は元々アトミック**（Put/multipart complete・put 完了まで不可視）なので追加対応不要。
  - **結果:** `pytest tests_storage/ -W error` 緑（25）、juice `make check` 緑（221）。S3/NATS は fake で検証（実機 follow-up）。
  - **関連 commit:** 本コミット（delete/cp/mv/vacuum＋Local 原子的書き込み）。

- **storage に真のストリーミング FileStore（S3 / NATS）を追加＋テスト置き場を `tests_storage/` へ移設。**
  前項の redesign に続けて、全体バッファの `KeyValueFileStore` に対し**一定/低レイテンシ**のストリーミング実装を足した。
  - **`S3FileStore`**（真のストリーミング）：read=`get_object` の body を `read(size)` で逐次／write=**multipart upload**
    （`part_size` ごと upload_part、close で残りを最終パート＋complete、空は put_object）。接続部は `_S3Base` に共通化。
  - **`NatsFileStore`**：read=`get(writeinto=sink)` を背景タスク化し `asyncio.Queue` 経由で逐次配送／write=バッファして
    close で put（nats の sync-IO モデル＝async-write を pull できないため。backpressure 不可でメモリは best-effort）。`_NatsBase` 共通化。
  - **テスト移設:** `shoudou_storage/tests/` → 最上位 **`tests_storage/`**（`shoudou_storage`/`tests` と同階層＝src/＋tests/ と同型。
    パッケージ dir はソースのみ＝wheel にテストが入らない。`pytest tests_storage/` で実行）。S3/NATS はインメモリ fake で分割・配送ロジックを検証。
  - **結果:** `pytest tests_storage/ -W error` 緑（20）、juice `make check` 緑（221）。実 S3/minio・実 NATS 疎通は未検証（fake 担保・follow-up）。
  - **関連 commit:** 本コミット（S3/NATS streaming FileStore＋テスト移設）。

- **shoudou_storage を「2 ストア抽象 × async/sync/bridge」へ再設計（ユーザー対話で逐次決定）。** 単一 `__init__.py`
  だった shoudou_storage を、将来別ライブラリへ抽出する前提でモジュール分割し、ストア抽象を整理した。
  src からは未 import（E006 結線は保留のまま・juice 本体の挙動は不変）。テストは**パッケージ同梱**
  （`tests_storage/`＝`shoudou_storage` と同階層〔src/＋tests/ と同型〕。juice の `testpaths=["tests"]` 外＝抽出時に一緒に持ち出せる。`pytest tests_storage/` で実行）。
  - **クリーンアップ:** `create_file_store` のベタ書き `/app/data` を撤去（`local` は `local_dir` 必須化、未知 backend は
    `ValueError`）。`create_file_store`→`create_key_value_store` に改名。
  - **モジュール分割:** `async_storage`（一次実装）/ `sync_storage`（同期 IF）/ `async_to_sync_storage`（橋渡し）/
    `safe_path`（検証ラッパ）。`__init__` が再エクスポート（`__init__` 直下は stdlib のみ、重い backend は遅延 import 据え置き）。
  - **2 ストア抽象:** ① **KeyValueStore**（put/get がメイン。`iter`→`list`〔iter が一次プリミティブ・全件を名前降順 yield、
    list は `_take` で先頭 limit〕/`exists`。backends = `Local`/`S3`/`Nats…KeyValueStore`。Local は init で**絶対パス固定**
    〔`resolve()`、cd 非依存〕・put は**親ディレクトリ作成**・iter は**再帰**〔rglob、相対 posix キー〕で s3/nats のフラットキー規約に整合）。
    ② **FileStore**（`open`→`FileObject`〔read/write/close＋async CM〕。`LocalFileStore` 具象＋`KeyValueFileStore`
    アダプタ〔KVS を全体 get/put でバッファし FileStore 化＝s3/nats も同型で open 化〕）。
  - **async→sync:** ゼロ依存の自前ラッパ `AsyncToSyncKeyValueStore`（専属ループ 1 つを `run_until_complete` で駆動、
    `iter` は 1 回の実行で全件取り切って同期 yield、`close()` で `shutdown_asyncgens`→`close`）。sync IF は
    `SyncKeyValueStore`/`SyncFileStore`/`SyncFileObject`。
  - **安全パス:** `validate_safe_path`（POSIX 相対のみ許可。絶対/`..`/バックスラッシュ/NUL/空を弾く・`UnsafePathError`）＋
    同 IF を被せる `SafeKeyValueStore`/`SafeFileStore`（key/filename を検証してから委譲＝各メソッド明示定義で型も引き継ぐ）。
  - **結果:** `pytest tests_storage/ -W error` 緑、juice `make check` 緑（221、変化なし）。
  - **E006 の経緯:** 当初 E006 で registry を shoudou backing するため FileStore に `walk`/`delete` を足す案を出したが、
    **shoudou を juice 都合で拡張しない**方針（pristine 維持・抽出予定）でユーザーが却下。E006 は保留のまま、本サイクルは
    storage パッケージ自体の抽象整備に充てた。詳細は「課題メモ: E006」。
  - **関連 commit:** 本コミット（shoudou_storage 抽象の再設計）。

- **workflow にライフサイクル・フック（Helm 流 pre_deploy / post_deploy）を実装（E001）。** 前セッションが
  実装＋テストまで終えて未コミットだったものを、docs / 作業状態を整えて確定（UPDATE 工程の仕上げ）。配備の
  前後に bundle を 1 回だけ走らせる宣言 `workflows[].hooks`（`{event, bundle, input?}`）。juice は実行せず
  **成果物に焼き込む**（「ワークロードを実行しない」原則どおり、実行は基盤に委譲）。
  - `manifest.py`: `HookSpec` / `HOOK_EVENTS`(pre_deploy/post_deploy) / `_parse_hook`、`WorkflowSpec.hooks`。
    validate は event 妥当性・bundle 必須・**hook.bundle の参照存在**まで検査。
  - `apply.py`: workflow materialize に `hooks`（event/bundle/input）を round-trip。
  - `deploy.py`: 命名を `_named`（step/hook 共通。service 名衝突回避）に汎用化。**compose** は pre=one-shot を
    先頭 step が `depends_on:{condition: service_completed_successfully}` で待ち、post=末尾 step 起動後に走る
    （`_compose_hook_service`）。**k8s** は各フックを Job 化（`_k8s_hook_job`、順序は基盤委譲＝`juice.hook` ラベル）。
  - `cli/deploy.py`: build 出力に hook 数を表示。
  - tests：`test_manifest +71`（hooks パース／event・bundle 検証／参照エラー）、`test_deploy +80`
    （compose の pre 完了待ち・post 起動後、k8s Job、命名衝突回避）。
  - docs：architecture.md の workflow/deploy 節に「ライフサイクル・フック」サブ節を追記。
  - **結果:** `make check` 緑（221）。生成・宣言系のため会話 API E2E は対象外（通常スキップ条件）。
  - **関連 commit:** 本コミット（feat: workflow lifecycle hooks）。

- **（前段）storage モジュールを独立パッケージ `juice_storage` として抽出（`src/` と同列・最上位）。** ユーザー指示で
  ストレージ抽象を juice 本体から切り出し、リポジトリ最上位に `src/` と並べて配置。パッケージング方式は
  「juice の wheel に同梱」（独自 pyproject/uv workspace ではなく hatch packages に追加）を選択。
  - **新パッケージ:** `juice_storage/__init__.py`（`Storage` ABC ＋ `LocalStorage`。`src` 非依存の単独モジュール）。
    旧 `src/core/storage.py` は削除。
  - **import 差し替え:** `factory.py` / `registry.py` / `core/__init__.py` を `from juice_storage import ...` に。
    `src/core` は `Storage`/`LocalStorage` を**後方互換で再エクスポート継続**（`from src.core import LocalStorage` は不変）。
  - **packaging:** `pyproject.toml` の `[tool.hatch.build.targets.wheel] packages = ["src", "juice_storage"]`。
    最上位がそのまま import パスなので（`src` も同様）editable/同梱の双方で `import juice_storage` が解決。
  - tests：`test_storage.py` を `from juice_storage import LocalStorage` に変更（パッケージ境界を直接検証）。件数不変。
  - docs：glossary に「storage（juice_storage パッケージ）」項目（物理ストア抽象・src と同列・wheel 同梱・factory が差し込み点）。
  - **結果:** `make check` 緑（209、Python 3.14.2 / ruff 0.15.17）。`uv sync`＋実機で `uv run juice all list` rc0、
    `import juice_storage`／`src.core` 再エクスポートの同一性（`LocalStorage is juice_storage.LocalStorage`）を確認。
  - **関連 commit:** 本コミット（storage→juice_storage 抽出）。純構造変更のため会話 API E2E は対象外。

- **（前段）python_packages を実レイヤ化（PyPI 様の registry を「同列の 1 registry」として横断対象に）。** これまで
  構造のみ（README だけ・LAYERS 未登録で inert）だったのを、`config.py` の 3 箇所
  （`LAYERS["python_package"]="python_packages"` / `ENTRY_FILES["python_package"]="index.yml"` /
  `ALL_ORDER` 末尾）に登録して実レイヤ化。registry の汎用化（layer=registry）の実証。
  - **横断対象になったもの:** `juice all list`（`== python_packages ==` 見出し）／自動生成の
    `juice python_package list`（CLI は LAYERS を回して per-layer parser を作る＝コード変更不要）／
    `juice registry verify`（name=dir 検査）／`juice registry index`（メタデータ索引）。
  - **OKF 検査外:** エントリが純 YAML `index.yml`（`.md` concept document でない）なので `OKF_MD_LAYERS`
    （`ENTRY_FILES` から `.md` を自動抽出）に入らず、OKF `type` 必須の対象にならない（bundle/instance と同方針）。
  - **manifest 非対象:** `juice.yaml` のキーを持たない＝`apply` の materialize/prune 対象でない
    （langfuse の vendored workflow と同様、registry に直接置くレイヤ）。空でも `list` は rc 0（メッセージは stderr）。
  - tests（+4）：metadata〔python_package の name=dir mismatch 検出／OKF 対象外〕、index〔書き込んだ
    python_package が索引に載る〕、cli〔all list に見出し／空 list は rc 0〕。
  - docs：README（実レイヤ化を反映）、glossary（ツリー＋layer=registry 説明）、architecture.md（「registry のみの
    レイヤ＝manifest 非対象」注）。
  - **結果:** `make check` 緑（209）。実機 CLI で `python_package list`（空・rc0）・`all list`（見出し）・
    `registry verify` rc0 を確認。**同梱 python_package はまだ無い**（構造のみ。wheel/index は YAGNI で未）。
  - **関連 commit:** 本コミット（python_packages 実レイヤ化）。生成・参照系のため会話 API E2E は対象外。

- **（前段）E002 remote mcp_server 対応を実装（外部参照＝黒箱を全層に通した）。** これまで mcp_server は
  local（command で stdio 起動＝vendoring）のみだったのを、`url`（＋任意 `transport`）で外部参照する
  **remote** に対応。消費側（subagent `allow_tools` / bundle `tools[].from`）からは同じ `mcp_server`
  に見え、結線の書き方は不変（remote は server の属性で、bind の新 kind ではない＝`SUPPORTED_BIND_KINDS`
  は据え置き）。
  - `manifest.py`: `McpServerSpec` に `url` / `transport`＋`is_remote()`。`REMOTE_TRANSPORTS=
    (streamable_http, sse)`／既定 streamable_http。`_parse_mcp_server` で検証＝**command と url は排他**・
    remote transport の妥当性・url 無しで transport 単独宣言はエラー。
  - `lock.py`: `LockedServer` に url/transport を記録（`LOCK_VERSION` 1→**2**）。
  - `apply.py`: `_tool` を remote 分岐＝materialize は `transport`/`url`/`env`（command/args を持たない）。
  - `bundle.py`: `_vendor` が remote tool（url 持ち）を**黒箱として vendoring 除外**。`_agent_config` と
    生成 `graph.py` の `_connections()` が remote を `{transport, url}` 接続に（local の `{command, args}` と対）。
  - tests（+10：manifest 6／apply 1／lock 2／bundle 1）：remote parse〔既定/明示 transport〕・排他/transport 単独/
    未対応 transport のエラー・remote materialize〔command なし〕・lock 記録〔url/transport〕・bundle〔url 接続＋vendor 除外〕。
  - docs：architecture.md に「mcp_server: local と remote（E002）」節（対照表＋vendoring/agent.json/lock の差）。
  - **結果:** `make check` 緑（205、Python 3.14.2 / ruff 0.15.17）。実機 CLI で remote 入り manifest を
    `manifest validate` ok・`lock`（github エントリに url 記録）・`apply --dry-run`（tool/github＋tool/weather）・
    排他エラー（command＋url）を確認。
  - **caveat/将来:** 実接続（remote server への到達性）は未検証＝生成のみ（API トークン要・外部依存のため通常スキップ条件）。
    registry への remote 実例は未同梱（CLI list テストが実レジストリ依存のため churn を避けた。必要時に follow-up）。
    `package`/`version` による黒箱の版 pin はフィールドとして保持するが範囲解決は未（依存解決は YAGNI のまま）。
  - **関連 commit:** 本コミット（E002 remote mcp_server）。生成・参照系のため会話 API E2E は対象外。

- **（前段）vendored workflow（終端・外部スタック）を実装＋ langfuse を例として配置。** ユーザー整理「juice の本質は
  依存解決。langfuse は依存物が無いので workflows レイヤに `docker-compose.yml` を直に置けばよい（終端）」を実装。
  - `deploy.py`: `is_vendored_workflow`（registry に `docker-compose.yml` を持つか）／`write_vendored_workflow`
    （生成せず compose を `deploy/<name>/` へ passthrough、closure 空、services 数を yaml から数える）。`VENDORED_COMPOSE`。
  - CLI: `juice workflow build <name>` が vendored を検知したら manifest を読まず passthrough（`--target` は compose のみ）。
  - registry: `namespaces/default/workflows/langfuse/`（`index.md`＝frontmatter `vendored: compose`＋OKF `type: workflow`、
    `docker-compose.yml`＝langfuse 公式 v3〔web/worker+postgres+clickhouse+redis+minio〕を distill）。`mcp_weather-bot` とは別スタック。
  - tests（test_deploy 2／test_cli 1）：検知・passthrough・closure 空・CLI 終端表示。docs（architecture.md に vendored workflow 節）。
  - **結果:** `make check` 緑（191）。実機で `all list` に langfuse、`registry verify` rc0、`workflow build langfuse`＝
    「vendored … (6 services, 終端) / build targets (bundle): (none)」を確認。docker 未起動（compose は未検証＝公式を正に reconcile 要）。
  - **caveat/将来:** langfuse は registry に**手置き**（juice.yaml manifest 管理外＝apply の prune 対象でない）。manifest からの
    宣言管理、`bundle` の pluggable bundler（`image`/`compose`）は別途。
  - **関連 commit:** 本コミット（vendored workflow＋langfuse）。生成・参照系のため会話 API E2E は対象外。

- **（前段）E001 step 協調の第一歩：workflow/compose に宣言順の直列 `depends_on` を実装。** step が独立 service の
  ままだったのに「起動順」を与えた。`build_compose`（deploy.py）で 2 番目以降の service が直前の service に
  依存（先頭は持たない）。同一 bundle の連番 service（`bot`→`bot-2`→`bot-3`）も宣言順に決定的に連鎖。
  - **限定:** `depends_on` は compose の意味での**起動順**にすぎず「完了待ち」ではない。k8s（Deployment）は
    depends_on 相当が無いので**順序を持たない**（Argo 等で別途）。schedule も対象外。完了待ち・データ受け渡し・
    DAG・実起動は次段階（YAGNI）。
  - tests（test_deploy.py 4 件）：直列連鎖／単一 step は付かない／連番 service の決定的連鎖／k8s・schedule は不変。
  - docs：architecture.md の deploy 節に「直列起動順（compose depends_on）」と compose/k8s の差を明記。
  - **結果:** `make check` 緑（188）。実機で live-bots の compose に `news-bot.depends_on: [mcp_weather-bot]`、
    先頭 `mcp_weather-bot` に depends_on 無しを確認。
  - **関連 commit:** 本コミット（E001 compose depends_on）。生成のみのため会話 API E2E は対象外。

- **（前段）`mcp_bundled` の語を全廃→`bundle`／最上位を `namespaces/` へ／サンプルを `mcp_weather-bot` へ（3 段）。**
  ユーザー整理「layer 自体が registry（tools/bundles/将来 datasets・python_packages が同列）」「mcp_bundled は残さない」
  「weather-bot→mcp_weather-bot で "mcp" をパッケージ名へ」を反映。
  - **(1) 構造:** 物理レイアウトを `registries/namespaces/<ns>/<layer>` → **`namespaces/<ns>/<layer>`** に。
    `registries/` ラッパ廃止、`DEFAULT_BUCKET='.'`、`namespace_root()` で bucket='.'/'' を畳む。ruff exclude も追従。
  - **(2) `mcp_bundled` 全廃:** レイヤキー/CLI/manifest を `bundle` に統一。manifest の **list キーは複数形 `bundles:`**
    （他レイヤと同規約）、**参照は単数 `bundle:`**（instance/step）。`McpBundledSpec`→`BundleSpec`、`_parse_mcp_bundled`→
    `_parse_bundle`、`kind: mcp_bundled`→`kind: bundle`、CLI `juice bundle ...`、Makefile も。dir 名は複数形 `bundles` のまま
    （`LAYERS["bundle"]="bundles"`）。src/tests/registries/docs/Makefile を横断更新（subagent で機械実施、`make check` で検証）。
  - **(3) サンプル改名:** bundle パッケージ `weather-bot`→**`mcp_weather-bot`**（dir・bundle.yml・image・instance/workflow/
    schedule の参照・vendor/agent.json・Makefile BUNDLE_NAME・全テスト）。instance `tokyo-weather-bot`／tool `weather`／
    skill `report-weather`／workflow `weather-service` は非対象（別物）。
  - **(4) python_packages:** glossary に「layer=registry／PyPI 様の同列レジストリ」を明記＋ `namespaces/default/python_packages/README.md`
    を置く（**構造のみ・未実装**。LAYERS 未登録で verify/list の走査外＝inert）。
  - **結果:** `make check` 緑（184）。`grep mcp_bundled`／`weather-bot`(bundle) はコード/registries/docs でゼロ。実機で
    `all list`（bundles に mcp_weather-bot）／`registry verify` rc0／`manifest validate`（bundles:/bundle:）／docker context が
    `namespaces/default/bundles/mcp_weather-bot/vendor` を確認。
  - **関連 commit:** 3 段（structural / mcp_bundled→bundle / weather-bot→mcp_weather-bot＋python_packages）。

- **（前段）registry の物理レイアウトを K8s 規約へ整列（namespaces 容器 ＋ mcp_bundled→bundles）。** ユーザー指摘で
  「default が namespace なら容器は `namespaces/` であるべき（K8s の `/namespaces/<ns>/` と同型）」「`mcp_bundled` だけ
  単数形ディレクトリで不整合」を解消。物理パスを **`registries/<ns>/<layer>/<name>` → `registries/namespaces/<ns>/<layer>/<name>`**、
  mcp_bundled レイヤの**ディレクトリ名のみ** `bundles` に変更（レイヤキー＝CLI コマンド・manifest の `mcp_bundled` は不変）。
  - `config.py`: 定数 `NAMESPACE_CONTAINER = "namespaces"` 追加、`LAYERS["mcp_bundled"]` を `"bundles"` に。
  - `factory.py` / `registry.py`: storage root と `location()` に namespaces 容器を挿入。
  - `bundle.py`: 表示用パス接頭辞 `_BUNDLE_DIR = LAYERS["mcp_bundled"]`（＝bundles）で vendored/generated/spec を生成（dir 名の単一ソース化）。
  - registries: `git mv` で `registries/default/*` → `registries/namespaces/default/*`、`mcp_bundled/` → `bundles/`。
  - tests/docs: 物理パスを組む箇所（conftest・test_bundle/registry/index/metadata/okf_cache）を namespaces/bundles に更新。
    `all list` 見出しは registry dir 名（複数形）なので `== bundles ==`。glossary にツリー＋命名規約、build.md のレイアウト図を更新。
  - **結果:** `make check` 緑（184 ケース）。実機で `all list`／`registry verify` rc0／`okf-cache`／docker context が
    `registries/namespaces/default/bundles/weather-bot/vendor` を指すのを確認。
- **関連 commit:** 本コミット（registry レイアウトを K8s 規約へ整列）。

- **（前段）「catalog」用語の整理＋ OKF ビューを `okf_catalog_cache` へ改名。** ユーザーとの用語整理で、コアの語
  **catalog** は**成果物の構造インベントリ**（レイヤー1=namespace / レイヤー2=kind / 成果物ディレクトリ=主役。
  K8s の namespace×kind×name 同型。閲覧口は `juice all list`）に予約し、前サイクルで追加した OKF 横断ビューが
  その語を squat していたのを解消した。OKF は「正式管理対象でなく不安定・主に AI が参照する周辺機能」と位置づけ、
  内部名 `okf_catalog_cache` で区別する（OKF は逆に収集物を "catalog" と呼ぶ＝`knowledge-catalog`。語の向きが逆な点に注意）。
  - **改名:** `src/core/catalog.py` → `okf_catalog_cache.py`（`build_catalog`/`filter_catalog` →
    `build_okf_catalog_cache`/`filter_okf_catalog_cache`、定数 `CATALOG_FIELDS` → `OKF_CACHE_FIELDS`）。
    `Juice.catalog()` → `Juice.okf_catalog_cache()`。CLI `juice catalog` → **`juice okf-cache`**（`_cmd_okf_cache`）。
  - **docs:** [docs/glossary.md](docs/glossary.md) を新設（catalog / registry / index / okf_catalog_cache の定義と OKF 対応）。
    architecture.md の当該節を okf_catalog_cache へ更新＋glossary 参照。
  - **tests:** `test_catalog.py` → `test_okf_catalog_cache.py`（シンボル更新）、`test_cli.py` を `okf-cache` に更新。
  - 機能・出力・射影スキーマは不変（純粋な改名＋用語確定）。index（一般メタデータキャッシュ）は名称据え置き。
- **結果:** `make check` 緑（計 184 ケース）。実機で `juice okf-cache`／`--tag weather`、旧 `juice catalog` は無効選択を確認。
- **関連 commit:** 本コミット（catalog 用語整理＋okf_catalog_cache 改名）。
  ※ 宣言・参照系のため会話 API の E2E 確認は対象外（通常スキップ条件）。

- **（前段）OKF メタデータの横断ビューを実装。** index 集約を OKF 標準スキーマ（identity＋type＋推奨フィールド
  title/description/tags/resource/timestamp）へ射影する派生ビュー＋ registries の weather/report-weather に
  description/tags の実例を追加。※この時点ではコマンド名が `juice catalog` で、上記サイクルで `okf-cache` へ改名。

- **（前段）依存の実ビルド起動（`build --build-deps`）を実装。** 「宣言→依存物を遡ってビルドする」の完成形。
  - CLI: `juice workflow/schedule build <name> --build-deps`（既定 off）。`_build_deps` が依存閉包の mcp_bundled を
    宣言順に `Juice.bundle`（vendoring）→ `Juice.build`（docker、`_exec`）まで起動し rc 集約。docker 不在は `_exec` が 127。
  - tests: `test_cli.py` に build-deps 既定 off＋`--build-deps` 無しで生成のみ（docker 非依存）2 ケース。
    実 docker ビルド／bundle の副作用は実機専用で CI 非実行（既存 build/run と同方針）。
  - docs: architecture.md の closure 節に `--build-deps` を追記。
- **結果:** `make check` 緑（計 175 ケース）。`juice workflow build -h` に `--build-deps` 表示を確認。
- **関連 commit:** 本コミット（依存の実ビルド起動）。
  ※ `--build-deps` 実行は bundle が registry を書き換える＆docker 要のため E2E 実行はスキップ（plumbing は単体で検証）。

- **（前段）schedule を registry レイヤに昇格＋「宣言→依存物を遡る」解決を実装。** ユーザー指示：schedule の実適用
  （cron 実発火）は未実装でよい、「宣言すると依存物を遡ってビルドする感じ」まで。
  - `config.py`: `LAYERS`/`ENTRY_FILES`/`ALL_ORDER` に `schedule`（`schedules/<name>/index.md`）を追加。
  - `apply.py`: `_schedule` materialize（frontmatter kind/name/type/schedule/steps、OKF `type: schedule`）＋
    `_LAYER_ORDER` 末尾に追加。→ `juice apply` が schedule を冪等 materialize。verify/index/`schedule list` は
    LAYERS/ALL_ORDER 経由で自動横断。
  - `deploy.py`: `dependency_closure(manifest, steps)` を追加。schedule/workflow の steps→mcp_bundled→
    subagent/skill/tool を遡って解決（build 対象＝mcp_bundled）。`write_*deployment` の結果に `closure` を同梱し、
    CLI `juice workflow/schedule build` が「build targets＋← deps」を表示。**実 docker ビルド起動はしない**。
  - CLI: schedule が LAYERS 入りしたため標準 `schedule list` が有効化。`build` は workflow/schedule 共通ブロックに統合。
  - registries/default に `schedules/morning-brief/index.md`（cron＋steps）を追加＝scheduled 実例を復活。
  - tests: apply の schedule materialize＋冪等 2、deploy の closure 2、metadata の OKF_MD_LAYERS 更新。
- **結果:** `make check` 緑（計 173 ケース）。実機で `registry verify` rc 0、`schedule list`／`all list` に
  morning-brief、`schedule build --target k8s` が CronJob 生成＋依存閉包（weather-bot ← forecaster/report-weather/weather）表示を確認。
- **docs:** architecture.md に apply の依存順へ schedule 追加＋「宣言から依存を遡る（dependency_closure）」節、schedule 節を materialize 済みに更新。
- **関連 commit:** 本コミット（schedule レイヤ昇格＋依存閉包）。
  ※ E2E 確認（会話 API）は宣言・生成系のため対象外（通常スキップ条件）。

- **（前段）スケジューラのターゲットを分類し E005 として課題化（概念のみ・未実装）。** ユーザーとの整理で
  「何を定期実行するか」を 2 種に分けた：**(A) ワークロード・ジョブ**（= 現 `schedules:`、k8s CronJob／
  docker one-shot、実装済）と **(B) パイプライン・トリガ**（= `triggers:`、juice の配備操作を定期実行）。
  (B) は **juice 内蔵スケジューラ（デーモン＝コントロールプレーン）** で実現する構想（ArgoCD の定期 sync と同型、
  「ワークロードは実行しない」原則は (A) 適用で矛盾なし）。docs/architecture.md に分類を追記、PROJECT.md に
  E005 行＋課題メモ。**コード変更なし**（`make check` 緑のまま）。関連 commit：本コミット。

- **（同日）README/docs の概念・位置づけを再整理。** ユーザーとの認識合わせで製品像を確定：juice は
  **AI エージェントのための宣言的パッケージマネージャー＋デリバリ・パイプライン**（依存を宣言・解決・版管理する
  PM の口と、配備まで運ぶパイプラインの口は同一物の両端）。juice は実行せず実行基盤に成果物を渡す。**現状は AI
  特化（リファレンス＝チャット）、機構は組織内資産〔dataset/model/知識〕へ一般化しうる＝構想**として明示。
  「workflow」はレイヤ名に温存し、製品呼称には使わない（衝突回避）。
  - `README.md` を全面改稿（位置づけ→パイプライン図→現状の使い方→ビジョン〔汎用化〕→リンク）。
  - `docs/architecture.md` 冒頭に位置づけを追記。`PROJECT.md` プロジェクト概要の一行も同方針に更新。
  - 書き出し方針：現状(AI)主役＋汎用は構想として 1 節（ユーザー選択）。
- **結果:** `make check` 緑（169 ケース、コード変更なし＝docs のみ）。
- **関連 commit:** 本コミット（docs 位置づけ再整理）。

- **（前サイクル）workflow と schedule の概念分離をリファクタ。** ユーザーとの設計対話で「`schedule` は workflow の持ち物では
  なく scheduler（いつ動かすか）の持ち物」「workflow は常駐サービス群」と確定。k8s の Deployment↔CronJob、
  Argo の WorkflowTemplate↔CronWorkflow と同型の整理。第三歩の「`schedule` 有無で Deployment/CronJob 分岐」
  という歪みを解消した。
  - `manifest.py`: `WorkflowSpec` から `schedule` を撤去（常駐の定義に純化）。新 `ScheduleSpec`（name /
    `schedule`(cron, 必須) / steps）＋ `Manifest.schedules` ＋ `_parse_schedule`。step パーサを `_parse_step`
    に汎用化し workflow/schedule で共用。validate に schedules の重複・参照チェックを追加。
  - `apply.py`: `_workflow` は schedule を出さない（workflow md = kind/name/type/steps）。
  - `deploy.py`: **workflow → 常駐**（compose `restart: unless-stopped` / k8s Deployment、CronJob 分岐は廃止）。
    **schedule → 定期実行**（k8s CronJob ／ compose は cron 非対応なので `restart: "no"`＋`profiles: [scheduled]`
    の one-shot、cron は label）。`build_schedule_compose` / `build_schedule_k8s` / `write_schedule_deployment` /
    `find_schedule` を追加。`_WF_TARGETS` / `_SCHED_TARGETS` に分離。
  - CLI: `juice schedule build <name> [-f] [-o] [--target]` を新設（workflow build と対）。
  - registries: `workflows/morning-brief`（schedule 付き）→ `workflows/weather-service`（常駐、schedule なし）に
    リネーム＝概念に整合。schedule の registry レイヤ化は別サイクル。
  - tests: test_deploy を workflow(常駐)/schedule(CronJob・one-shot) に再編、test_manifest に schedule パース＋
    エラー 2 ケース、test_apply の workflow を schedule なしに更新。
- **結果:** `make check` 緑（計 169 ケース、Python 3.14.2 / ruff 0.15.17）。tmp の juice.yaml で
  workflow→compose 常駐 service、schedule→k8s CronJob／compose one-shot を実機確認。`juice registry verify` rc 0。
- **docs:** architecture.md の概念対応表に schedule 行を追加、workflow 節を「定義(workflow)とトリガ(schedule)の分離」
  ＋ 4 通りの生成（workflow/schedule × compose/k8s）に書き換え。
- **関連 commit:** 本コミット（workflow/schedule 概念分離）。
  ※ E2E 確認（会話 API）は生成系機能のため対象外（通常スキップ条件）。

### 作業中（In Progress / Next） — 次サイクルの優先度を着手時に確認（候補を提示）

**状況:** E001 の「生成のみ」系（定義/トリガ分離・compose/k8s 生成・schedule レイヤ昇格・依存閉包・
`--build-deps`・compose `depends_on`・**ライフサイクル・フック〔pre/post_deploy〕**）、**E002 remote mcp_server**
（外部参照＝黒箱の全層対応）、**python_packages の実レイヤ化**（layer=registry の横断対応）は実装済。
ここから先は **(a) E001 の残り
（実起動・スケジューラ稼働・完了待ち/DAG）＝juice の「実行しない」原則に触れる大物**、または **(b) 別バックログ**
に分岐する。**着手時にユーザーへ優先度を確認**してから 1 つ選ぶ。

**新規メモ（ユーザー追加・要記憶）:** `shoudou_storage` パッケージを最上位に追加し、依存を
dependency-group `shoudou-storage` に分離＋`uv run` 自動同期（default-groups）＋wheel 同梱まで設定済み
（**足場のみ・src 未結線**）。将来 **juice のストレージ機能を shoudou_storage に結合**したい（→ **E006**）。

**候補（上から推奨順・要確認）:**
1. **E003 skill ライブラリ** — 再利用可能な skill 集。
2. **python_packages の中身（follow-up）** — 実レイヤ化は済。次は wheel/sdist の実格納と PEP 503 風の
   simple index 提供、`apply`/manifest からの宣言管理（今は registry 直置きのみ）。必要になってから。
3. **E001 残り（大物）** — 実起動（`up`/`kubectl apply`）・スケジューラ稼働・step 完了待ち/データ受け渡し/DAG。
   「juice はワークロードを実行しない」原則との線引き（生成 vs 実行）を要設計。
4. **E006 shoudou_storage 統合（保留中）** — factory から FileStore を使う adapter は方針対立で保留。
   **制約:** shoudou_storage を juice 都合で拡張しない（pristine 維持・別ライブラリ抽出予定）。再開するなら
   **(a) adapter のみ**で現状の `save/get/list/exists` だけから階層 Storage を構成（list_dirs/再帰列挙/再帰削除は
   adapter 側の補助 index で補う）、または **(b) doc-first** でインターフェースギャップ（同期↔非同期・階層↔フラット・
   delete/prefix 列挙の欠落）と方針を先に文書化してから着手。詳細は「課題メモ: E006」。

**完了条件（共通）:** 選んだタスクの実装＋tests＋docs。`make check` 緑。可能なら E2E（会話 API）確認。

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

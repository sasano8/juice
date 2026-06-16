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
（tool / skill / subagent を `mcp_bundled` 化）を同梱。現状は AI 特化、機構は組織内資産（dataset / model /
知識）へ一般化しうる（構想）。

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
- [x] エラーメッセージ（Q001。ファイルパス＋ヒント＋YAML 行情報、_fail で集約）
- [x] architecture.md に宣言系レイヤを反映（Q003。概念モデル↔juice.yaml の 2 軸＋ライフサイクル）
- [x] registry の健全性検査（E004。name=dir＋OKF 適合＋メタデータ索引 drift。`juice registry verify`/`index`）
- [~] workflow を宣言パイプラインに載せる（E001 第一歩。manifest/validate/apply materialize＋plan・drift 対応）
- [~] workflow / schedule のデプロイ成果物生成（E001。workflow=常駐〔compose service／k8s Deployment〕、schedule=定期実行のワークロード・ジョブ〔k8s CronJob／compose one-shot〕。生成のみ）
- [x] schedule を registry レイヤに昇格（E001。`apply` で materialize＋index／verify／list 横断）
- [x] 宣言→依存物を遡る解決（E001。`deploy.dependency_closure`。build 時に依存閉包＝build 対象を表示）
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
| E001 | workflow 実装 | 🚧一部完了 | 定義(workflow=常駐)とトリガ(schedule=定期実行)を分離。宣言パイプライン＋デプロイ成果物生成（compose＋k8s、生成のみ）＋schedule の registry レイヤ昇格＋依存閉包解決（`deploy.dependency_closure`）は実装済。残りは依存の実 docker ビルド起動・実起動(`up`/`kubectl apply`)・step 協調 |
| E002 | remote mcp_server 対応 | 未着手 | 外部サーバーの参照 |
| E003 | skill ライブラリ | 未着手 | 再利用可能な skill 集 |
| E004 | OKF を registries の md に自動適用 | ✅完了 | name=dir 検証＋OKF 適合（`type`）検証（`src/core/metadata.py`）＋メタデータインデックス生成・drift 検出（`src/core/index.py`）。`juice registry verify`／`index`。下記「課題メモ」参照（任意の follow-up あり） |
| E005 | triggers（juice 内蔵スケジューラ） | 構想・未着手 | コントロールプレーンの定期トリガ。下記「課題メモ: E005」参照 |

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
  `kind`（juice のレイヤ分類）は後方互換のため併記。純 YAML マニフェスト（mcp_bundled/instance、apiVersion/kind ＝
  k8s 流儀）は OKF の `.md` concept document ではないため対象外。
- `metadata.py` の `verify_okf`（非空 `type` を検証、報告のみ・自動修正なし）＋ `juice registry verify` に相乗り
  （name=dir・OKF 適合・索引 drift の 3 点を束ねた「registry の健全性」検査）。apply の materialize（C003）も `type` を生成。
**任意の follow-up（YAGNI で未着手）:** ①OKF 推奨フィールドの充足度チェック（description 等）。②OKF 予約名
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

### 直前の作業（Just Done） — 最終更新: 2026-06-16

- **schedule を registry レイヤに昇格＋「宣言→依存物を遡る」解決を実装。** ユーザー指示：schedule の実適用
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

### 作業中（In Progress / Next） — E001: 依存の実ビルド起動（`build --build-deps` で closure を bundle→build）

**概要（ゴール）:** 「宣言 → 依存物を遡る」は `dependency_closure` で**解決・表示**まで実装した。次は遡った
**build 対象（mcp_bundled）を実際に bundle→build まで起動**する一手を足す（ユーザーの「遡ってビルドする」の完成）。
`juice workflow/schedule build <name> --build-deps` で、closure の各 mcp_bundled に対し既存の `bundle`→`build`
（docker）を順に実行する。docker 実行は既存 `_exec`（コマンド文字列を実行）に委譲。

**タスク（チェックリスト）:**
- [ ] `--build-deps` フラグを workflow/schedule build に追加（既定 off）。
- [ ] closure の `mcp_bundled` を順に `Juice.bundle(name)`→`Juice.build(name)` のコマンドへ。`_exec` で実行（rc 集約）。
- [ ] docker 不在時は既存どおり rc 127 ＋メッセージ（`_exec` の挙動）。デプロイ成果物生成自体は先に済ます。
- [ ] tests（`--build-deps` でビルドコマンド列が closure 順に組まれること。docker 実行は command 文字列で検証＝既存 build テスト流儀）。
- [ ] docs（build に依存ビルド起動の一手を追記）。

**完了条件:** `juice workflow/schedule build <name> --build-deps` が closure の mcp_bundled を bundle→build まで
起動できる（docker があれば実ビルド、無ければ 127）。既定 off。`make check` 緑。

**留意点:** docker 実行はテスト不可なのでコマンド文字列レベルで検証（既存 `test_bundle`/build 流儀）。step 協調
（順序・データ受け渡し）・実起動（`up`/`kubectl apply`）・E005 triggers は引き続き別サイクル（YAGNI）。
代替候補：step 協調（compose `depends_on` 直列）に進んでもよい。着手時に優先度を確認する。

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

# アーキテクチャ（レイヤ関係）

> juice の全体像を **2 軸** で捉える。
> 1. **概念モデル** … mcp_server / mcp_bundled / subagent / skill / tool の関係（本書前半）。
> 2. **宣言的ワークスペース** … その概念モデルを `juice.yaml` 1 ファイルで宣言し、
>    `lock → plan → apply` で registries へ具現化するライフサイクル（本書「[宣言的ワークスペース](#宣言的ワークスペースjuiceyaml)」節）。
>
> 同じレイヤ群を「関係（概念）」と「宣言（運用）」の別表現で見ているだけで、両者は対応する。
> 実装の使い方は [README](../README.md)、ビルド手順は [build.md](build.md) を参照。
> 旧設計の宣言案 [workspace.md](workspace.md)（SUPERSEDED）が `juice.yaml` 系の出発点で、
> 現行で実装された範囲を本書「宣言的ワークスペース」節に反映する。

`mcp_bundled (deployable) = mcp_server`。`mcp_server`（公開インターフェース）には
**remote**（外部参照）と **bundled**（自作＝同梱）の 2 実現がある。`mcp_bundled` は依存一式を
vendoring・ビルドし、変数の既定値・secret 参照を抱えた、自己完結したデプロイ単位。

## レイヤ間の関係

始発点は **公開インターフェースである `mcp_server`**。これには **remote**（外部・黒箱）と
**bundled = `mcp_bundled`**（自作・同梱）の 2 種類がある。bundled は subagent / skill / tool を
所持する。そして **その tool を公開しているのも、また 1 つの mcp_server**（remote or 別の
mcp_bundled）。だから tool をたどると先頭の mcp_server に戻る＝**再帰**（底は remote）。

```mermaid
flowchart TB
    MCP{{"mcp_server<br/>（公開インターフェース）"}}
    MCP -->|"remote"| REMOTE["remote mcp_server<br/>（外部・黒箱）"]
    MCP -->|"bundled"| BND["mcp_bundled<br/>（自作・同梱 = deployable）"]

    BND -->|"所持 1"| SA["subagent"]
    BND -->|"所持 N"| SK["skill"]
    BND -->|"所持 N"| TL["tool"]
    SK -.->|"requires N（前提 tool）"| TL
    SA -.->|"allow N（許可リスト）"| TL
    TL -.->|"この tool を公開する mcp_server（再帰）"| MCP
```

> **包含制約:** `skill.requires ⊆ subagent.allow ⊆ mcp_bundled.provides`
> （手順が呼ぶ tool ⊆ 許可された tool ⊆ 実体が提供される tool）。

| 関係 | 多重度 | 意味 |
|------|--------|------|
| mcp_server → 実体 | 1 : 1 | remote（外部）か bundled（= mcp_bundled）のいずれか |
| mcp_bundled → subagent | **1 : 1** | 脳は 1 つ |
| mcp_bundled → skill | **1 : N** | 手順を複数所持 |
| mcp_bundled → tool | **1 : N** | tool を複数所持 |
| skill → tool | **N : M** | 手順が呼ぶ前提 tool（requires）。`skill.requires ⊆ subagent.allow` |
| subagent → tool | **1 : N** | 使ってよい tool の許可リスト |
| tool → mcp_server | N : 1 | その tool を公開している mcp_server（remote or 別の mcp_bundled）＝再帰 |

- **mcp_server = 公開インターフェース。** remote でも bundled でも、消費側からは同一に見える。
- **remote** … 既存の MCP server を黒箱として参照（実体は内包せず `package`/`version` で参照）。
- **bundled（mcp_bundled）** … subagent / skill は内包（vendoring）、tool は別の mcp_server が公開（再帰）。

## 関係の 2 レベル（参照 vs バンドル）

混同しやすいので分けて捉える。

| 関係 | レベル | 多重度 | 目的 |
|------|--------|--------|------|
| skill / mcp_server を複数 mcp_bundled が使う | **参照**（authoring） | **N : M** | 再利用・共有 |
| 1 mcp_bundled が抱える subagent / skill / tool | **バンドル**（build） | **1 : N（包含）** | **deployable 化（vendoring）** |

→ 参照レベルでは共有（N:M）だが、**bundle 時に包含ツリー（1:N）へ畳んで vendoring** し、
mcp_bundled を自己完結＝ deployable な mcp_server にする。

## bundle/build/run（実装の対応）

現在の実装では、宣言（`bundle.yml`）→ `bundle`（vendoring ＋ LangGraph 一式生成）→ `build`
（docker イメージ）→ `run`（api / ui / mcp_server）という流れ。`run` は LangGraph で LLM と
MCP server を連携した会話エージェントを起動する。詳細は [build.md](build.md)。

## 宣言的ワークスペース（juice.yaml）

上の概念モデル（mcp_server / subagent / skill / tool / mcp_bundled）を、`bundle.yml` のように
1 つの mcp_bundled 単位ではなく、**全レイヤを 1 ファイル `juice.yaml` で宣言**する軸。Kubernetes と
同じく **desired state を宣言 → `apply` で reconcile** する考え方で、`juice.yaml` が唯一の正
（source of truth）。`registries/` は手で書く一次情報ではなく、apply の**出力先**（生成物）。

```
juice.yaml ──lock──▶ juice.lock（解決＋manifestDigest）──plan──▶ 差分 ──apply──▶ registries/（冪等 reconcile＋prune）
```

| 段階 | コマンド | 何をする | 実装 |
|------|----------|----------|------|
| 解決 | `juice lock`     | manifest を解決し版/digest と `manifestDigest` を冪等に pin | `src/core/lock.py`（C002） |
| 差分 | `juice plan`     | apply の dry-run。registries に与える変更だけ表示          | apply の dry-run 昇格（C005） |
| 反映 | `juice apply`    | 依存順に registries へ materialize、宣言外は prune（冪等）  | `src/core/apply.py`（C003） |
| 検証 | `juice manifest validate` | 構造・相互参照・version 制約を検証                 | `src/core/manifest.py`（C001/C006） |

`apply` は **依存順（mcp_server → skill / subagent → mcp_bundled → instance → workflow）** に
下層から reconcile する（概念モデルの「下位層に依存」と同じ向き）。manifest パーサ（manifest.py）は
registry / storage に依存しない独立モジュールで、層の分離を保つ。

### 概念モデルと宣言の対応

`juice.yaml` の各キーは、前半の概念モデルのレイヤに 1:1 で対応する（**同じレイヤの別表現**）。

| 概念モデル | juice.yaml のキー | 補足 |
|------------|-------------------|------|
| mcp_server（公開インターフェース） | `mcp_servers:` | tool の提供元。remote / bundled の両実現 |
| subagent | `subagents:` | 脳（1 mcp_bundled に 1 つ） |
| skill    | `skills:`    | 手順 |
| tool     | mcp_server の `tools:` ＋ mcp_bundled の `tools[].from` | 公開は mcp_server、結線は from |
| mcp_bundled（deployable） | `mcp_bundled:` | subagent + skill + tool を結線 |
| instance（実体化） | `instances:` | 変数既定値・secret 参照を与えた具象（workflow 協調の単位） |
| workflow（常駐の協調） | `workflows:` | `steps[].mcp_bundled` を**常駐**させる定義（時間非依存）。`schedule` は持たない |
| schedule（定期実行） | `schedules:` | `schedule`（cron）＋ `steps[]`。**いつ動かすか**を持つトリガ（scheduler の責務） |

### version / 制約 / drift（再現性の補助線）

- **version（C004）** … 各パッケージ Spec に任意の SemVer を付与（`src/core/semver.py`、外部依存なし）。
  lock は mcp_server の `version` を記録し `manifestDigest` に反映する。
- **制約参照（C006）** … tool 束縛の `from: mcp_server:weather@>=1.0.0` を validate で充足チェック
  （`satisfies`）。`@` 無しは従来どおり（後方互換）。範囲マッチ・複数版共存の依存解決はまだ持たない。
- **lock drift（C005）** … apply は `juice.lock` の `manifestDigest` と spec を照合し drift を検出
  （既定は警告、`--frozen` でエラー、`--require-lock` で lock 不在をエラー）。
  これは「生成物を焼かず spec から再生成し、整合性は digest で担保する」設計原則の実装。
- **registry の健全性（E004）** … `juice registry verify` が registries の 3 点を検査する
  （`src/core/metadata.py` / `index.py`）。(1) **name=dir** … メタデータの `name` がディレクトリ名と
  一致するか。(2) **OKF 適合** … `.md` の concept document（tool / skill / subagent / workflow）が
  [OKF（Open Knowledge Format）](https://github.com/GoogleCloudPlatform/knowledge-catalog) 必須の
  非空 `type` を持つか。`type` は OKF 標準の concept type（tool は `mcp-server`）、`kind` は juice の
  レイヤ分類で併記する。純 YAML マニフェスト（mcp_bundled / instance）は OKF の `.md` ではないため対象外。
  (3) **index drift** … メタデータ索引（`juice.index.yml`、生成物）が registry と一致するか（digest 照合）。
  いずれも**検出して報告するだけ**で自動修正はしない（コピー流用か移動かを機械判断できないため人間に委ねる）。

> bundle.yml ベースの現行パイプライン（[build.md](build.md)）と juice.yaml ベースの宣言系は
> **別系統**。前者は 1 mcp_bundled を deployable にする手順、後者はワークスペース全体の desired state を
> 宣言・収束させる軸。詳細・未決の論点は [workspace.md](workspace.md)（SUPERSEDED だが宣言設計の出発点）。

## workflow（実行・協調レイヤ：別軸）

mcp_bundled の関係図とは**別軸**（こちらは実行時の協調）。**instance = mcp_bundled を実体化
したもの**（image → container の container 相当）。**1 つの workflow が複数の instance を協調
動作**させる。**workflow 同士は協調しない**（必要ならさらに上位レイヤの話。別途検討）。

```mermaid
flowchart TB
    WF{{"workflow（中心の 1 つ）"}}
    IN1["instance A"]
    IN2["instance B"]
    BND1["mcp_bundled X"]
    BND2["mcp_bundled Y"]

    WF -->|"協調 1:N"| IN1
    WF -->|"協調 1:N"| IN2
    IN1 -->|"実体化 N:1"| BND1
    IN2 -->|"実体化 N:1"| BND2
    WF -. "協調しない（上位レイヤ・別途検討）" .-> WF2{{"別の workflow"}}
```

| 関係 | 多重度 | 意味 |
|------|--------|------|
| workflow → instance | **1 : N** | 複数 instance を協調動作させる |
| instance → mcp_bundled | **N : 1** | mcp_bundled を実体化したもの（1 bundled → 複数 instance） |
| workflow ↔ workflow | — | 協調しない（上位レイヤ。別途検討） |

> **image / container 類比:** mcp_bundled = image（deployable 成果物）、instance = container（実体）。
> workflow はその container 群を協調させる実行レイヤ。

> **定義とトリガの分離（重要）:** 「何を動かすか（workflow）」と「いつ動かすか（schedule）」を分ける。
> k8s の Deployment↔CronJob、Argo の WorkflowTemplate↔CronWorkflow と同型。`schedule` は workflow の
> 持ち物ではなく、**scheduler の持ち物＝別概念 `schedules:`**（`ScheduleSpec`）。
> - **workflow**（`workflows:` / `WorkflowSpec`）… 複数 mcp_bundled を**常駐**させる定義（時間非依存）。
>   `apply` が `workflows/<name>/index.md`（frontmatter kind/name/type/steps）へ materialize。
> - **schedule**（`schedules:` / `ScheduleSpec`）… `schedule`（cron）＋ steps で**定期実行**を宣言するトリガ。
>   （registry レイヤ化＝apply materialize は別サイクル。現状は manifest＋deploy 生成のみ）
>
> **実行モデル（E001 第二〜四歩）:** juice は **実行しない**。宣言から実行基盤が食える**デプロイ成果物を生成**
> する（`src/core/deploy.py` / CLI `juice workflow build` / `juice schedule build`）。常駐・協調・監視・定期実行は
> 外部基盤（compose / k8s＋ArgoCD / 外部 cron）に委譲する。**target は pluggable**（`compose` / `k8s`）：
> - **workflow → compose**：`deploy/<name>/docker-compose.yml`。各 step の image（規約 `juice/<name>[:version]`）を
>   長期常駐 service（`restart: unless-stopped`）に。`input`→env、label `juice.workflow`。
> - **workflow → k8s**：`manifests.yaml`（multi-doc）。各 step を **Deployment**（replicas:1）に。
> - **schedule → k8s**：各 step を **CronJob**（`schedule` を cron に）。
> - **schedule → compose**：compose に cron は無いので自動起動しない one-shot service（`restart: "no"`＋
>   `profiles: [scheduled]`、cron は label）。外部 cron が `docker compose run` で起動する想定。
>
> いずれも **生成のみ**。実起動（`up`/`kubectl apply`）・スケジューラ稼働・step 協調（順序・データ受け渡し）は
> 次段階（YAGNI）。現状 step は独立 service / Deployment / CronJob のまま。

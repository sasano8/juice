# app_mcp_manager

AI エージェントのための「パッケージマネージャー」。

ツール・スキル・エージェント・ワークフローを、それぞれ独立した **パッケージ** として
宣言・バージョン管理・配布・実行できるようにすることを目的とする。
コンテナにおける「イメージ（テンプレート）」と「コンテナ（具象）」の関係を、
AI エージェントの世界に持ち込む。

---

## 中核概念

本プロジェクトが管理するパッケージは 5 種。依存方向は下から上へ積み上がる。

```
workflow          … 複数の actor を束ねる実行スケジューラ
   └─ actor       … subagent / skill / tool を結線・具象化したファサード（実行可能エージェント）
        ├─ subagent … model + system prompt + tool 許可リスト（標準・可搬な「脳」）
        ├─ skill    … ある関心を実行する「手順」（prompt を内包する）
        └─ tool     … 外部システムと連携する具体的な実装
```

| 概念 | 定義 | コンテナ類比 |
|------|------|------------|
| **tool** | 外部システムなどと連携する具体的な実装（capability） | ライブラリ／バイナリ依存 |
| **skill** | ある関心を実行する手順。指示文（prompt）はこの中に含める | playbook |
| **subagent** | model + system prompt + tool の許可リストを宣言した、標準・可搬な「脳」テンプレート | ベースイメージ |
| **actor** | subagent / skill / tool を結線し、単一の実行可能エージェントとして見せる **ファサード（合成物）テンプレート** | イメージ＋起動設定 |
| **workflow** | 複数の actor を束ねる実行スケジューラ | docker-compose / DAG |

### tool は subagent と actor の両方に現れるが役割が違う

`tool` は 2 層に出てくるが、責務が分かれているため衝突しない。

| 層 | tool に対する責務 |
|----|------------------|
| **subagent** | 「**何を使ってよいか**」= 許可リスト（capability / 権限の宣言）。標準フォーマットのまま |
| **actor** | 「**実体を渡し、起動可能にする**」= 提供と結線（facade） |

例: subagent は「github を使ってよい」と宣言するだけ。actor が「これが github の MCP server」と実体を結線する。

### テンプレート と 具象（instance）

全パッケージは可搬な **テンプレート**。これに env / secret（API キー等）を注入して
起動可能にした 1 個体が **instance（具象）**。コンテナの「イメージ ↔ 起動済みコンテナ」に等しい。

- **テンプレート** … `actors/` 等。依存を宣言した雛形。可搬・再利用可能。
- **instance** … `instances/`。テンプレート（主に actor）に具象値を注入した実個体。`docker ps` で並ぶイメージ。

具象化は起動ごとに何度でも行える（image → container 型）。
**具象化情報（secret 注入）はテンプレートではなく instance が持つ**。

---

## ディレクトリ構成

```
.
├── registries/        … 管理対象パッケージの置き場（= registry 本体）
│   ├── tools/         …   tool テンプレート（MCP server 単位）
│   ├── skills/        …   skill テンプレート（prompt を内包）
│   ├── subagents/     …   subagent テンプレート（標準・可搬な「脳」）
│   ├── actors/        …   actor テンプレート（subagent / skill / tool の合成）
│   ├── workflows/     …   workflow テンプレート
│   └── instances/     …   具象（actor の実個体 / docker ps 相当）
└── src/               … パッケージマネージャー本体。registries/ を参照する
```

> `prompts/` は設けない。prompt を複数 skill で共有すると skill 間に暗黙の結合が生まれ、
> 依存関係が複雑化するため。**重複は許容し、結合は回避する**方針で、prompt は各 skill に内包する。

### ファイル規約（1 パッケージ = 1 ディレクトリ）

| 種別 | エントリファイル | 形式 | 理由 |
|------|----------------|------|------|
| tool / subagent / actor / workflow | `<name>/index.md` | YAML frontmatter + 本文 | 本文に散文（prompt 等）を持ちうる |
| skill | `<name>/SKILL.md` | YAML frontmatter + 本文 | Claude Code 標準に準拠 |
| instance | `<name>/index.yml` | 純 YAML | 具象パラメータのみで散文不要 |

frontmatter／YAML の先頭は `kind:`（`tool` / `skill` / `subagent` / `actor` / `workflow` / `instance`）で型を識別する。

---

## 標準フォーマット方針

「既存ランタイム（Claude Code 等）がそのまま解釈できる標準フォーマット」に寄せることを基本とし、
標準が存在しない領域のみ独自スキーマを定義する。

| 対象 | 準拠する標準 | 備考 |
|------|------------|------|
| **tool** | **MCP（Model Context Protocol）server** | package 単位は **MCP server 単位**。配布・起動・認証（env/secret）がサーバー単位で効くため、`tools/<server-name>/` を package 境界とする |
| **skill** | **Claude Code skill**（`SKILL.md` + frontmatter + 補助ファイル） | prompt はこの中に内包 |
| **subagent** | **Claude Code subagent**（`.claude/agents/*.md`） | **拡張せず標準のまま**保つ（可搬性最優先）。model + system prompt + tool 許可リストのみ |
| **actor** | **独自スキーマ（合成・ファサード層）** | subagent を参照し、skill / tool の実体を結線する。標準では表現できないため独自定義 |
| **workflow** | **独自スキーマ** | 宣言的なマルチエージェント workflow の業界標準は未確立。将来 LangGraph 等へのコンパイル出力を想定 |
| **instance** | **独自スキーマ（純 YAML）** | テンプレートに env / secret を注入した具象。secret の値は直書きせず参照（env 名）にとどめる |

### subagent と actor の責務分離

「subagent 形式を拡張して actor を表現する」のではなく、不一致（具象化・skill 依存宣言）を
拡張で埋めず **層を分けて解決**する。

- **subagent** … 標準フォーマットのまま。拡張しない → 他ランタイムへもそのまま持ち出せる。
- **actor** … subagent に足りない点を上位層で補う独自スキーマ：
  - **skill / tool の依存宣言と結線** … 「どの subagent に、どの skill と、どの tool 実体を結ぶか」を宣言する。
- **instance** … secret 注入などの具象化情報を持つ（テンプレートからは分離）。

---

## パッケージマネージャーとして今後必要になる要素

現時点では未実装だが、package manager の核として以下が必要になる。

- **ローダー / パーサ** … `registries/**/index.md`（`SKILL.md` / `index.yml`）を読み、`kind` で型付けしてモデル化
- **依存解決** … `workflow → actor → (subagent, skill, tool)` の参照を名前で引き当て・検証
- **具象化** … `${WEATHER_API_KEY}` 等の env / secret を instance に注入
- **versioning** … 例: `actor@1.2` が `subagent@>=2.0` を要求、等
- **依存方向の保証** … `subagent → (model, tool-allowlist)`、`actor → (subagent, skill, tool)`、`workflow → actor`、`instance → actor`

# build：mcp_server → mcp_bundled → instance のビルド手順（仮）

> ⚠️ **これは仮（draft）。** ここに出てくる `juice ...` サブコマンドの多くは未実装で、
> 想定する一連の手続きを推論で書き下したもの。現状実装済みは `juice <layer> list` /
> `juice all list` のみ。コマンド名・引数は確定仕様ではなく叩き台。
>
> 📌 **正は宣言的ワークスペース（[workspace.md](workspace.md)）。** 構成・再現性は
> `juice.yaml`(manifest) + `juice.lock` + `juice apply` が担う。本書の命令的コマンド
> （`juice mcp_server new` 等）は **manifest を編集する糖衣／概念整理** であり、再現性の
> 担保元ではない。各レイヤが何に依存し何を結線するかの **概念フロー**として読むこと。

## このドキュメントが描くもの

「素の MCP server」から「起動中の mcp_bundled instance」までを、パッケージマネージャー的な
ライフサイクルで一直線に通す。コンテナの `build → push → run` に対応させる。

```
mcp_server        … デプロイ可能な成果物（= 1 capability の提供元）          [build / deploy]
   └─ mcp_bundled       … subagent / skill / mcp_server(tool) を集約するファサード   [compose / build]
        └─ instance … mcp_bundled に secret を注入した起動可能な実個体               [instantiate / start]
```

現状は **1 mcp_server = 1 tool**。mcp_bundled はその上の **集約層**で、複数の mcp_server（tool）＋
subagent ＋ skill を 1 つの実行可能エージェントに束ねる。逆に言うと、mcp_bundled として instance 化
する前段に、**単体でデプロイ可能な成果物層 = mcp_server** を置く。

---

## レイヤ位置づけ

`mcp_server` は依存の最下層（すべての tool を提供する土台）。依存順（具象 → 土台）は:

```
instance → workflow → mcp_bundled → subagent → skill → tool → mcp_server
```

- `tool` … subagent から見た「使ってよい capability」（許可リスト側の名前）。
- `mcp_server` … その capability を実際に提供する**デプロイ可能成果物**（command / endpoint / env）。
- 今は 1:1 なので両者はほぼ重なるが、将来「1 server が複数 tool を公開」しても割れるように分けておく。

---

## 手順

### 0. namespace を用意（任意）

```bash
# 既定は default。区画を分けたいときだけ。
juice namespace new staging
juice namespace list
```

### 1. mcp_server をパッケージ化する（成果物層）

素の MCP server 定義を作り、デプロイ可能な成果物として固める。

```bash
# 1-a. テンプレートを scaffold
juice mcp_server new weather \
  --command "npx -y @example/mcp-weather" \
  --env WEATHER_API_KEY

# 1-b. 公開ツール（関数）を宣言（1 server が複数 tool を持てる前提）
juice mcp_server add-tool weather get_forecast --desc "都市の天気予報を返す"

# 1-c. 依存・スキーマを検証して成果物に固める（= build）
juice mcp_server build weather
#   -> registries/<ns>/mcp_servers/weather/ を確定。lockfile / digest を付与。

# 1-d. namespace へデプロイ（= push 相当）。mcp_bundled から参照可能になる。
juice mcp_server deploy weather --namespace default

juice mcp_server list
```

> ここまでで「mcp_bundled に依存される前に、単体でデプロイ可能な成果物」が出来る。
> mcp_server 単体を別の mcp_bundled から再利用できる（集約層との分離点）。

### 2. 脳（subagent）と手順（skill）を用意する

```bash
# 標準フォーマット（Claude Code 準拠）のまま。拡張しない。
juice subagent new forecaster \
  --model claude-opus-4-8 \
  --allow-tool weather              # 許可リスト宣言（capability 側）

juice skill new report-weather      # SKILL.md を scaffold（prompt を内包）
```

### 3. mcp_bundled で集約する（ファサード層）

subagent ＋ skill ＋ mcp_server(tool) を結線して、1 つの実行可能エージェント
テンプレートに束ねる。**ここが集約層**。

```bash
juice mcp_bundled new weather-bot --subagent forecaster

# skill を結線
juice mcp_bundled add-skill weather-bot report-weather

# tool 実体（= mcp_server）を結線。複数 server を足せる = 集約。
juice mcp_bundled bind-tool weather-bot weather \
  --from mcp_server:weather \
  --env WEATHER_API_KEY            # env 名の参照だけ。値はここに書かない

# 依存解決（subagent / skill / mcp_server を名前で引き当て）＋検証して確定
juice mcp_bundled build weather-bot
#   -> 参照先が deploy 済みか・許可リストと結線が整合するかを検査。
```

### 4. instance 化して起動する（具象）

mcp_bundled テンプレートに secret を注入し、起動可能な 1 個体にする（image → container）。

```bash
# テンプレート -> 具象。secret は env 名参照で渡す（直書きしない）。
juice mcp_bundled instantiate weather-bot \
  --name tokyo-weather-bot \
  --namespace default \
  --set WEATHER_API_KEY=env:WEATHER_API_KEY

juice instance start tokyo-weather-bot
juice instance status tokyo-weather-bot
juice instance list
```

### 5. （任意）workflow で束ねる

```bash
juice workflow new morning-brief --schedule "0 7 * * *"
juice workflow add-step morning-brief --mcp_bundled weather-bot --input '{"city":"Tokyo"}'
juice workflow build morning-brief
juice workflow run morning-brief        # 手動キック
```

---

## 別案：mcp_server を「独立デプロイ」しておく形

mcp_bundled に取り込む前に mcp_server を常設デプロイし、mcp_bundled は**参照だけ**するパターン。
リモート/共有 server（複数 mcp_bundled が同じ server を使う）に向く。

```bash
juice mcp_server build weather
juice mcp_server deploy weather --namespace default      # 常設

# mcp_bundled 側は実体を持たず参照に徹する
juice mcp_bundled bind-tool weather-bot weather --ref mcp_server:weather@default
juice mcp_bundled build weather-bot
```

- **取り込み型（手順 3）** … mcp_bundled が server 定義ごと抱える。可搬・自己完結。
- **参照型（別案）** … server は共有資産、mcp_bundled は薄い結線。再利用・集中管理向き。

---

## コマンド早見（仮）

| 目的 | コマンド |
|------|----------|
| server 作成 | `juice mcp_server new <name> --command ... --env ...` |
| server に tool 宣言 | `juice mcp_server add-tool <server> <tool>` |
| server 成果物化 | `juice mcp_server build <name>` |
| server デプロイ | `juice mcp_server deploy <name> -n <ns>` |
| subagent 作成 | `juice subagent new <name> --model ... --allow-tool ...` |
| skill 作成 | `juice skill new <name>` |
| mcp_bundled 作成 | `juice mcp_bundled new <name> --subagent <sa>` |
| mcp_bundled 結線 | `juice mcp_bundled add-skill / bind-tool <mcp_bundled> ...` |
| mcp_bundled 確定 | `juice mcp_bundled build <name>` |
| instance 化 | `juice mcp_bundled instantiate <mcp_bundled> --name <inst> --set K=env:V` |
| 起動 / 状態 | `juice instance start / status / list <inst>` |

---

## 未決の論点（実装前に決める）

- `mcp_server` を独立レイヤにするか、当面 `tool` のリネームで済ますか（1:1 が続く間は後者でも可）。
- `build` の成果物（lockfile / digest）の形式と置き場所。
- `deploy` の意味（local では単にコピー、s3/remote では転送＋登録）。
- 結線の「取り込み型 vs 参照型」をどちらを既定にするか。
- `mcp_client`（接続プロファイル）を namespace 別に持つ必要が出るか。

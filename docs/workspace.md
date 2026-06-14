> ⚠️ **SUPERSEDED（旧・未実装の設計案）。** ここで描いた宣言的ワークスペース
> （`juice.yaml` + `lock` + `apply` + `instance`/`workflow`）は**実装されていません**。
> 現行の実装は **`bundle.yml`（mcp_bundled 定義）→ `init/bundle/build/run`** です
> （[build.md](build.md) / [architecture.md](architecture.md) を参照）。本ファイルは将来検討用の
> 歴史的メモとして残しています。

---

# workspace：宣言的ワークスペース（仮・未実装）

> ⚠️ **仮（draft）。** コマンド・スキーマは叩き台。現状実装済みは `juice <layer> list` /
> `juice all list` のみ。

## 方針：宣言的のみ（Agentfile を持たない）

再現性は **「committed な spec ＋ lock」** が担保する。命令的なビルド手順（Agentfile）や
「コマンドの再実行」では担保しない。Kubernetes と同じく **desired state を宣言 → `apply` で
reconcile** する。`juice.yaml` が唯一の正（source of truth）。

- パイプラインの終点は **deployable な instance**。`mcp_server` / `subagent` / `skill` / `mcp_bundled` /
  `instance` を 1 つの manifest で宣言する（複数 mcp_bundled のスケジューリング＝`workflow` は
  「1 instance を deployable にする」範囲の外なので扱わない）。
- `registries/` は apply の **出力先**（reconcile 結果の置き場）であって、手で書く一次情報ではない。
- 別の `pipeline.yml` は作らない。**manifest 自体がパイプライン**（宣言の二重化を避ける）。

---

## ワークスペースの構成

```
my-agent/
  juice.yaml     # desired state（宣言）= 唯一の正
  juice.lock     # 解決済みバージョン/digest（再現性の本体）
  registries/    # apply の出力（reconcile 結果）。生成物なので手編集しない
```

- **juice.yaml** … 何を・どう結線するかの宣言。人が編集する。
- **juice.lock** … 参照パッケージ（mcp_server の npm 版など）と registry の解決結果を pin。
  これがある限り、別環境でも同じ構成を再現できる。
- **registries/** … `juice apply` が manifest と lock から具現化する。`git` 管理対象にするかは任意
  （生成物として ignore してもよい）。

---

## manifest（juice.yaml）

全レイヤを 1 ファイルで宣言する。依存は名前参照で表す。

```yaml
apiVersion: juice/v1
namespace: default

# 最下層：能力の提供元。command/env を宣言するだけ（命令的ビルドはしない）。
mcp_servers:
  - name: weather
    package: "@example/mcp-weather"   # lock がバージョン/digest を pin
    command: npx -y @example/mcp-weather
    env: [WEATHER_API_KEY]
    tools: [get_forecast]             # 1 server が公開する tool（将来複数可）

# 標準フォーマット（Claude Code 準拠）のまま。
subagents:
  - name: forecaster
    model: claude-opus-4-8
    allow_tools: [weather]            # capability 側の許可リスト
    prompt: |
      あなたは天気予報アシスタントです。簡潔で親切に要点だけを伝えてください。

skills:
  - name: report-weather
    description: 都市の天気を取得し一言で要約する

# 集約層：subagent + skill + mcp_server(tool) を結線。
mcp_bundled:
  - name: weather-bot
    subagent: forecaster
    skills: [report-weather]
    tools:
      - bind: weather
        from: mcp_server:weather      # 取り込み/参照は from で表現
        env: [WEATHER_API_KEY]        # 値は書かず env 名の参照のみ

# 具象：mcp_bundled をバンドル・ビルドし、変数の既定値を与えた deployable な実個体。
# これがパイプラインの最終成果物。
instances:
  - name: tokyo-weather-bot
    mcp_bundled: weather-bot
    # 変数の既定値。これが揃って初めて deployable（入力なしでも起動できる状態）。
    defaults:
      city: "Tokyo"
    # secret は値を書かず env 名の参照のみ。起動時に環境から解決する。
    secrets:
      WEATHER_API_KEY: env:WEATHER_API_KEY
```

> **secret は値を書かない。** `env:NAME` 参照にとどめる。`defaults` は非 secret 変数の既定値で、
> deployable 判定（変数が埋まっているか）の対象。

---

## deployable な instance の定義

このパイプラインのゴールは「**deployable な instance**」を 1 つ作ること。deployable とは
次の 2 つが揃った状態:

1. **バンドル・ビルド済み** … instance が要する依存一式（mcp_bundled → subagent / skill /
   mcp_server=tool）が解決・集約・ビルドされ、`juice.lock` で digest が pin されている。
2. **変数の既定値が定義済み** … 非 secret 変数は `defaults` に既定値があり、secret は
   `env:NAME` 参照が揃っている。→ 追加入力なしで起動できる。

> deploy / 起動そのものは本パイプラインの範囲外（次の工程）。ここでは「いつでもデプロイできる
> 成果物」を作るところまでを定義する。

---

## ライフサイクル（コマンド）

```bash
# 1) 解決：参照パッケージ/registry のバージョン・digest を確定して lock を更新
juice lock

# 2) 差分確認：apply が registry に与える変更を表示（dry-run）
juice plan -f juice.yaml          # = diff（適用せず表示）

# 3) 反映：manifest を registries/ へ reconcile（依存順に下層から）
juice apply -f juice.yaml         # 宣言にない既存リソースは prune（冪等）

# 4) バンドル＆ビルド：instance の依存一式を集約・ビルドし、変数既定値を確定して
#    "deployable な instance" にする（= パイプラインの終点）
juice bundle tokyo-weather-bot

# 5) 検証：deployable か確認（未解決依存・既定値未設定の変数を検出）
juice instance verify tokyo-weather-bot
```

`apply` は **依存順（mcp_server → skill / subagent → mcp_bundled → instance）** に下層から reconcile し、
各リソースを「あるべき状態」へ収束させる（冪等）。`bundle` がその instance を deployable 成果物に
固める終点。

---

## 再現性のモデル

| 担保するもの | 方法 |
|--------------|------|
| 構成（何を・どう結線） | `juice.yaml` を commit |
| 依存の同一性 | `juice.lock`（mcp_server の package 版/digest、registry 解決を pin） |
| 反映の冪等性 | `juice apply`（desired state へ収束、差分のみ適用、不要分は prune） |

**コマンド列の再実行に依存しない。** `juice.yaml` と `juice.lock` を持っていけば、どの環境でも
`juice apply` で同じ構成が再現される。

---

## mcp_server のビルド副作用をどう扱うか（Agentfile なし）

`npx` 取得や vendoring などの副作用は **runtime 側**（instance 起動時の解決）に寄せる。
ビルド成果物を焼くのではなく、**lock で package バージョン/digest を pin** することで再現性を得る。

- 取得の同一性 … `juice.lock` の digest。
- 起動の同一性 … `command`/`env` は manifest に宣言済み。
- 専用のビルド層（Agentfile / `juice build`）は持たない。

> 将来、起動が重く層キャッシュが欲しくなった場合に限り、`mcp_server` のビルド層を再検討する
> （その時点で初めて Agentfile 相当を導入するか判断）。

---

## 未決の論点

- `juice.yaml` を単一ファイルにするか、`kind:` 別の複数 manifest（k8s 風）を許すか。
- `registries/` を生成物として ignore するか、commit するか。
- `from: mcp_server:weather` の取り込み型 / 参照型（共有 server）の表現と既定。
- `juice lock` の digest 取得元（npm / OCI / 独自）。
- namespace 跨ぎ参照（`mcp_server:weather@other-ns`）を許すか。

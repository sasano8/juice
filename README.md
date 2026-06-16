# juice

**AI エージェントのための、宣言的パッケージマネージャー＋デリバリ・パイプライン。**

tool（MCP server）・skill・subagent といった部品を 1 つの spec（`juice.yaml`）で宣言し、
**解決 → 整合 → 生成**を通して「動かせる成果物」（registries / docker image / docker-compose・
k8s manifest）まで一気通貫で組み上げる。コンテナの「イメージ → 起動」を AI エージェントに
持ち込むイメージ。

> **位置づけ:** juice は「依存を宣言・解決・バージョン管理する」パッケージマネージャーであり、
> その *install 先が「動いているデプロイ」* であるデリバリ・パイプラインでもある（同じものの両端）。
> **juice 自身はワークロードを実行しない。** 実行基盤（docker / k8s＋ArgoCD / cron）が食える
> 成果物を**生成**し、常駐・協調・監視・定期実行は実行基盤に委譲する。

## パイプライン（宣言 → 配備）

```
juice.yaml ──lock──▶ 解決＋整合 ──apply──▶ registries/（生成物）
                                              │
              bundle ──bundle/build──▶ docker image
                                              │
      workflow / schedule ──build──▶ docker-compose.yml / k8s manifest（→ 実行基盤へ）
```

- **宣言的が唯一の正:** `juice.yaml` が source of truth。registries / image / manifest はすべて
  spec から再生成される生成物（焼き込まない。整合性は digest で担保）。
- **レイヤの分離:** tool / skill / subagent / bundle / instance / workflow / schedule。
  上位は下位に依存する（詳細は [docs/architecture.md](docs/architecture.md)）。

## いま使える形（リファレンス・フレーバー＝チャット）

現在の juice は **AI エージェントの配備**に特化し、リファレンス実装として
**LangGraph で LLM（Claude）と MCP server を連携した会話エージェント**を同梱している
（サンプル `mcp_weather-bot`）。`bundle → build → run` で起動でき、api / ui / mcp_server の各モードを持つ。

### 利用方法

**前提**
- Docker が使えること。
- **Anthropic の API キー**を `.env.agent` に設定しておくこと。

```bash
cp .env.agent.sample .env.agent
# .env.agent を編集して APIキーを入れる:
#   ANTHROPIC_API_KEY=sk-ant-xxxxxxxx
```

**起動（チャット UI）**

```bash
make juice-run-ui
```

これで **bundle → docker build → 起動** まで自動で走ります（初回はイメージビルドで数分）。
起動後、ブラウザで `http://localhost:8000/chat` を開いてチャットできます。`.env.agent` の
API キーが読み込まれ、Claude が応答します（裏で MCP server の tool を呼びます）。
キー未設定のときは画面に「API キーが未設定です」と表示されます。

**その他の起動・操作**

```bash
make juice-run-api          # 会話 API（/chat ＋ /v1/chat/completions ＋ /docs）
make juice-run-mcp_server   # MCP server（stdio）として起動
make juice-all              # registry の全パッケージを一覧

juice apply -f juice.yaml                 # 宣言を registries へ反映
juice workflow build <name>               # 常駐サービスの docker-compose を生成
juice schedule build <name> --target k8s  # 定期実行の k8s CronJob を生成
```

## ビジョン（汎用化の方向）

> ここは**構想**であり現状の実装ではない。今の juice は上記の AI エージェント配備に特化している。

juice の中核機構（registry / レイヤ / manifest / lock / verify / index / デプロイ成果物生成）は
**本質的に AI 専用ではない**。「型付き資産を宣言・体系化・バージョン管理・配備する」仕組みなので、
**モノレポ＋組織内資産**（dataset / model / 知識）を同じパイプラインに載せて配備する基盤へ
一般化できる、と考えている（知識を Markdown で体系化する OKF の取り込みもこの方向）。
AI エージェントは、その最初の適用例（first application）という位置づけ。

## もっと詳しく

- 概念・レイヤ関係（mcp_server / bundle / subagent / skill / tool / workflow / schedule）:
  [docs/architecture.md](docs/architecture.md)
- ビルド・実行ガイド（bundle.yml / init・bundle・build・run / run モード）: [docs/build.md](docs/build.md)
- 開発の進め方（改善ループ）: [AGENT_LOOP.md](AGENT_LOOP.md)、状態・課題: [PROJECT.md](PROJECT.md)

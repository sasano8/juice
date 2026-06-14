# juice

AI エージェントの **パッケージマネージャー**。tool（MCP server）・skill・subagent をひとつの
`mcp_bundled` として宣言し、**LangGraph で LLM（Claude）と MCP server を連携した会話エージェント**を
`bundle → build → run` で組み上げて起動できる。コンテナの「イメージ→起動」を AI エージェントに
持ち込むイメージ。

## 利用方法

### 前提
- Docker が使えること。
- **Anthropic の API キー**を `.env.agent` に設定しておくこと。

```bash
cp .env.agent.sample .env.agent
# .env.agent を編集して APIキーを入れる:
#   ANTHROPIC_API_KEY=sk-ant-xxxxxxxx
```

### 起動（チャット UI）

```bash
make juice-run-ui
```

これで **bundle → docker build → 起動** まで自動で走ります（初回はイメージビルドで数分）。
起動後、ブラウザで以下を開いてチャットできます:

```
http://localhost:8000/chat
```

`.env.agent` の API キーが読み込まれ、Claude が応答します（裏で MCP server の tool を呼びます）。
キー未設定のときは画面に「API キーが未設定です」と表示されます。

## もっと詳しく

- 概念・レイヤ関係（mcp_server / mcp_bundled / subagent / skill / tool）: [docs/architecture.md](docs/architecture.md)
- ビルド・実行ガイド（bundle.yml / init・bundle・build・run / run モード）: [docs/build.md](docs/build.md)
- その他の起動モード:
  ```bash
  make juice-run-api          # 会話 API（/chat ＋ /v1/chat/completions ＋ /docs）
  make juice-run-mcp_server   # MCP server（stdio）として起動
  make juice-all              # registry の全パッケージを一覧
  ```

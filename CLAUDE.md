# juice — Memory Bank（毎セッション必読）

このプロジェクトは状態を 2 ファイルに永続化している。**新しいセッションで作業に着手する前に、必ず両方を読むこと。**

- **[AGENT_LOOP.md](AGENT_LOOP.md)** … 開発サイクルの手順（ASSESS→PLAN→IMPLEMENT→VERIFY→UPDATE）と運用ルール。プロジェクト非依存。
- **[PROJECT.md](PROJECT.md)** … 概要・バックログ・設計原則・スタック・**作業状態**。これが状態の source of truth。
  - 「作業状態」の **「作業中（In Progress / Next）」** を起点に着手する。
  - 終了時は AGENT_LOOP.md の「運用ルール」に従い、「作業中」を「直前の作業（Just Done）」へ移し、次の作業を「作業中」に書いてから commit する。

> activeContext ＝ PROJECT.md の「作業中」、progress ＝「直前の作業」に対応（Memory Bank 流）。
> 1 サイクルを明示的に回したいときは `/memory-bank` スキルを使う（同じ手順を実行する）。

## 検証

- 着手前後とも `make check`（lint + test）を緑に保つ。
- 可能なら PROJECT.md の「サンプルデプロイの E2E 確認」を行う（API キー/docker 無しならスキップし、その旨を作業状態に残す）。

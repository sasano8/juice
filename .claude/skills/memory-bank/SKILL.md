---
name: memory-bank
description: juice の Memory Bank（状態の永続化）を読み、継続的改善ループを 1 サイクル回す。AGENT_LOOP.md（手順）と PROJECT.md（状態）を読み、PROJECT.md の「作業状態」を起点に ASSESS→PLAN→IMPLEMENT→VERIFY→UPDATE を実行する。ユーザーが「memory bank」「ループを回す」「作業を進める」「次のサイクル」「agentloop」等を求めたとき、または切りのいい作業状態にしたいときに使う。
---

# memory-bank — juice の Memory Bank ＋ 改善ループの 1 サイクル

このスキルは [AGENT_LOOP.md](../../../AGENT_LOOP.md) のループを 1 サイクル実行するための入口。

## 手順

1. **読む（必須・最初に）**
   - リポジトリ直下の `AGENT_LOOP.md`（ループの手順・運用ルール）を読む。
   - リポジトリ直下の `PROJECT.md`（概要・バックログ・設計原則・**作業状態**）を読む。
   - 特に PROJECT.md の「作業状態（Work State）」の **「作業中（In Progress / Next）」** を起点にする。

2. **ASSESS（現状評価）**
   - 「作業中」があればそれを継続。無ければバックログから優先タスクを 1 つ選ぶ。
   - 「作業中」に *ユーザーへ優先度を確認* と書かれている分岐点なら、着手前にユーザーへ候補を提示して確認する。
   - 着手前に `make check` が緑であることを確認する。

3. **PLAN → IMPLEMENT → VERIFY**
   - 実装方針・影響範囲・テスト方法を決める。
   - コードとテストを書き、関連ドキュメント（docs / README / glossary 等）を更新する。
   - `make check`（lint + test）を緑にする。可能なら PROJECT.md の「サンプルデプロイの E2E 確認」を行う
     （API キーや docker が無い等で起動できない場合のみスキップし、その旨を作業状態に残す）。

4. **UPDATE & HANDOFF（毎サイクル必ず）**
   - AGENT_LOOP.md の「運用ルール」に従う：
     - 「作業中」だった項目を「直前の作業（Just Done）」へ移し、**何を変えたか・検証結果・関連 commit** をまとめる。
     - バックログから次の 1 つを選び、「作業中」に **ゴール／タスク（チェックリスト）／完了条件** を書き出す。
   - PROJECT.md の更新を含めて **commit する**（「完了した直前の作業 ＋ 次の作業の計画」を 1 コミットに残す）。
   - commit / push はユーザーが求めたとき、または本ループの運用ルール通りに行う。`main` 直コミットを避ける運用なら branch を切る。

## 注意

- ドキュメントは **手順（AGENT_LOOP.md）／状態（PROJECT.md）** に分離されている。ループの回し方を変えるなら
  AGENT_LOOP.md、現状・課題・作業状態を更新するなら PROJECT.md。
- 1 サイクルで切りよく止める。大物タスクや「実行しない」原則に触れる設計判断は、着手前にユーザーへ確認する。

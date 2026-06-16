"""設定。

1 つの Config が「あるストレージ上の 1 ロケーション」を指す接続記述子。
`backend` がストレージ種別（local / s3 …）、`storage_option` が backend 毎の接続情報
（local なら不要なので空）、`bucket` が入れ物（local なら `registries`）、`namespace` が
リソース空間の区画（既定 `default`）、`path` がその中の 1 つの場所（local なら `mcp_bundled` 等）を
指す。物理的な位置は (bucket, namespace, layer/path) の組で決まり、Kubernetes の
namespace × kind × name と同じリソース空間になる。デフォルトや overrides の解決は factory が
担い、ここには解決済みの値だけを持たせる。複数レイヤを束ねるのは RegistryArray の役割。
"""

from __future__ import annotations

from dataclasses import dataclass

# CLI で使う単数形コマンド名 -> レジストリ上のディレクトリ名（複数形）
LAYERS: dict[str, str] = {
    "tool": "tools",
    "skill": "skills",
    "subagent": "subagents",
    "mcp_bundled": "mcp_bundled",
    "workflow": "workflows",
    "schedule": "schedules",
    "instance": "instances",
}

# 各レイヤのエントリファイル名（1 パッケージ = 1 ディレクトリ）
ENTRY_FILES: dict[str, str] = {
    "tool": "index.md",
    "skill": "SKILL.md",
    "subagent": "index.md",
    "mcp_bundled": "bundle.yml",  # 定義 + ビルド宣言（純 YAML）
    "workflow": "index.md",
    "schedule": "index.md",  # 定期実行ワークロード（cron＋steps）の宣言
    "instance": "index.yml",
}

# `juice all` の列挙順。依存の上位（具象=instance）から末端（tool）へ向かう順を明示宣言する。
ALL_ORDER: list[str] = [
    "instance",
    "workflow",
    "schedule",
    "mcp_bundled",
    "subagent",
    "skill",
    "tool",
]


@dataclass
class Config:
    backend: str  # ストレージ種別: "local" | "s3" 等
    storage_option: dict[str, str]  # backend 毎の接続情報。local なら空
    bucket: str  # 入れ物。local なら "registries"、s3 ならバケット名
    namespace: str  # リソース空間の区画。既定 "default"
    path: str  # namespace 内の 1 ロケーション。local なら "mcp_bundled" 等

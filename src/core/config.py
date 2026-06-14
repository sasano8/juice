"""設定。

1 つの Config が「あるストレージ上の 1 ロケーション」を指す接続記述子。
`backend` がストレージ種別（local / s3 …）、`storage_option` が backend 毎の接続情報
（local なら不要なので空）、`bucket` が入れ物（local なら `registries`）、`path` がその中の
1 つの場所（local なら `actors` 等）を指す。デフォルトや overrides の解決は factory が担い、
ここには解決済みの値だけを持たせる。複数レイヤを束ねるのは RegistryArray の役割。
"""

from __future__ import annotations

from dataclasses import dataclass

# CLI で使う単数形コマンド名 -> レジストリ上のディレクトリ名（複数形）
LAYERS: dict[str, str] = {
    "tool": "tools",
    "skill": "skills",
    "subagent": "subagents",
    "actor": "actors",
    "workflow": "workflows",
    "instance": "instances",
}

# `juice all` の列挙順。依存の上位（具象=instance）から末端（tool）へ向かう順を明示宣言する。
ALL_ORDER: list[str] = ["instance", "workflow", "actor", "subagent", "skill", "tool"]


@dataclass
class Config:
    backend: str  # ストレージ種別: "local" | "s3" 等
    storage_option: dict[str, str]  # backend 毎の接続情報。local なら空
    bucket: str  # 入れ物。local なら "registries"、s3 ならバケット名
    path: str  # bucket 内の 1 ロケーション。local なら "actors" 等

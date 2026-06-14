"""設定。

レジストリのベースパスと、各レイヤのディレクトリ解決を持つ。
まずはデフォルト（`registries/<layer>`）をベタ打ちし、必要に応じて
レイヤ単位でパスを上書きできる。将来 S3 などへ拡張する余地として
`backend` を持たせてあるが、現状は local のみ。
"""

from __future__ import annotations

from dataclasses import dataclass, field

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
    base: str = "registries"
    backend: str = "local"  # 将来: "s3" 等
    root: str = "."  # local backend の基点
    # レイヤ単位のパス上書き。未指定なら `{base}/{LAYERS[layer]}`
    overrides: dict[str, str] = field(default_factory=dict)

    def path_for(self, layer: str) -> str:
        """レイヤのレジストリパスを返す。上書きがあればそれを優先。"""
        if layer not in LAYERS:
            raise KeyError(f"unknown layer: {layer}")
        if layer in self.overrides:
            return self.overrides[layer]
        return f"{self.base}/{LAYERS[layer]}"

"""juice の Python API（core）。

CLI を含む利用側はこのパッケージ越しにレジストリを操作する。
Config/Storage/Registry の組み立ては `Juice` ファサードが隠蔽し、
``Juice().list("tool")`` のように最小手数で使えるようにする。
"""

from __future__ import annotations

from .config import ALL_ORDER, LAYERS, Config
from .factory import create_registry, create_storage
from .registry import Registry
from .storage import LocalStorage, Storage

__all__ = [
    "Juice",
    "Config",
    "Registry",
    "Storage",
    "LocalStorage",
    "LAYERS",
    "ALL_ORDER",
    "create_registry",
    "create_storage",
]


class Juice:
    """juice の操作をまとめた API ファサード。

    Config からレジストリを組み立て、レイヤ単位／全レイヤの一覧取得を提供する。
    出力整形（ラベル付けや並び）は呼び出し側（CLI 等）の責務とし、ここでは
    生データ（名前リスト）のみ返す。
    """

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()
        self.registry: Registry = create_registry(self.config)

    def list(self, layer: str) -> list[str]:
        """単一レイヤのパッケージ名一覧を返す。"""
        return self.registry.list(layer)

    def list_all(self) -> dict[str, list[str]]:
        """全レイヤを依存順（ALL_ORDER）に並べた {レイヤ: 名前リスト} を返す。"""
        return {layer: self.registry.list(layer) for layer in ALL_ORDER}

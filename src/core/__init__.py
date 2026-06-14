"""juice の Python API（core）。

CLI を含む利用側はこのパッケージ越しにレジストリを操作する。
Config/Storage/Registry の組み立ては `Juice` ファサードが隠蔽し、
``Juice().list("tool")`` のように最小手数で使えるようにする。
"""

from __future__ import annotations

from .config import ALL_ORDER, LAYERS, Config
from .factory import create_registries, create_registry, create_storage
from .registry import Registry, RegistryArray
from .storage import LocalStorage, Storage

__all__ = [
    "Juice",
    "Config",
    "Registry",
    "RegistryArray",
    "Storage",
    "LocalStorage",
    "LAYERS",
    "ALL_ORDER",
    "create_registry",
    "create_registries",
    "create_storage",
]


class Juice:
    """juice の操作をまとめた API ファサード。

    bucket からレジストリ群（RegistryArray）を組み立て、レイヤ単位／全レイヤの一覧取得を
    提供する。出力整形（ラベル付けや並び）は呼び出し側（CLI 等）の責務とし、ここでは
    生データ（名前リスト）のみ返す。
    """

    def __init__(self, bucket: str | None = None) -> None:
        self.registries: RegistryArray = create_registries(bucket)

    def list(self, layer: str) -> list[str]:
        """単一レイヤのパッケージ名一覧を返す。"""
        return self.registries.list(layer)

    def list_all(self) -> dict[str, list[str]]:
        """全レイヤを依存順（ALL_ORDER）に並べた {レイヤ: 名前リスト} を返す。"""
        return self.registries.list_all()

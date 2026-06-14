"""juice の Python API（core）。

CLI を含む利用側はこのパッケージ越しにレジストリを操作する。
Config/Storage/Registry の組み立ては `Juice` ファサードが隠蔽し、
``Juice().list("tool")`` のように最小手数で使えるようにする。
"""

from __future__ import annotations

from . import bundle as _bundle
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

    bucket / namespace からレジストリ群（RegistryArray）を組み立て、レイヤ単位／全レイヤの
    一覧取得を提供する。出力整形（ラベル付けや並び）は呼び出し側（CLI 等）の責務とし、ここでは
    生データ（名前リスト）のみ返す。
    """

    def __init__(self, bucket: str | None = None, namespace: str | None = None) -> None:
        self.registries: RegistryArray = create_registries(bucket, namespace=namespace)

    def list(self, layer: str) -> list[str]:
        """単一レイヤのパッケージ名一覧を返す。"""
        return self.registries.list(layer)

    def list_all(self) -> dict[str, list[str]]:
        """全レイヤを依存順（ALL_ORDER）に並べた {レイヤ: 名前リスト} を返す。"""
        return self.registries.list_all()

    def init(self, name: str, clean: bool = False) -> dict:
        """宣言ファイル bundle.yml の雛形を生成し、生成物をクリーンする（既存なら要 clean）。"""
        return _bundle.init(self.registries, name, clean=clean)

    def bundle(self, name: str) -> dict:
        """内包物を vendoring し、build コンテキスト（requirements/entrypoint/Dockerfile）を生成する。"""
        return _bundle.bundle(self.registries, name)

    def build(self, name: str, image: str | None = None) -> dict:
        """docker イメージビルドコマンドを生成して返す（実行はしない）。"""
        return _bundle.build(self.registries, name, image)

    def run(self, name: str, image: str | None = None) -> dict:
        """docker run コマンド（mcp_server を stdio 起動）を生成して返す。"""
        return _bundle.run(self.registries, name, image)

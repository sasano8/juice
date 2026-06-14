"""レジストリ操作。

Registry は 1 ロケーション（1 つの Config / Storage）を扱い、その配下のパッケージ
一覧を返す。複数レイヤを束ねるのは RegistryArray。
"""

from __future__ import annotations

from .config import Config
from .storage import Storage


class Registry:
    """1 ロケーション（Config.path）配下のパッケージ一覧を引く。"""

    def __init__(self, config: Config, storage: Storage) -> None:
        self.config = config
        self.storage = storage

    def list(self) -> list[str]:
        """このロケーション配下のパッケージ（= ディレクトリ）名一覧を返す。"""
        return self.storage.list_dirs(self.config.path)


class RegistryArray:
    """レイヤ名で引ける Registry の束。"""

    def __init__(self, registries: dict[str, Registry]) -> None:
        self._registries = registries

    def list(self, layer: str) -> list[str]:
        """指定レイヤのパッケージ名一覧を返す。未知のレイヤなら KeyError。"""
        return self._registries[layer].list()

    def list_all(self) -> dict[str, list[str]]:
        """束ねている全レイヤを保持順に {レイヤ: 名前リスト} で返す。"""
        return {layer: reg.list() for layer, reg in self._registries.items()}

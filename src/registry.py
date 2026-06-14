"""レジストリ操作。

Config が示すパスを Storage 越しに引き、各レイヤのパッケージ一覧を返す。
"""

from __future__ import annotations

from .config import Config
from .storage import Storage


class Registry:
    def __init__(self, config: Config, storage: Storage) -> None:
        self.config = config
        self.storage = storage

    def list(self, layer: str) -> list[str]:
        """レイヤ配下のパッケージ（= ディレクトリ）名一覧を返す。"""
        return self.storage.list_dirs(self.config.path_for(layer))

"""レジストリ操作。

Registry は 1 ロケーション（1 つの Config / Storage）を扱い、その配下のパッケージ
一覧を返す。複数レイヤを束ねるのは RegistryArray。
"""

from __future__ import annotations

from .config import ENTRY_FILES, Config
from .storage import Storage


class Registry:
    """1 ロケーション（Config.path）配下のパッケージを引く。"""

    def __init__(self, config: Config, storage: Storage) -> None:
        self.config = config
        self.storage = storage

    def list(self) -> list[str]:
        """このロケーション配下のパッケージ（= ディレクトリ）名一覧を返す。"""
        return self.storage.list_dirs(self.config.path)

    def read(self, name: str, entry: str) -> str:
        """このロケーション配下 `name/entry` のテキストを読む。"""
        return self.storage.read_text(f"{self.config.path}/{name}/{entry}")

    def exists(self, name: str, entry: str) -> bool:
        """このロケーション配下 `name/entry` が存在するか。"""
        return self.storage.exists(f"{self.config.path}/{name}/{entry}")

    def write(self, name: str, entry: str, text: str) -> None:
        """このロケーション配下 `name/entry` にテキストを書く。"""
        self.storage.write_text(f"{self.config.path}/{name}/{entry}", text)

    def remove(self, name: str, entry: str) -> None:
        """このロケーション配下 `name/entry` を削除する（無ければ無視）。"""
        self.storage.remove(f"{self.config.path}/{name}/{entry}")

    def location(self, name: str, entry: str = "") -> str:
        """`name`（任意で `entry`）の物理パスを返す（local: cwd 起点）。docker context 用。"""
        base = f"{self.config.bucket}/{self.config.namespace}/{self.config.path}/{name}"
        return f"{base}/{entry}" if entry else base


class RegistryArray:
    """レイヤ名で引ける Registry の束。"""

    def __init__(self, registries: dict[str, Registry]) -> None:
        self._registries = registries

    @property
    def namespace(self) -> str:
        """束ねている registry の namespace（全レイヤ共通）。"""
        return next(iter(self._registries.values())).config.namespace

    def list(self, layer: str) -> list[str]:
        """指定レイヤのパッケージ名一覧を返す。未知のレイヤなら KeyError。"""
        return self._registries[layer].list()

    def list_all(self) -> dict[str, list[str]]:
        """束ねている全レイヤを保持順に {レイヤ: 名前リスト} で返す。"""
        return {layer: reg.list() for layer, reg in self._registries.items()}

    def read(self, layer: str, name: str, entry: str | None = None) -> str:
        """指定レイヤのパッケージ `name` のファイルを読む（既定はエントリファイル）。"""
        return self._registries[layer].read(name, entry or ENTRY_FILES[layer])

    def exists(self, layer: str, name: str, entry: str | None = None) -> bool:
        """指定レイヤのパッケージ `name` のファイルが存在するか（既定はエントリファイル）。"""
        return self._registries[layer].exists(name, entry or ENTRY_FILES[layer])

    def write(self, layer: str, name: str, entry: str, text: str) -> None:
        """指定レイヤのパッケージ `name` 配下 `entry` にテキストを書く。"""
        self._registries[layer].write(name, entry, text)

    def remove(self, layer: str, name: str, entry: str) -> None:
        """指定レイヤのパッケージ `name` 配下 `entry` を削除する。"""
        self._registries[layer].remove(name, entry)

    def location(self, layer: str, name: str, entry: str = "") -> str:
        """指定レイヤのパッケージ `name`（任意で `entry`）の物理パスを返す。"""
        return self._registries[layer].location(name, entry)

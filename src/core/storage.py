"""ストレージ抽象。

将来 S3 などのバックエンドを差し込めるよう、レジストリへのアクセスを
この抽象越しに行う。まずはローカルファイルシステム実装のみ。
"""

from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from pathlib import Path


class Storage(ABC):
    """レジストリ格納先へのアクセス。"""

    @abstractmethod
    def list_dirs(self, path: str) -> list[str]:
        """`path` 直下のディレクトリ名を名前順で返す。path が無ければ空リスト。"""

    @abstractmethod
    def exists(self, path: str) -> bool:
        """`path` が存在するか。"""

    @abstractmethod
    def read_text(self, path: str) -> str:
        """`path` のテキストを読む。"""

    @abstractmethod
    def write_text(self, path: str, text: str) -> None:
        """`path` にテキストを書く（親ディレクトリは必要なら作成）。"""

    @abstractmethod
    def remove(self, path: str) -> None:
        """`path` を削除（ディレクトリは再帰削除）。無ければ無視。"""


class LocalStorage(Storage):
    """ローカルファイルシステム実装。`root` を基点に相対パスを解決する。"""

    def __init__(self, root: str | Path = ".") -> None:
        self.root = Path(root)

    def _resolve(self, path: str) -> Path:
        return self.root / path

    def list_dirs(self, path: str) -> list[str]:
        base = self._resolve(path)
        if not base.is_dir():
            return []
        return sorted(p.name for p in base.iterdir() if p.is_dir())

    def exists(self, path: str) -> bool:
        return self._resolve(path).exists()

    def read_text(self, path: str) -> str:
        return self._resolve(path).read_text(encoding="utf-8")

    def write_text(self, path: str, text: str) -> None:
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def remove(self, path: str) -> None:
        target = self._resolve(path)
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()

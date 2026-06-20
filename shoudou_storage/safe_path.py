"""safe path — backend を包む単一のラッパ層（パス検証＋ダウンロード/キャッシュ）。

[validate_safe_path] が POSIX 相対パスのみを許し、絶対パス・`..`・バックスラッシュ・NUL を弾く。
[SafeKeyValueStore] は backend（[KeyValueStore]）を 1 枚だけ包む**唯一の wrapper**で、キー検証して
委譲しつつ、`download` でローカルキャッシュへ取得する機能も持つ。**ラッパは入れ子にしない**
（差し替えるのは backend だけ＝ネストによる性能低下と、利用者ごとの挙動差を避ける）。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from .async_storage import FileInfo, FileObject, FileStore, KeyValueStore, _atomic_write_bytes

# ダウンロードキャッシュのデフォルト先（ホーム配下）。
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "shoudou_storage"


class UnsafePathError(ValueError):
    """安全でないキー/パスが渡された。"""


def validate_safe_path(path: str) -> str:
    """`path` を検証し、安全ならそのまま返す。不正なら [UnsafePathError]。

    許可するのは POSIX 相対パスのみ。弾くもの:
    空文字 / NUL バイト / バックスラッシュ / 絶対パス（先頭 '/'） / '..' セグメント。
    """
    if not path:
        raise UnsafePathError("empty path")
    if "\x00" in path:
        raise UnsafePathError(f"NUL byte in path: {path!r}")
    if "\\" in path:
        raise UnsafePathError(f"backslash in path: {path!r}")
    if path.startswith("/"):
        raise UnsafePathError(f"absolute path: {path!r}")
    if any(seg == ".." for seg in path.split("/")):
        raise UnsafePathError(f"parent traversal in path: {path!r}")
    return path


class SafeKeyValueStore:
    """backend を 1 枚だけ包む唯一の wrapper。キー検証＋委譲に加え `download`（キャッシュ）も持つ。

    キーは [validate_safe_path] で検証してから委譲する（path を覗いて検証するため各メソッドを
    明示的に書く＝型情報もそのまま引き継がれる）。`download` はローカルのキャッシュ先へ取得する
    （キャッシュは常にローカル FS・sync。cache_dir は init で絶対パスへ固定＝cd 非依存）。
    """

    def __init__(self, store: KeyValueStore, cache_dir: Path | str | None = None) -> None:
        self._store = store
        base = Path(cache_dir).expanduser() if cache_dir is not None else DEFAULT_CACHE_DIR
        self._cache_dir = base.resolve()  # cwd が変わってもヒットさせるため固定

    async def put(self, key: str, value: bytes) -> None:
        await self._store.put(validate_safe_path(key), value)

    async def get(self, key: str) -> bytes | None:
        return await self._store.get(validate_safe_path(key))

    def iter(self) -> AsyncIterator[FileInfo]:
        return self._store.iter()

    async def list(self, limit: int = 10) -> list[FileInfo]:
        return await self._store.list(limit)

    async def exists(self, key: str) -> bool:
        return await self._store.exists(validate_safe_path(key))

    async def delete(self, key: str) -> None:
        await self._store.delete(validate_safe_path(key))

    async def cp(self, src: str, dst: str) -> None:
        await self._store.cp(validate_safe_path(src), validate_safe_path(dst))

    async def mv(self, src: str, dst: str) -> None:
        await self._store.mv(validate_safe_path(src), validate_safe_path(dst))

    async def connect(self) -> None:
        await self._store.connect()

    async def aclose(self) -> None:
        await self._store.aclose()

    @property
    def cache_dir(self) -> Path:
        return self._cache_dir

    async def download(self, key: str, *, force: bool = False) -> Path:
        """`key` の値をローカルキャッシュへ取得してパスを返す（PyTorch のモデル DL 様）。

        既にキャッシュ済み（ローカルにファイルが在る）なら再取得しない。`force=True` で取り直す。
        キャッシュ済み判定は存在ベース。上流更新の自動無効化には上流メタデータが要るが現状 KVS は
        per-key メタデータを持たない（ローカル backend は上流＝ローカルで検証メタデータも無い）。
        """
        safe = validate_safe_path(key)
        dst = self._cache_dir / safe
        if dst.is_file() and not force:
            return dst  # cache hit（存在ベース）
        data = await self._store.get(key)
        if data is None:
            raise FileNotFoundError(key)
        dst.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_bytes(dst, data)  # 原子的に書く
        return dst


class SafeFileStore:
    """filename を [validate_safe_path] で検証してから委譲する [FileStore] ラッパ。"""

    def __init__(self, store: FileStore) -> None:
        self._store = store

    async def open(self, filename: str, mode: str = "rb") -> FileObject:
        return await self._store.open(validate_safe_path(filename), mode)

"""async storage — 非同期ストアの一次実装。

2 種のストア抽象を持つ:
- [KeyValueStore] … put/get がメインの値ストア（バイト列をキーで出し入れ）。
  Local / S3 / NATS バックエンドを同梱。
- [FileStore] … `open` でファイルオブジェクト（[FileObject]）を取得するストリーム指向の抽象。
  当面はインターフェイスのみ（実装は後で）。

ストレージの一次実装はこの async 側に置く（同期版は async_to_sync_storage が被せて得る）。
重い backend（aiobotocore / nats）は各メソッド内で遅延 import する。
"""

from __future__ import annotations

import io
from collections.abc import AsyncIterator
from pathlib import Path
from typing import BinaryIO, Protocol, TypedDict


class FileInfo(TypedDict):
    filename: str
    size: int


# ── Key-Value store（put/get がメイン） ──


class KeyValueStore(Protocol):
    async def put(self, key: str, value: bytes) -> None: ...
    async def get(self, key: str) -> bytes | None: ...
    def iter(self) -> AsyncIterator[FileInfo]: ...
    async def list(self, limit: int = 10) -> list[FileInfo]: ...
    async def exists(self, key: str) -> bool: ...


async def _take(entries: AsyncIterator[FileInfo], limit: int) -> list[FileInfo]:
    """非同期イテレータから先頭 `limit` 件を集めて返す（各 backend の list 共通実装）。"""
    out: list[FileInfo] = []
    async for info in entries:
        out.append(info)
        if len(out) >= limit:
            break
    return out


# ── Local filesystem ──


class LocalKeyValueStore:
    def __init__(self, directory: Path) -> None:
        # 初期化時に絶対パスへ解決して固定する。実行中に cwd が cd で変わっても
        # 挙動が変わらないようにするため（相対パスのまま保持しない）。
        self._dir = Path(directory).resolve()
        self._dir.mkdir(parents=True, exist_ok=True)

    async def put(self, key: str, value: bytes) -> None:
        # キーに '/' を含む場合に備えて親ディレクトリを作る（s3/nats の
        # フラットキー規約＝任意の '/' を含むキーをそのまま置けるのに合わせる）。
        path = self._dir / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)

    async def get(self, key: str) -> bytes | None:
        path = self._dir / key
        if not path.is_file():
            return None
        return path.read_bytes()

    async def iter(self) -> AsyncIterator[FileInfo]:
        # 再帰列挙（rglob）。キーは self._dir からの相対 posix パスにし、'/' を含む
        # ネストキーも列挙する（s3/nats のフラットキー列挙と規約を揃える）。
        files = sorted(
            (f for f in self._dir.rglob("*") if f.is_file()),
            key=lambda p: p.relative_to(self._dir).as_posix(),
            reverse=True,
        )
        for f in files:
            yield FileInfo(filename=f.relative_to(self._dir).as_posix(), size=f.stat().st_size)

    async def list(self, limit: int = 10) -> list[FileInfo]:
        return await _take(self.iter(), limit)

    async def exists(self, key: str) -> bool:
        return (self._dir / key).is_file()


# ── S3-compatible ──


class S3KeyValueStore:
    def __init__(
        self,
        bucket: str,
        endpoint_url: str = "",
        region: str = "us-east-1",
        access_key: str = "",
        secret_key: str = "",
    ) -> None:
        self._bucket = bucket
        self._endpoint_url = endpoint_url or None
        self._region = region
        self._access_key = access_key
        self._secret_key = secret_key

    def _session(self):
        from aiobotocore.session import get_session

        return get_session().create_client(
            "s3",
            endpoint_url=self._endpoint_url,
            region_name=self._region,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
        )

    async def put(self, key: str, value: bytes) -> None:
        async with self._session() as client:
            await client.put_object(Bucket=self._bucket, Key=key, Body=value)

    async def get(self, key: str) -> bytes | None:
        async with self._session() as client:
            try:
                resp = await client.get_object(Bucket=self._bucket, Key=key)
                async with resp["Body"] as stream:
                    return await stream.read()
            except client.exceptions.NoSuchKey:
                return None

    async def iter(self) -> AsyncIterator[FileInfo]:
        async with self._session() as client:
            paginator = client.get_paginator("list_objects_v2")
            objects: list[dict] = []
            async for page in paginator.paginate(Bucket=self._bucket):
                objects.extend(page.get("Contents", []))
        objects.sort(key=lambda o: o["Key"], reverse=True)
        for o in objects:
            yield FileInfo(filename=o["Key"], size=o["Size"])

    async def list(self, limit: int = 10) -> list[FileInfo]:
        return await _take(self.iter(), limit)

    async def exists(self, key: str) -> bool:
        async with self._session() as client:
            try:
                await client.head_object(Bucket=self._bucket, Key=key)
                return True
            except Exception:
                return False


# ── NATS JetStream Object Store ──


class NatsObjectKeyValueStore:
    def __init__(self, url: str, bucket: str) -> None:
        self._url = url
        self._bucket = bucket
        self._nc = None
        self._obs = None

    async def _get_obs(self):
        if self._obs is None:
            import nats
            from nats.js.errors import BucketNotFoundError

            self._nc = await nats.connect(self._url)
            js = self._nc.jetstream()
            try:
                self._obs = await js.object_store(self._bucket)
            except BucketNotFoundError:
                self._obs = await js.create_object_store(self._bucket)
        return self._obs

    async def put(self, key: str, value: bytes) -> None:
        obs = await self._get_obs()
        await obs.put(key, value)

    async def get(self, key: str) -> bytes | None:
        obs = await self._get_obs()
        try:
            result = await obs.get(key)
            return result.data
        except Exception:
            return None

    async def iter(self) -> AsyncIterator[FileInfo]:
        obs = await self._get_obs()
        try:
            entries = await obs.list()
        except Exception:
            entries = []
        entries = [e for e in entries if not e.deleted]
        entries.sort(key=lambda e: e.name, reverse=True)
        for e in entries:
            yield FileInfo(filename=e.name, size=e.size or 0)

    async def list(self, limit: int = 10) -> list[FileInfo]:
        return await _take(self.iter(), limit)

    async def exists(self, key: str) -> bool:
        obs = await self._get_obs()
        try:
            info = await obs.info(key)
            return not info.deleted
        except Exception:
            return False


# ── Factory ──


def create_key_value_store(
    backend: str,
    local_dir: Path | None = None,
    s3_bucket: str = "",
    s3_endpoint: str = "",
    s3_region: str = "us-east-1",
    s3_access_key: str = "",
    s3_secret_key: str = "",
    nats_url: str = "",
    nats_bucket: str = "shoudou_files",
) -> KeyValueStore:
    if backend == "local":
        if local_dir is None:
            raise ValueError("local backend requires local_dir")
        return LocalKeyValueStore(local_dir)
    elif backend == "s3":
        return S3KeyValueStore(
            bucket=s3_bucket,
            endpoint_url=s3_endpoint,
            region=s3_region,
            access_key=s3_access_key,
            secret_key=s3_secret_key,
        )
    elif backend == "nats":
        return NatsObjectKeyValueStore(url=nats_url, bucket=nats_bucket)
    else:
        raise ValueError(f"unknown backend: {backend!r}")


# ── File store（open でファイルオブジェクトを取得） ──


class FileObject(Protocol):
    """`FileStore.open` が返すファイルオブジェクト（ストリーム）。"""

    async def read(self, size: int = -1) -> bytes: ...
    async def write(self, data: bytes) -> int: ...
    async def close(self) -> None: ...
    async def __aenter__(self) -> FileObject: ...
    async def __aexit__(self, *exc: object) -> None: ...


class FileStore(Protocol):
    """`open` でファイルオブジェクトを取得するストリーム指向のストア。"""

    async def open(self, filename: str, mode: str = "rb") -> FileObject: ...


# ── Local file store ──


class LocalFileObject:
    """ローカルファイルハンドルを [FileObject] として被せる（IO 自体は同期）。"""

    def __init__(self, fh: BinaryIO) -> None:
        self._fh = fh

    async def read(self, size: int = -1) -> bytes:
        return self._fh.read(size)

    async def write(self, data: bytes) -> int:
        return self._fh.write(data)

    async def close(self) -> None:
        self._fh.close()

    async def __aenter__(self) -> LocalFileObject:
        return self

    async def __aexit__(self, *exc: object) -> None:
        self._fh.close()


class LocalFileStore:
    """`open` でファイルオブジェクトを返すローカル実装（[FileStore]）。"""

    def __init__(self, directory: Path) -> None:
        # KVS と同様、初期化時に絶対パスへ固定する（実行中の cd で挙動を変えない）。
        self._dir = Path(directory).resolve()
        self._dir.mkdir(parents=True, exist_ok=True)

    async def open(self, filename: str, mode: str = "rb") -> FileObject:
        path = self._dir / filename
        # 書き込み系モードなら親ディレクトリを作る（KVS の put と同じ規約）。
        if any(c in mode for c in "wax+"):
            path.parent.mkdir(parents=True, exist_ok=True)
        return LocalFileObject(path.open(mode))


# ── KeyValueStore を FileStore として被せるアダプタ ──


class _KvReadFileObject:
    """KVS から取得した全体バイト列を読み出す読み取り専用 [FileObject]。"""

    def __init__(self, data: bytes) -> None:
        self._buf = io.BytesIO(data)

    async def read(self, size: int = -1) -> bytes:
        return self._buf.read(size)

    async def write(self, data: bytes) -> int:
        raise io.UnsupportedOperation("not writable")

    async def close(self) -> None:
        self._buf.close()

    async def __aenter__(self) -> _KvReadFileObject:
        return self

    async def __aexit__(self, *exc: object) -> None:
        self._buf.close()


class _KvWriteFileObject:
    """書き込みをメモリにバッファし、close 時に KVS へ全体 put する [FileObject]。"""

    def __init__(self, store: KeyValueStore, key: str) -> None:
        self._store = store
        self._key = key
        self._buf = io.BytesIO()
        self._closed = False

    async def read(self, size: int = -1) -> bytes:
        raise io.UnsupportedOperation("not readable")

    async def write(self, data: bytes) -> int:
        return self._buf.write(data)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._store.put(self._key, self._buf.getvalue())
        self._buf.close()

    async def __aenter__(self) -> _KvWriteFileObject:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()


class KeyValueFileStore:
    """[KeyValueStore] を [FileStore]（open）として被せるアダプタ。

    S3 / NATS のような全体 get/put のオブジェクトストアに open ベースのアクセスを与える
    （`KeyValueFileStore(S3KeyValueStore(...))` で S3 の FileStore になる）。真のストリーミング/
    ランダムアクセスではなく、read は全体取得、write は close 時に全体 put（メモリにバッファ）。
    """

    def __init__(self, store: KeyValueStore) -> None:
        self._store = store

    async def open(self, filename: str, mode: str = "rb") -> FileObject:
        if "r" in mode:
            data = await self._store.get(filename)
            if data is None:
                raise FileNotFoundError(filename)
            return _KvReadFileObject(data)
        if "w" in mode:
            return _KvWriteFileObject(self._store, filename)
        raise ValueError(f"unsupported mode for KeyValueFileStore: {mode!r}")

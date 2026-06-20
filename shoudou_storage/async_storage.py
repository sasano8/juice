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

import asyncio
import contextlib
import io
import os
import tempfile
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
    async def delete(self, key: str) -> None: ...
    async def cp(self, src: str, dst: str) -> None: ...
    async def mv(self, src: str, dst: str) -> None: ...
    async def connect(self) -> None: ...
    async def aclose(self) -> None: ...


async def _take(entries: AsyncIterator[FileInfo], limit: int) -> list[FileInfo]:
    """非同期イテレータから先頭 `limit` 件を集めて返す（各 backend の list 共通実装）。"""
    out: list[FileInfo] = []
    async for info in entries:
        out.append(info)
        if len(out) >= limit:
            break
    return out


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """同じディレクトリの一時ファイルへ書いてから `os.replace` で原子的に差し替える。

    途中失敗で `path` が壊れない（all-or-nothing）。一時ファイルは同一ディレクトリに作るので
    rename は同一ファイルシステム内＝アトミック。失敗時は一時ファイルを掃除する。
    """
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f"{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


async def _kv_copy(store: KeyValueStore, src: str, dst: str) -> None:
    """get→put で src を dst へコピーする汎用実装（src が無ければ FileNotFoundError）。"""
    data = await store.get(src)
    if data is None:
        raise FileNotFoundError(src)
    await store.put(dst, data)


async def _kv_move(store: KeyValueStore, src: str, dst: str) -> None:
    """copy→delete で src を dst へ移動する汎用実装（原子的ではない）。"""
    await _kv_copy(store, src, dst)
    await store.delete(src)


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
        # temp+rename で原子的に書く（途中失敗で既存値が壊れない＝all-or-nothing）。
        _atomic_write_bytes(path, value)

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

    async def delete(self, key: str) -> None:
        # ファイルだけ消す（空になった親ディレクトリは残す）。無いキーは無視。
        path = self._dir / key
        if path.is_file():
            path.unlink()

    async def vacuum(self) -> None:
        """空ディレクトリを再帰的に削除する（root 自身は残す）。delete とは別の保守操作。

        ローカルファイルシステム特有の掃除（s3/nats はフラットで空ディレクトリ概念が無い）。
        bottom-up に走査するので、ネストした空ディレクトリもまとめて畳む。
        """
        for dirpath, _dirnames, _filenames in os.walk(self._dir, topdown=False):
            p = Path(dirpath)
            if p != self._dir and not any(p.iterdir()):
                with contextlib.suppress(OSError):
                    p.rmdir()

    async def cp(self, src: str, dst: str) -> None:
        await _kv_copy(self, src, dst)  # get→put（put は原子的・親ディレクトリ作成）

    async def mv(self, src: str, dst: str) -> None:
        src_path = self._dir / src
        if not src_path.is_file():
            raise FileNotFoundError(src)
        dst_path = self._dir / dst
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(src_path, dst_path)  # 同一 FS 内の原子的 rename

    async def connect(self) -> None:
        # ローカルは接続不要だが、ライフサイクルのステップを合わせるため dir を確実に用意する。
        self._dir.mkdir(parents=True, exist_ok=True)

    async def aclose(self) -> None:
        return None


# ── S3-compatible ──


class _S3Base:
    """S3 系ストアの共通接続部（bucket・認証・`_session`）。"""

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

    async def connect(self) -> None:
        # 永続セッションは持たない（毎オペでクライアント生成）。接続確認として bucket 到達を見る。
        async with self._session() as client:
            await client.head_bucket(Bucket=self._bucket)

    async def aclose(self) -> None:
        return None


class S3KeyValueStore(_S3Base):
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

    async def delete(self, key: str) -> None:
        async with self._session() as client:
            await client.delete_object(Bucket=self._bucket, Key=key)

    async def cp(self, src: str, dst: str) -> None:
        async with self._session() as client:
            await client.copy_object(
                Bucket=self._bucket,
                Key=dst,
                CopySource={"Bucket": self._bucket, "Key": src},
            )

    async def mv(self, src: str, dst: str) -> None:
        await self.cp(src, dst)  # S3 にネイティブの move は無い
        await self.delete(src)


# ── NATS JetStream Object Store ──


class _NatsBase:
    """NATS object store の共通接続部（lazy connect の `_get_obs`）。"""

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

    async def connect(self) -> None:
        # nc 接続＋object store を確立する（以降は使い回す）。
        await self._get_obs()

    async def aclose(self) -> None:
        if self._nc is not None:
            await self._nc.close()
            self._nc = None
            self._obs = None


class NatsObjectKeyValueStore(_NatsBase):
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

    async def delete(self, key: str) -> None:
        obs = await self._get_obs()
        with contextlib.suppress(Exception):
            await obs.delete(key)

    async def cp(self, src: str, dst: str) -> None:
        await _kv_copy(self, src, dst)

    async def mv(self, src: str, dst: str) -> None:
        await _kv_move(self, src, dst)


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


class _LocalAtomicWriter:
    """一時ファイルへ書き、close（正常終了）でのみ `os.replace` で確定する書き込み [FileObject]。

    全部書けてから差し替えるので all-or-nothing（途中失敗・例外では確定せず一時ファイルを破棄）。
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f"{path.name}.", suffix=".tmp")
        self._tmp = tmp
        self._fh = os.fdopen(fd, "wb")
        self._done = False

    async def read(self, size: int = -1) -> bytes:
        raise io.UnsupportedOperation("not readable")

    async def write(self, data: bytes) -> int:
        return self._fh.write(data)

    async def close(self) -> None:
        if self._done:
            return
        self._done = True
        self._fh.close()
        os.replace(self._tmp, self._path)  # ここで初めて確定（原子的差し替え）

    async def _abort(self) -> None:
        if self._done:
            return
        self._done = True
        self._fh.close()
        with contextlib.suppress(OSError):
            os.unlink(self._tmp)

    async def __aenter__(self) -> _LocalAtomicWriter:
        return self

    async def __aexit__(self, *exc: object) -> None:
        if exc and exc[0] is not None:
            await self._abort()  # 例外時は確定しない
        else:
            await self.close()


class LocalFileStore:
    """`open` でファイルオブジェクトを返すローカル実装（[FileStore]）。書き込みは原子的。"""

    def __init__(self, directory: Path) -> None:
        # KVS と同様、初期化時に絶対パスへ固定する（実行中の cd で挙動を変えない）。
        self._dir = Path(directory).resolve()
        self._dir.mkdir(parents=True, exist_ok=True)

    async def open(self, filename: str, mode: str = "rb") -> FileObject:
        path = self._dir / filename
        if "r" in mode:
            return LocalFileObject(path.open(mode))
        if "w" in mode:
            return _LocalAtomicWriter(path)  # temp+rename で all-or-nothing
        raise ValueError(f"unsupported mode for LocalFileStore: {mode!r}")

    async def connect(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)

    async def aclose(self) -> None:
        return None


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


# ── S3 streaming file store（真のストリーミング＝全体バッファしない） ──


class _S3StreamReader:
    """`get_object` のストリーム body を read で逐次読み出す（全体をメモリに載せない）。

    body / client の接続は close まで開いたままにする（ストリームを跨いで読むため）。
    """

    def __init__(self, client_cm, client, body) -> None:
        self._client_cm = client_cm
        self._body = body

    async def read(self, size: int = -1) -> bytes:
        return await self._body.read() if size < 0 else await self._body.read(size)

    async def write(self, data: bytes) -> int:
        raise io.UnsupportedOperation("not writable")

    async def close(self) -> None:
        self._body.close()
        await self._client_cm.__aexit__(None, None, None)

    async def __aenter__(self) -> _S3StreamReader:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()


class _S3MultipartWriter:
    """書き込みを multipart upload でパート分割アップロードする（全体バッファしない）。

    `part_size` ごとに upload_part し、close で残りを最終パート（5MB 未満可）として送って
    complete する。1 バイトも書かれなければ空オブジェクトを単純 put する。
    """

    def __init__(self, base: _S3Base, key: str, part_size: int) -> None:
        self._base = base
        self._key = key
        self._part_size = part_size
        self._buf = bytearray()
        self._parts: list[dict] = []
        self._upload_id: str | None = None
        self._client_cm = None
        self._client = None
        self._closed = False

    async def read(self, size: int = -1) -> bytes:
        raise io.UnsupportedOperation("not readable")

    async def _start(self) -> None:
        self._client_cm = self._base._session()
        self._client = await self._client_cm.__aenter__()
        resp = await self._client.create_multipart_upload(Bucket=self._base._bucket, Key=self._key)
        self._upload_id = resp["UploadId"]

    async def _flush(self, size: int) -> None:
        chunk = bytes(self._buf[:size])
        del self._buf[:size]
        n = len(self._parts) + 1
        resp = await self._client.upload_part(
            Bucket=self._base._bucket,
            Key=self._key,
            PartNumber=n,
            UploadId=self._upload_id,
            Body=chunk,
        )
        self._parts.append({"PartNumber": n, "ETag": resp["ETag"]})

    async def write(self, data: bytes) -> int:
        if self._upload_id is None:
            await self._start()
        self._buf.extend(data)
        while len(self._buf) >= self._part_size:
            await self._flush(self._part_size)
        return len(data)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._upload_id is None:
            # 何も書かれていない → 空オブジェクトを単純 put（multipart は 0 パート不可）。
            cm = self._base._session()
            client = await cm.__aenter__()
            try:
                await client.put_object(Bucket=self._base._bucket, Key=self._key, Body=b"")
            finally:
                await cm.__aexit__(None, None, None)
            return
        try:
            if self._buf:
                await self._flush(len(self._buf))
            await self._client.complete_multipart_upload(
                Bucket=self._base._bucket,
                Key=self._key,
                UploadId=self._upload_id,
                MultipartUpload={"Parts": self._parts},
            )
        finally:
            await self._client_cm.__aexit__(None, None, None)

    async def __aenter__(self) -> _S3MultipartWriter:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()


class S3FileStore(_S3Base):
    """S3 の真のストリーミング [FileStore]（read=body 逐次 / write=multipart）。

    全体をメモリに載せる [KeyValueFileStore] と違い、大きなオブジェクトでも一定メモリで扱える。
    `part_size` は multipart の 1 パートサイズ（実 S3 は最終パート以外 5MB 以上が必要。既定 8MiB）。
    """

    def __init__(
        self,
        bucket: str,
        endpoint_url: str = "",
        region: str = "us-east-1",
        access_key: str = "",
        secret_key: str = "",
        part_size: int = 8 * 1024 * 1024,
    ) -> None:
        super().__init__(bucket, endpoint_url, region, access_key, secret_key)
        self._part_size = part_size

    async def open(self, filename: str, mode: str = "rb") -> FileObject:
        if "r" in mode:
            cm = self._session()
            client = await cm.__aenter__()
            resp = await client.get_object(Bucket=self._bucket, Key=filename)
            return _S3StreamReader(cm, client, resp["Body"])
        if "w" in mode:
            return _S3MultipartWriter(self, filename, self._part_size)
        raise ValueError(f"unsupported mode for S3FileStore: {mode!r}")


# ── NATS streaming file store ──


class _QueueSink:
    """NATS の `get(writeinto=...)` が呼ぶ sync な write 先。チャンクを Queue へ流す。"""

    def __init__(self, queue: asyncio.Queue) -> None:
        self._queue = queue

    def write(self, chunk: bytes) -> int:
        # get コルーチンと同じループ上から同期的に呼ばれる（put_nowait は同期で安全）。
        self._queue.put_nowait(bytes(chunk))
        return len(chunk)


class _NatsStreamReader:
    """背景の `get(writeinto=sink)` が Queue へ流すチャンクを read で逐次引く読み取り側。"""

    _EOF = None

    def __init__(self, queue: asyncio.Queue, task: asyncio.Future) -> None:
        self._queue = queue
        self._task = task
        self._leftover = b""
        self._eof = False

    async def _pull(self) -> bool:
        """次のチャンクを Queue から取り込む。EOF なら False。"""
        if self._eof:
            return False
        chunk = await self._queue.get()
        if chunk is self._EOF:
            self._eof = True
            return False
        self._leftover += chunk
        return True

    async def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            while await self._pull():
                pass
            out, self._leftover = self._leftover, b""
            return out
        while len(self._leftover) < size and await self._pull():
            pass
        out, self._leftover = self._leftover[:size], self._leftover[size:]
        return out

    async def write(self, data: bytes) -> int:
        raise io.UnsupportedOperation("not writable")

    async def close(self) -> None:
        if not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def __aenter__(self) -> _NatsStreamReader:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()


class _NatsBufferedWriter:
    """書き込みをバッファし、close 時に `put` する書き込み [FileObject]。

    nats-py の put は readable から sync 読みするため、async の write を pull させるには
    スレッド/パイプが要る。単一ループでは破綻するので、ここではバッファして close で put する
    （nats が wire 上でチャンク化して送る）。
    """

    def __init__(self, base: _NatsBase, name: str) -> None:
        self._base = base
        self._name = name
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
        obs = await self._base._get_obs()
        await obs.put(self._name, self._buf.getvalue())
        self._buf.close()

    async def __aenter__(self) -> _NatsBufferedWriter:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()


class NatsFileStore(_NatsBase):
    """NATS object store の [FileStore]（read=チャンク逐次配送 / write=close で put）。

    read は `get(writeinto=sink)` を背景タスクで走らせ、チャンクを逐次 read で引く（最初の
    バイトまでのレイテンシが低い）。nats writeinto は sync ＝ backpressure を掛けられないため、
    メモリは厳密には bounded でない（best-effort）。write は単一ループの制約上バッファして put。
    """

    async def open(self, filename: str, mode: str = "rb") -> FileObject:
        if "r" in mode:
            queue: asyncio.Queue = asyncio.Queue()
            task = asyncio.ensure_future(self._pump(filename, queue))
            return _NatsStreamReader(queue, task)
        if "w" in mode:
            return _NatsBufferedWriter(self, filename)
        raise ValueError(f"unsupported mode for NatsFileStore: {mode!r}")

    async def _pump(self, name: str, queue: asyncio.Queue) -> None:
        obs = await self._get_obs()
        try:
            await obs.get(name, writeinto=_QueueSink(queue))
        finally:
            queue.put_nowait(None)  # EOF sentinel

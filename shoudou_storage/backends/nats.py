"""nats backend — NATS JetStream Object Store（KVS / ストリーミング FileStore）。

nats-py はメソッド内で遅延 import する。read はチャンク逐次配送、write は close で put。
"""

import asyncio
import contextlib
import io
from collections.abc import AsyncIterator

from ..async_storage import FileInfo, FileObject, _kv_copy, _kv_move, _take


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


# ── ストリーミング FileStore ──


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

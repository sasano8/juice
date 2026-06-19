"""shoudou_storage のテスト（juice の test 群とは分離した同階層ディレクトリ）。

ストレージは将来 juice の外のライブラリとして抽出する想定のため、テストを `shoudou_storage`
パッケージと同階層の `tests_storage/` に置く（src/＋tests/ と同型。パッケージ dir はソースのみ＝
wheel にもテストが入らない）。juice の `make test`（testpaths=["tests"]）の対象外。
ここを直接 `pytest tests_storage/` で回す。
"""

from __future__ import annotations

import asyncio
import io
from pathlib import Path

import pytest

from shoudou_storage import (
    AsyncToSyncKeyValueStore,
    KeyValueFileStore,
    LocalFileStore,
    LocalKeyValueStore,
    NatsFileStore,
    S3FileStore,
    SafeFileStore,
    SafeKeyValueStore,
    UnsafePathError,
    validate_safe_path,
)


def test_async_to_sync_kvs_roundtrip(tmp_path: Path) -> None:
    # 非同期 KeyValueStore を同期ブリッジで被せ、ループ無しの同期コードから put/get できる。
    with AsyncToSyncKeyValueStore(LocalKeyValueStore(tmp_path)) as store:
        assert store.exists("a.txt") is False
        store.put("a.txt", b"hello")
        assert store.exists("a.txt") is True
        assert store.get("a.txt") == b"hello"
        assert store.get("missing.txt") is None
        store.put("b.txt", b"x")
        # iter は async ジェネレータを同期イテレータとして流す（名前降順）。
        assert [i["filename"] for i in store.iter()] == ["b.txt", "a.txt"]
        assert [i["filename"] for i in store.list(limit=1)] == ["b.txt"]
        store.delete("a.txt")
        assert store.exists("a.txt") is False


@pytest.mark.parametrize("good", ["a.txt", "dir/b.txt", "a/b/c.bin"])
def test_validate_safe_path_allows_relative(good: str) -> None:
    assert validate_safe_path(good) == good


@pytest.mark.parametrize(
    "bad",
    ["", "/etc/passwd", "../secret", "a/../../b", "a\\b", "x\x00y"],
)
def test_validate_safe_path_rejects_unsafe(bad: str) -> None:
    with pytest.raises(UnsafePathError):
        validate_safe_path(bad)


def test_safe_kvs_validates_before_delegating(tmp_path: Path) -> None:
    safe = SafeKeyValueStore(LocalKeyValueStore(tmp_path))
    # 正常キー（サブディレクトリ付き）は通り、委譲先に書かれる。
    asyncio.run(safe.put("ok/a.txt", b"hi"))
    assert asyncio.run(safe.get("ok/a.txt")) == b"hi"
    # 不正キーは委譲前に弾く。
    with pytest.raises(UnsafePathError):
        asyncio.run(safe.put("../evil", b"x"))
    with pytest.raises(UnsafePathError):
        asyncio.run(safe.get("/abs"))


def test_local_kvs_iter_and_list(tmp_path: Path) -> None:
    store = LocalKeyValueStore(tmp_path)

    async def scenario() -> None:
        for name in ("a", "b", "c"):
            await store.put(name, name.encode())
        # iter は全件を名前降順で yield する。
        names = [info["filename"] async for info in store.iter()]
        assert names == ["c", "b", "a"]
        # list は iter の先頭 limit 件。
        assert [i["filename"] for i in await store.list(limit=2)] == ["c", "b"]

    asyncio.run(scenario())


def test_local_file_store_open_write_read(tmp_path: Path) -> None:
    store = LocalFileStore(tmp_path)

    async def scenario() -> None:
        # 書き込みモードは親ディレクトリを作って open できる。
        async with await store.open("d/f.bin", "wb") as f:
            await f.write(b"hello")
        # 読み込みは open→read→（context manager で close）。
        async with await store.open("d/f.bin", "rb") as f:
            assert await f.read() == b"hello"

    asyncio.run(scenario())


def test_local_kvs_put_creates_parent_dirs(tmp_path: Path) -> None:
    store = LocalKeyValueStore(tmp_path)
    # '/' を含むキーは親ディレクトリを作って格納できる（s3/nats のフラットキー規約に整合）。
    asyncio.run(store.put("a/b/c.bin", b"data"))
    assert asyncio.run(store.get("a/b/c.bin")) == b"data"


def test_local_kvs_delete_removes_file_keeps_dirs(tmp_path: Path) -> None:
    store = LocalKeyValueStore(tmp_path)

    async def scenario() -> None:
        await store.put("a/b.txt", b"x")
        assert await store.exists("a/b.txt")
        await store.delete("a/b.txt")
        assert not await store.exists("a/b.txt")
        # ファイルだけ消す。親ディレクトリは残す。
        assert (tmp_path / "a").is_dir()
        # 無いキーの delete は無視（例外を投げない）。
        await store.delete("missing")

    asyncio.run(scenario())


def test_local_kvs_vacuum_removes_empty_dirs(tmp_path: Path) -> None:
    store = LocalKeyValueStore(tmp_path)

    async def scenario() -> None:
        await store.put("a/b/c.txt", b"x")
        await store.put("keep/d.txt", b"y")
        await store.delete("a/b/c.txt")  # a/b は空になるが delete は残す
        assert (tmp_path / "a" / "b").is_dir()
        await store.vacuum()
        # ネストした空ディレクトリ（a, a/b）は畳まれ、中身のある keep は残る。
        assert not (tmp_path / "a").exists()
        assert (tmp_path / "keep").is_dir()

    asyncio.run(scenario())


def test_local_kvs_cp_and_mv(tmp_path: Path) -> None:
    store = LocalKeyValueStore(tmp_path)

    async def scenario() -> None:
        await store.put("a.txt", b"hi")
        # cp は src を残して dst へ複製（dst のサブディレクトリも作る）。
        await store.cp("a.txt", "dir/b.txt")
        assert await store.get("a.txt") == b"hi"
        assert await store.get("dir/b.txt") == b"hi"
        # mv は src を消して dst へ（原子的 rename）。
        await store.mv("a.txt", "moved.txt")
        assert not await store.exists("a.txt")
        assert await store.get("moved.txt") == b"hi"
        # 無い src はエラー。
        with pytest.raises(FileNotFoundError):
            await store.cp("missing", "x")
        with pytest.raises(FileNotFoundError):
            await store.mv("missing", "x")

    asyncio.run(scenario())


def test_local_kvs_put_is_atomic(tmp_path: Path) -> None:
    store = LocalKeyValueStore(tmp_path)

    async def scenario() -> None:
        await store.put("k", b"v1")
        await store.put("k", b"v2")  # 原子的に差し替え
        assert await store.get("k") == b"v2"
        # 一時ファイルの残骸が無い（最終ファイルだけ）。
        assert [p.name for p in tmp_path.iterdir()] == ["k"]

    asyncio.run(scenario())


def test_local_file_store_write_is_atomic_on_error(tmp_path: Path) -> None:
    store = LocalFileStore(tmp_path)

    async def scenario() -> None:
        async with await store.open("k", "wb") as f:
            await f.write(b"old")
        # 書き込み中に例外 → 確定せず、既存値（old）が保たれる。
        with pytest.raises(RuntimeError):
            async with await store.open("k", "wb") as f:
                await f.write(b"new-partial")
                raise RuntimeError("boom")
        async with await store.open("k", "rb") as f:
            assert await f.read() == b"old"
        # 一時ファイルの残骸が無い。
        assert [p.name for p in tmp_path.iterdir()] == ["k"]

    asyncio.run(scenario())


def test_local_kvs_iter_is_recursive(tmp_path: Path) -> None:
    store = LocalKeyValueStore(tmp_path)

    async def scenario() -> None:
        await store.put("top.txt", b"1")
        await store.put("a/b/c.bin", b"2")
        # iter はサブディレクトリ配下のキーも相対 posix パスで列挙する。
        names = [info["filename"] async for info in store.iter()]
        assert names == ["top.txt", "a/b/c.bin"]  # 名前降順

    asyncio.run(scenario())


def test_key_value_file_store_open_over_kvs(tmp_path: Path) -> None:
    # KeyValueStore を FileStore として被せる（s3/nats も同型で FileStore 化できる）。
    fs = KeyValueFileStore(LocalKeyValueStore(tmp_path))

    async def scenario() -> None:
        async with await fs.open("k/v.bin", "wb") as f:
            await f.write(b"abc")
            await f.write(b"de")  # close 時にまとめて put
        async with await fs.open("k/v.bin", "rb") as f:
            assert await f.read() == b"abcde"
        # 無いキーの読み取りは FileNotFoundError。
        with pytest.raises(FileNotFoundError):
            await fs.open("missing", "rb")

    asyncio.run(scenario())


def test_safe_file_store_validates_filename(tmp_path: Path) -> None:
    safe = SafeFileStore(LocalFileStore(tmp_path))

    async def scenario() -> None:
        async with await safe.open("ok/a.bin", "wb") as f:
            await f.write(b"x")
        async with await safe.open("ok/a.bin", "rb") as f:
            assert await f.read() == b"x"
        with pytest.raises(UnsafePathError):
            await safe.open("../evil", "rb")

    asyncio.run(scenario())


def test_local_kvs_path_fixed_at_init(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 相対パスで初期化しても、初期化時の cwd を基準に絶対パスへ固定される。
    monkeypatch.chdir(tmp_path)
    (tmp_path / "store").mkdir()
    store = LocalKeyValueStore(Path("store"))
    asyncio.run(store.put("k", b"v"))
    # 実行中に cd しても、初期化時に固定したパスを参照する。
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.chdir(other)
    assert asyncio.run(store.get("k")) == b"v"
    assert (tmp_path / "store" / "k").read_bytes() == b"v"


# ── S3 streaming file store（fake S3 client で分割ロジックを検証） ──


class _FakeBody:
    def __init__(self, data: bytes) -> None:
        self._buf = io.BytesIO(data)

    async def read(self, size: int = -1) -> bytes:
        return self._buf.read() if size is None or size < 0 else self._buf.read(size)

    def close(self) -> None:
        self._buf.close()


class _FakeS3:
    """S3FileStore を駆動する最小のインメモリ fake（async client 兼 context manager）。"""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self._uploads: dict[str, dict] = {}
        self._uid = 0

    async def __aenter__(self) -> _FakeS3:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def create_multipart_upload(self, Bucket: str, Key: str) -> dict:
        self._uid += 1
        uid = f"u{self._uid}"
        self._uploads[uid] = {"key": Key, "parts": {}}
        return {"UploadId": uid}

    async def upload_part(self, Bucket, Key, PartNumber, UploadId, Body) -> dict:
        self._uploads[UploadId]["parts"][PartNumber] = bytes(Body)
        return {"ETag": f'"etag{PartNumber}"'}

    async def complete_multipart_upload(self, Bucket, Key, UploadId, MultipartUpload) -> dict:
        up = self._uploads.pop(UploadId)
        order = [p["PartNumber"] for p in MultipartUpload["Parts"]]
        self.objects[Key] = b"".join(up["parts"][n] for n in order)
        return {}

    async def put_object(self, Bucket, Key, Body) -> dict:
        self.objects[Key] = bytes(Body)
        return {}

    async def get_object(self, Bucket, Key) -> dict:
        return {"Body": _FakeBody(self.objects[Key])}


def test_s3_file_store_streams_multipart_write_and_read() -> None:
    fake = _FakeS3()
    store = S3FileStore("bucket", part_size=4)  # 小さなパートで分割を起こす
    store._session = lambda: fake  # 接続を fake に差し替え

    async def scenario() -> None:
        # 11 バイトを part_size=4 で書く → パート分割（4,4,3）して multipart upload。
        async with await store.open("k", "wb") as f:
            await f.write(b"hello world")
        assert fake.objects["k"] == b"hello world"
        assert len(fake._uploads) == 0  # complete 済み

        # ストリーム read（全体／chunk）。
        async with await store.open("k", "rb") as f:
            assert await f.read() == b"hello world"
        async with await store.open("k", "rb") as f:
            assert await f.read(5) == b"hello"
            assert await f.read() == b" world"

        # 空書き込みは空オブジェクトを put（multipart 0 パート不可）。
        async with await store.open("empty", "wb") as f:
            pass
        assert fake.objects["empty"] == b""

    asyncio.run(scenario())


# ── NATS streaming file store（fake object store でチャンク配送を検証） ──


class _FakeNatsObs:
    """NatsFileStore を駆動する最小の fake object store（get は writeinto へチャンク write）。"""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put(self, name: str, data) -> None:
        self.objects[name] = bytes(data)

    async def get(self, name: str, writeinto) -> None:
        data = self.objects[name]
        # 4 バイトずつ writeinto.write へ（nats のチャンク配送を模倣）。
        for i in range(0, len(data), 4):
            writeinto.write(data[i : i + 4])


def test_nats_file_store_streams_read_and_buffers_write() -> None:
    store = NatsFileStore("nats://x", "bucket")
    fake = _FakeNatsObs()

    async def fake_get_obs() -> _FakeNatsObs:
        return fake

    store._get_obs = fake_get_obs  # 接続を fake に差し替え

    async def scenario() -> None:
        # write はバッファして close で put。
        async with await store.open("k", "wb") as f:
            await f.write(b"hello")
            await f.write(b" world")
        assert fake.objects["k"] == b"hello world"

        # read は背景 get がチャンクを Queue へ流し、逐次引く（全体／chunk）。
        async with await store.open("k", "rb") as f:
            assert await f.read() == b"hello world"
        async with await store.open("k", "rb") as f:
            assert await f.read(5) == b"hello"
            assert await f.read() == b" world"

    asyncio.run(scenario())

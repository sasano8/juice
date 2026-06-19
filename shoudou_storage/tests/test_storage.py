"""shoudou_storage のテスト（パッケージ同梱・juice の test 群とは分離）。

ストレージは将来 juice の外のライブラリとして抽出する想定のため、テストもパッケージ配下に
置いて一緒に持ち出せるようにしている。juice の `make test`（testpaths=["tests"]）の対象外。
ここを直接 `pytest shoudou_storage/tests/` で回す。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from shoudou_storage import (
    AsyncToSyncKeyValueStore,
    KeyValueFileStore,
    LocalFileStore,
    LocalKeyValueStore,
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

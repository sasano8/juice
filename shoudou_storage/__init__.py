"""File store — save/get/list/exists files with swappable backends."""

from pathlib import Path
from typing import Protocol, TypedDict


class FileInfo(TypedDict):
    filename: str
    size: int


class FileStore(Protocol):
    async def save(self, filename: str, content: bytes) -> None: ...
    async def get(self, filename: str) -> bytes | None: ...
    async def list(self, limit: int = 10) -> list[FileInfo]: ...
    async def exists(self, filename: str) -> bool: ...


# ── Local filesystem ──


class LocalFileStore:
    def __init__(self, directory: Path) -> None:
        self._dir = directory
        self._dir.mkdir(parents=True, exist_ok=True)

    async def save(self, filename: str, content: bytes) -> None:
        (self._dir / filename).write_bytes(content)

    async def get(self, filename: str) -> bytes | None:
        path = self._dir / filename
        if not path.is_file():
            return None
        return path.read_bytes()

    async def list(self, limit: int = 10) -> list[FileInfo]:
        files = sorted(
            (f for f in self._dir.iterdir() if f.is_file()),
            key=lambda p: p.name,
            reverse=True,
        )
        return [FileInfo(filename=f.name, size=f.stat().st_size) for f in files[:limit]]

    async def exists(self, filename: str) -> bool:
        return (self._dir / filename).is_file()


# ── S3-compatible ──


class S3FileStore:
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

    async def save(self, filename: str, content: bytes) -> None:
        async with self._session() as client:
            await client.put_object(Bucket=self._bucket, Key=filename, Body=content)

    async def get(self, filename: str) -> bytes | None:
        async with self._session() as client:
            try:
                resp = await client.get_object(Bucket=self._bucket, Key=filename)
                async with resp["Body"] as stream:
                    return await stream.read()
            except client.exceptions.NoSuchKey:
                return None

    async def list(self, limit: int = 10) -> list[FileInfo]:
        async with self._session() as client:
            resp = await client.list_objects_v2(Bucket=self._bucket, MaxKeys=limit * 2)
            objects = resp.get("Contents", [])
            objects.sort(key=lambda o: o["Key"], reverse=True)
            return [FileInfo(filename=o["Key"], size=o["Size"]) for o in objects[:limit]]

    async def exists(self, filename: str) -> bool:
        async with self._session() as client:
            try:
                await client.head_object(Bucket=self._bucket, Key=filename)
                return True
            except Exception:
                return False


# ── NATS JetStream Object Store ──


class NatsObjectFileStore:
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

    async def save(self, filename: str, content: bytes) -> None:
        obs = await self._get_obs()
        await obs.put(filename, content)

    async def get(self, filename: str) -> bytes | None:
        obs = await self._get_obs()
        try:
            result = await obs.get(filename)
            return result.data
        except Exception:
            return None

    async def list(self, limit: int = 10) -> list[FileInfo]:
        obs = await self._get_obs()
        try:
            entries = await obs.list()
        except Exception:
            return []
        entries = [e for e in entries if not e.deleted]
        entries.sort(key=lambda e: e.name, reverse=True)
        return [FileInfo(filename=e.name, size=e.size or 0) for e in entries[:limit]]

    async def exists(self, filename: str) -> bool:
        obs = await self._get_obs()
        try:
            info = await obs.info(filename)
            return not info.deleted
        except Exception:
            return False


# ── Factory ──


def create_file_store(
    backend: str,
    local_dir: Path | None = None,
    s3_bucket: str = "",
    s3_endpoint: str = "",
    s3_region: str = "us-east-1",
    s3_access_key: str = "",
    s3_secret_key: str = "",
    nats_url: str = "",
    nats_bucket: str = "shoudou_files",
) -> FileStore:
    if backend == "local":
        return LocalFileStore(local_dir or Path("/app/data"))
    elif backend == "s3":
        return S3FileStore(
            bucket=s3_bucket,
            endpoint_url=s3_endpoint,
            region=s3_region,
            access_key=s3_access_key,
            secret_key=s3_secret_key,
        )
    elif backend == "nats":
        return NatsObjectFileStore(url=nats_url, bucket=nats_bucket)
    else:
        return LocalFileStore(local_dir or Path("/app/data"))

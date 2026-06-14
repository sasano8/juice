"""Storage / Registry の組み立て。

backend 名から Storage 実装を選ぶ単一の差し込み点。S3 等を足すときは
ここに分岐を追加する。
"""

from __future__ import annotations

from .config import Config
from .registry import Registry
from .storage import LocalStorage, Storage


def create_storage(config: Config) -> Storage:
    if config.backend == "local":
        return LocalStorage(root=config.root)
    raise NotImplementedError(f"backend not supported yet: {config.backend}")


def create_registry(config: Config | None = None) -> Registry:
    config = config or Config()
    return Registry(config, create_storage(config))

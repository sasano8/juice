"""Storage / Registry の組み立て。

backend 名から Storage 実装を選ぶ単一の差し込み点。S3 等を足すときはここに分岐を
追加する。既定のロケーション（bucket）やレイヤ別 path の解決もここが担う。
"""

from __future__ import annotations

from .config import ALL_ORDER, LAYERS, NAMESPACE_CONTAINER, Config
from .registry import Registry, RegistryArray
from .storage import LocalStorage, Storage

# 既定値。どこにレジストリがあるか／どの区画かの既定はここが持つ。
DEFAULT_BUCKET = "registries"
DEFAULT_NAMESPACE = "default"


def create_storage(config: Config) -> Storage:
    if config.backend == "local":
        # local は bucket/namespaces/namespace を基点にし、その配下の path（レイヤ）を引く。
        return LocalStorage(root=f"{config.bucket}/{NAMESPACE_CONTAINER}/{config.namespace}")
    raise NotImplementedError(f"backend not supported yet: {config.backend}")


def create_registry(config: Config) -> Registry:
    """1 つの Config から Registry（1 ロケーション）を組み立てる。"""
    return Registry(config, create_storage(config))


def create_registries(
    bucket: str | None = None,
    *,
    namespace: str | None = None,
    backend: str = "local",
    storage_option: dict[str, str] | None = None,
    overrides: dict[str, str] | None = None,
) -> RegistryArray:
    """ある namespace の全レイヤ分の Registry を組み立てて RegistryArray で束ねて返す。

    bucket / namespace を省略すると既定（DEFAULT_BUCKET / DEFAULT_NAMESPACE）を使う。
    各レイヤの path はここで解決し（overrides があれば優先）、解決済みの値だけを Config に渡す。
    """
    bucket = bucket or DEFAULT_BUCKET
    namespace = namespace or DEFAULT_NAMESPACE
    storage_option = storage_option or {}
    overrides = overrides or {}
    registries = {}
    for layer in ALL_ORDER:
        path = overrides.get(layer, LAYERS[layer])
        config = Config(
            backend=backend,
            storage_option=storage_option,
            bucket=bucket,
            namespace=namespace,
            path=path,
        )
        registries[layer] = create_registry(config)
    return RegistryArray(registries)

"""juice の Python API（core）。

CLI を含む利用側はこのパッケージ越しにレジストリを操作する。
Config/Storage/Registry の組み立ては `Juice` ファサードが隠蔽し、
``Juice().list("tool")`` のように最小手数で使えるようにする。
"""

from __future__ import annotations

from . import bundle as _bundle
from .apply import apply_manifest
from .config import ALL_ORDER, LAYERS, Config
from .factory import create_registries, create_registry, create_storage
from .lock import (
    Lock,
    LockError,
    build_lock,
    dump_lock,
    lock_status,
    write_lock,
)
from .manifest import (
    Manifest,
    ManifestError,
    load_manifest,
    parse_manifest,
)
from .registry import Registry, RegistryArray
from .semver import SemverError, Version, is_valid, parse_version, satisfies
from .storage import LocalStorage, Storage

__all__ = [
    "Juice",
    "Config",
    "Registry",
    "RegistryArray",
    "Storage",
    "LocalStorage",
    "LAYERS",
    "ALL_ORDER",
    "Manifest",
    "ManifestError",
    "parse_manifest",
    "load_manifest",
    "Lock",
    "LockError",
    "build_lock",
    "dump_lock",
    "write_lock",
    "lock_status",
    "apply_manifest",
    "Version",
    "SemverError",
    "parse_version",
    "is_valid",
    "satisfies",
    "create_registry",
    "create_registries",
    "create_storage",
]


class Juice:
    """juice の操作をまとめた API ファサード。

    bucket / namespace からレジストリ群（RegistryArray）を組み立て、レイヤ単位／全レイヤの
    一覧取得を提供する。出力整形（ラベル付けや並び）は呼び出し側（CLI 等）の責務とし、ここでは
    生データ（名前リスト）のみ返す。
    """

    def __init__(self, bucket: str | None = None, namespace: str | None = None) -> None:
        self.registries: RegistryArray = create_registries(bucket, namespace=namespace)

    def list(self, layer: str) -> list[str]:
        """単一レイヤのパッケージ名一覧を返す。"""
        return self.registries.list(layer)

    def list_all(self) -> dict[str, list[str]]:
        """全レイヤを依存順（ALL_ORDER）に並べた {レイヤ: 名前リスト} を返す。"""
        return self.registries.list_all()

    def apply(
        self,
        manifest_path: str,
        prune: bool = True,
        dry_run: bool = False,
        lock_path: str = "juice.lock",
        frozen: bool = False,
        require_lock: bool = False,
    ) -> dict:
        """juice.yaml を registries へ冪等反映する（C003）。

        juice.lock があれば manifest との drift を照合する（C005）: drift は既定で警告（結果の
        `warning`）、`frozen=True` ならエラー。`require_lock=True` で lock 不在をエラーにする。
        """
        manifest = load_manifest(manifest_path)
        warning = self._lock_guard(manifest, lock_path, frozen, require_lock)
        result = apply_manifest(self.registries, manifest, prune=prune, dry_run=dry_run)
        if warning:
            result["warning"] = warning
        return result

    def plan(
        self,
        manifest_path: str,
        prune: bool = True,
        lock_path: str = "juice.lock",
        frozen: bool = False,
        require_lock: bool = False,
    ) -> dict:
        """apply を書き込まず実行し、行われる変更（差分）を返す（C005）。"""
        return self.apply(
            manifest_path,
            prune=prune,
            dry_run=True,
            lock_path=lock_path,
            frozen=frozen,
            require_lock=require_lock,
        )

    def _lock_guard(self, manifest, lock_path: str, frozen: bool, require_lock: bool) -> str | None:
        """manifest と juice.lock の整合を確認する。drift 警告文を返す（無ければ None）。"""
        status = lock_status(manifest, lock_path)
        if not status["present"]:
            if require_lock:
                raise LockError(
                    f"juice.lock がありません（--require-lock）。"
                    f"`juice lock` を実行してください: {lock_path}"
                )
            return None
        if status["drift"]:
            msg = (
                f"juice.lock が manifest と一致しません（drift）。"
                f"`juice lock` で更新してください: {lock_path}"
            )
            if frozen:
                raise LockError(msg)
            return msg
        return None

    def init(self, name: str, clean: bool = False) -> dict:
        """宣言ファイル bundle.yml の雛形を生成し、生成物をクリーンする（既存なら要 clean）。"""
        return _bundle.init(self.registries, name, clean=clean)

    def bundle(self, name: str) -> dict:
        """内包物を vendoring し、build コンテキスト一式を生成する。"""
        return _bundle.bundle(self.registries, name)

    def build(self, name: str, image: str | None = None) -> dict:
        """docker イメージビルドコマンドを生成して返す（実行はしない）。"""
        return _bundle.build(self.registries, name, image)

    def run(
        self, name: str, mode: str = "api", image: str | None = None, env_file: str | None = None
    ) -> dict:
        """mode（api / ui / mcp_server）に応じた docker run コマンドを生成して返す。"""
        return _bundle.run(self.registries, name, mode, image, env_file)

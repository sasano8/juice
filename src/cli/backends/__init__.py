"""デプロイ先バックエンド（実起動の実行系）。

core/deploy は target ごとの成果物を**生成**する（純粋・冪等。`_WF_TARGETS` で target を分岐）。
本パッケージは生成済み成果物を各バックエンドへ**実起動**する実行系で、生成側の target に対応する
**実行側の seam**。新 target は generate（core/deploy）と apply（ここ）を対で追加する。
"""

from __future__ import annotations

from . import docker, k8s
from .base import run

# target -> 生成済み成果物を実起動する関数。core/deploy の _WF_TARGETS と対になる。
_APPLY = {
    "compose": lambda artifact, detach: docker.compose_up(artifact, detach=detach),
    "k8s": lambda artifact, detach: k8s.apply(artifact),  # k8s は宣言適用（detach 無し）
}


def apply_built(target: str, artifact: str, *, detach: bool = True) -> int:
    """生成済みデプロイ成果物 `artifact` を target のバックエンドで実起動する。"""
    try:
        backend = _APPLY[target]
    except KeyError:
        raise ValueError(
            f"未対応の target: {target}（対応: {', '.join(sorted(_APPLY))}）"
        ) from None
    return backend(artifact, detach)


__all__ = ["run", "apply_built", "docker", "k8s"]

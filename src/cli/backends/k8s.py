"""k8s バックエンド（manifests target の実起動）。

core/deploy が生成した `manifests.yaml`（Deployment / CronJob）を `kubectl apply` で適用する。
k8s は宣言適用なので detach 概念は無い（常に冪等 apply）。
"""

from __future__ import annotations

from . import base


def apply(artifact: str) -> int:
    """生成済み manifest を `kubectl apply -f <artifact>` で適用する。"""
    return base.run(f"kubectl apply -f {artifact}")

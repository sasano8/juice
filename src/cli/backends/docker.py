"""docker バックエンド（compose target の実起動）。

core/deploy が生成した `docker-compose.yml` を `docker compose` で実起動する。
bundle image の build / run は core が生成したコマンド文字列を `base.run` で実行するだけなので
（target 非依存）、ここには持たない。
"""

from __future__ import annotations

from . import base


def compose_up(artifact: str, *, detach: bool = True) -> int:
    """生成済み compose を `docker compose -f <artifact> up [-d]` で起動する。

    detach（既定）はスタック全体を背景起動（`-d`）。複数サービスの常駐スタックを
    一括で立ち上げるので `run`（単一サービスのワンショット）ではなく `up` を使う。
    """
    cmd = f"docker compose -f {artifact} up -d" if detach else f"docker compose -f {artifact} up"
    return base.run(cmd)

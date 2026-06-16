"""デプロイ先バックエンドの共通基盤（実起動の実行系）。

core/deploy は target ごとのデプロイ成果物を**生成**するだけ（純粋・冪等）。本パッケージは
生成済み成果物を各バックエンド（docker compose / k8s）へ**実起動**する実行系を担う。
生成（副作用なし）と実行（docker / kubectl を叩く）の分離を保つ層。
"""

from __future__ import annotations

import subprocess
import sys


def run(command: str) -> int:
    """コマンドを stderr にエコーして実行する（stdout は server I/O 用にクリーンに保つ）。

    実行ファイルが見つからなければ 127 を返し、導入を促すヒントを stderr に出す
    （docker / kubectl など未インストール環境でも CLI を壊さない）。
    """
    print(f"$ {command}", file=sys.stderr)
    try:
        return subprocess.call(command.split())
    except FileNotFoundError:
        tool = command.split(maxsplit=1)[0]
        print(f"{tool} not found (install it to build / run / deploy)", file=sys.stderr)
        return 127

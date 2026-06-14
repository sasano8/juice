"""juice CLI。

例:
    juice actor list
    juice instance list
各レイヤ配下のディレクトリ（= パッケージ）一覧を表示する。
"""

from __future__ import annotations

import argparse
import sys

from .config import ALL_ORDER, LAYERS, Config
from .factory import create_registry


def _cmd_list(registry, layer: str) -> int:
    names = registry.list(layer)
    if not names:
        print(f"(no {layer}s)", file=sys.stderr)
        return 0
    for name in names:
        print(name)
    return 0


def _cmd_all(registry) -> int:
    """全レイヤを依存順（ALL_ORDER）に一覧表示する。"""
    for layer in ALL_ORDER:
        print(f"== {LAYERS[layer]} ==")
        _cmd_list(registry, layer)
        print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="juice", description="AI エージェントのパッケージマネージャー")
    layer_subs = parser.add_subparsers(dest="layer", required=True, metavar="LAYER")

    layer_subs.add_parser("all", help="全レイヤを依存順に一覧表示する")

    for layer in LAYERS:
        lp = layer_subs.add_parser(layer, help=f"{layer} パッケージを操作する")
        action_subs = lp.add_subparsers(dest="action", required=True, metavar="ACTION")
        action_subs.add_parser("list", help=f"{layer} 一覧を表示する")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    registry = create_registry(Config())

    if args.layer == "all":
        return _cmd_all(registry)

    if args.action == "list":
        return _cmd_list(registry, args.layer)

    print(f"unknown action: {args.action}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

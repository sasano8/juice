"""juice CLI。

例:
    juice mcp_bundled list
    juice instance list
各レイヤ配下のディレクトリ（= パッケージ）一覧を表示する。
"""

from __future__ import annotations

import argparse
import sys

from ..core import LAYERS, Juice


def _print_names(names: list[str], layer: str) -> None:
    if not names:
        print(f"(no {layer}s)", file=sys.stderr)
        return
    for name in names:
        print(name)


def _cmd_list(juice: Juice, layer: str) -> int:
    _print_names(juice.list(layer), layer)
    return 0


def _cmd_all(juice: Juice) -> int:
    """全レイヤを依存順（ALL_ORDER）に一覧表示する。"""
    for layer, names in juice.list_all().items():
        print(f"== {LAYERS[layer]} ==")
        _print_names(names, layer)
        print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="juice", description="AI エージェントのパッケージマネージャー")
    layer_subs = parser.add_subparsers(dest="layer", required=True, metavar="LAYER")

    ap = layer_subs.add_parser("all", help="全レイヤを依存順に一覧表示する")
    ap_subs = ap.add_subparsers(dest="action", required=True, metavar="ACTION")
    ap_subs.add_parser("list", help="全レイヤ一覧を表示する")

    for layer in LAYERS:
        lp = layer_subs.add_parser(layer, help=f"{layer} パッケージを操作する")
        action_subs = lp.add_subparsers(dest="action", required=True, metavar="ACTION")
        action_subs.add_parser("list", help=f"{layer} 一覧を表示する")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    juice = Juice()

    if args.action == "list":
        if args.layer == "all":
            return _cmd_all(juice)
        return _cmd_list(juice, args.layer)

    print(f"unknown action: {args.action}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

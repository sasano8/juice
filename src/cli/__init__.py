"""juice CLI。

例:
    juice mcp_bundled list
    juice instance list
各レイヤ配下のディレクトリ（= パッケージ）一覧を表示する。
"""

from __future__ import annotations

import argparse
import sys

import yaml

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
        if layer == "mcp_bundled":
            bp = action_subs.add_parser("bundle", help="宣言ファイルを成果物名のスロットに登録する")
            bp.add_argument("-f", "--file", required=True, help="bundle 宣言ファイル（yml）")
            bp.add_argument("name", help="登録先の成果物名（mcp_bundled）")
            blp = action_subs.add_parser("build", help="登録済み宣言を参照し内包物をまとめてビルドする")
            blp.add_argument("name", help="ビルドする成果物名（mcp_bundled）")
            blp.add_argument("-n", "--namespace", default=None, help="namespace（既定: default）")

    return parser


def _cmd_bundle(path: str, name: str) -> int:
    """宣言ファイルで `name` をフルビルド（クリーンアップ→再配置→build）する。"""
    with open(path, encoding="utf-8") as f:
        spec_text = f.read()
    namespace = (yaml.safe_load(spec_text) or {}).get("namespace")
    result = Juice(namespace=namespace).bundle(name, spec_text)
    print(yaml.safe_dump(result, allow_unicode=True, sort_keys=False))
    return 0


def _cmd_build(name: str, namespace: str | None) -> int:
    """登録済み宣言を参照し vendor を最新化（再 vendoring）して YAML 出力する。"""
    result = Juice(namespace=namespace).build(name)
    print(yaml.safe_dump(result, allow_unicode=True, sort_keys=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.action == "list":
        juice = Juice()
        if args.layer == "all":
            return _cmd_all(juice)
        return _cmd_list(juice, args.layer)

    if args.action == "bundle":
        return _cmd_bundle(args.file, args.name)

    if args.action == "build":
        return _cmd_build(args.name, args.namespace)

    print(f"unknown action: {args.action}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

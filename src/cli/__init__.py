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
            ip = action_subs.add_parser("init", help="bundle.yml の雛形を生成して成果物を初期化する")
            ip.add_argument("name", help="成果物名（mcp_bundled）")
            ip.add_argument("-n", "--namespace", default=None, help="namespace（既定: default）")
            ip.add_argument("--clean", action="store_true", help="ディレクトリをクリーンアップして再初期化する")

            bp = action_subs.add_parser("bundle", help="内包物を vendoring し requirements/Dockerfile/entrypoint を生成する")
            bp.add_argument("name", help="成果物名（mcp_bundled）")
            bp.add_argument("-n", "--namespace", default=None, help="namespace（既定: default）")

            blp = action_subs.add_parser("build", help="docker でイメージをビルドする")
            blp.add_argument("name", help="成果物名（mcp_bundled）")
            blp.add_argument("-n", "--namespace", default=None, help="namespace（既定: default）")
            blp.add_argument("-t", "--tag", default=None, help="イメージタグ（既定: juice/<name>:latest）")

            rp = action_subs.add_parser("run", help="docker で mcp_server を起動する（stdio）")
            rp.add_argument("name", help="成果物名（mcp_bundled）")
            rp.add_argument("-n", "--namespace", default=None, help="namespace（既定: default）")
            rp.add_argument("-t", "--tag", default=None, help="イメージタグ（既定: juice/<name>:latest）")
            rp.add_argument("--build", action="store_true", help="run の前に build も実行する")

    return parser


def _cmd_init(name: str, namespace: str | None, clean: bool) -> int:
    """成果物 `name` の bundle.yml 雛形を生成して初期化する（既存なら要 --clean）。"""
    try:
        result = Juice(namespace=namespace).init(name, clean=clean)
    except FileExistsError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(yaml.safe_dump(result, allow_unicode=True, sort_keys=False))
    return 0


def _cmd_bundle(name: str, namespace: str | None) -> int:
    """内包物を vendoring し build コンテキストを生成して YAML 出力する。"""
    result = Juice(namespace=namespace).bundle(name)
    print(yaml.safe_dump(result, allow_unicode=True, sort_keys=False))
    return 0


def _exec(command: str) -> int:
    """コマンドを stderr にエコーして実行する（stdout は server I/O 用にクリーンに保つ）。"""
    import subprocess

    print(f"$ {command}", file=sys.stderr)
    try:
        return subprocess.call(command.split())
    except FileNotFoundError:
        print("docker not found (install docker to build/run)", file=sys.stderr)
        return 127


def _cmd_build(name: str, namespace: str | None, tag: str | None) -> int:
    """docker でイメージを実際にビルドする。"""
    return _exec(Juice(namespace=namespace).build(name, image=tag)["command"])


def _cmd_run(name: str, namespace: str | None, tag: str | None, build: bool) -> int:
    """docker で mcp_server を起動する（--build で事前に build も実行）。"""
    juice = Juice(namespace=namespace)
    if build:
        rc = _exec(juice.build(name, image=tag)["command"])
        if rc != 0:
            return rc
    return _exec(juice.run(name, image=tag)["command"])


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.action == "list":
        juice = Juice()
        if args.layer == "all":
            return _cmd_all(juice)
        return _cmd_list(juice, args.layer)

    if args.action == "init":
        return _cmd_init(args.name, args.namespace, args.clean)

    if args.action == "bundle":
        return _cmd_bundle(args.name, args.namespace)

    if args.action == "build":
        return _cmd_build(args.name, args.namespace, args.tag)

    if args.action == "run":
        return _cmd_run(args.name, args.namespace, args.tag, args.build)

    print(f"unknown action: {args.action}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

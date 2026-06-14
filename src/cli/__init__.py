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

from ..core import LAYERS, Juice, ManifestError, load_manifest, write_lock


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
    parser = argparse.ArgumentParser(
        prog="juice", description="AI エージェントのパッケージマネージャー"
    )
    layer_subs = parser.add_subparsers(dest="layer", required=True, metavar="LAYER")

    ap = layer_subs.add_parser("all", help="全レイヤを依存順に一覧表示する")
    ap_subs = ap.add_subparsers(dest="action", required=True, metavar="ACTION")
    ap_subs.add_parser("list", help="全レイヤ一覧を表示する")

    mp = layer_subs.add_parser("manifest", help="宣言的 manifest（juice.yaml）を扱う")
    mp_subs = mp.add_subparsers(dest="action", required=True, metavar="ACTION")
    vp = mp_subs.add_parser("validate", help="juice.yaml をパースして構造・参照を検証する")
    vp.add_argument(
        "-f", "--file", default="juice.yaml", help="manifest のパス（既定: juice.yaml）"
    )

    lp = layer_subs.add_parser("lock", help="juice.yaml を解決して juice.lock を冪等生成する")
    lp.add_argument(
        "-f", "--file", default="juice.yaml", help="manifest のパス（既定: juice.yaml）"
    )
    lp.add_argument("-o", "--out", default="juice.lock", help="出力先（既定: juice.lock）")

    for layer in LAYERS:
        lp = layer_subs.add_parser(layer, help=f"{layer} パッケージを操作する")
        action_subs = lp.add_subparsers(dest="action", required=True, metavar="ACTION")
        action_subs.add_parser("list", help=f"{layer} 一覧を表示する")
        if layer == "mcp_bundled":
            ip = action_subs.add_parser(
                "init", help="bundle.yml の雛形を生成して成果物を初期化する"
            )
            ip.add_argument("name", help="成果物名（mcp_bundled）")
            ip.add_argument("-n", "--namespace", default=None, help="namespace（既定: default）")
            ip.add_argument(
                "--clean",
                action="store_true",
                help="ディレクトリをクリーンアップして再初期化する",
            )

            bp = action_subs.add_parser(
                "bundle",
                help="内包物を vendoring し requirements/Dockerfile/entrypoint を生成する",
            )
            bp.add_argument("name", help="成果物名（mcp_bundled）")
            bp.add_argument("-n", "--namespace", default=None, help="namespace（既定: default）")

            blp = action_subs.add_parser("build", help="docker でイメージをビルドする")
            blp.add_argument("name", help="成果物名（mcp_bundled）")
            blp.add_argument("-n", "--namespace", default=None, help="namespace（既定: default）")
            blp.add_argument(
                "-t",
                "--tag",
                default=None,
                help="イメージタグ（既定: juice/<name>:latest）",
            )

            rp = action_subs.add_parser(
                "run", help="mode に応じてサービスを docker 起動する（api / ui / mcp_server）"
            )
            rp.add_argument("name", help="成果物名（mcp_bundled）")
            rp.add_argument(
                "mode",
                nargs="?",
                default="api",
                choices=["api", "ui", "mcp_server"],
                help="起動するサービス（既定: api）",
            )
            rp.add_argument("-n", "--namespace", default=None, help="namespace（既定: default）")
            rp.add_argument(
                "-t",
                "--tag",
                default=None,
                help="イメージタグ（既定: juice/<name>:latest）",
            )
            rp.add_argument("--build", action="store_true", help="run の前に build も実行する")
            rp.add_argument(
                "--bundle",
                action="store_true",
                help="run の前に bundle からやり直す（bundle→build→run）",
            )
            rp.add_argument(
                "--env-file",
                "--env",
                dest="env_file",
                default=None,
                help="docker の --env-file で読み込む .env パス（無ければスキップ）",
            )

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


def _cmd_run(
    name: str,
    mode: str,
    namespace: str | None,
    tag: str | None,
    build: bool,
    bundle: bool,
    env_file: str | None,
) -> int:
    """mode に応じてサービスを docker 起動する。

    --bundle: bundle からやり直す（bundle→build→run）。--build: build→run。
    --env-file: .env を docker に読ませる（無ければスキップ）。
    """
    import os

    juice = Juice(namespace=namespace)
    if env_file and not os.path.exists(env_file):
        print(f"(env-file skipped: {env_file} not found)", file=sys.stderr)
        env_file = None
    if bundle:
        result = juice.bundle(name)
        print(f"(bundle) regenerated {len(result.get('generated', []))} files", file=sys.stderr)
    if build or bundle:  # bundle 後はイメージ再ビルドが必要
        rc = _exec(juice.build(name, image=tag)["command"])
        if rc != 0:
            return rc
    return _exec(juice.run(name, mode=mode, image=tag, env_file=env_file)["command"])


def _cmd_manifest_validate(file: str) -> int:
    """juice.yaml をパース・検証し、要約を表示する（不正なら 1）。"""
    try:
        manifest = load_manifest(file)
    except ManifestError as e:
        print(f"invalid manifest: {e}", file=sys.stderr)
        return 1
    print(f"ok: {file} (apiVersion={manifest.api_version}, namespace={manifest.namespace})")
    for layer in ("mcp_servers", "subagents", "skills", "mcp_bundled", "instances"):
        names = manifest.names(layer)
        if names:
            print(f"  {layer}: {', '.join(names)}")
    return 0


def _cmd_lock(file: str, out: str) -> int:
    """juice.yaml を解決して juice.lock を生成する（不正なら 1）。"""
    try:
        result = write_lock(file, out)
    except ManifestError as e:
        print(f"invalid manifest: {e}", file=sys.stderr)
        return 1
    print(f"locked: {out} ({result['manifestDigest']})")
    for layer in ("mcp_servers", "instances"):
        if result[layer]:
            print(f"  {layer}: {', '.join(result[layer])}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.layer == "lock":
        return _cmd_lock(args.file, args.out)

    if args.layer == "manifest" and args.action == "validate":
        return _cmd_manifest_validate(args.file)

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
        return _cmd_run(
            args.name, args.mode, args.namespace, args.tag, args.build, args.bundle, args.env_file
        )

    print(f"unknown action: {args.action}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

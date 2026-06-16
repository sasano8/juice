"""workflow / schedule のデプロイ系 CLI ハンドラ。

生成（core/deploy）と実起動（cli/backends）を束ねる配線層。core は target ごとの成果物を
生成するだけ、backends がそれを各基盤（docker compose / k8s）へ実起動する。本モジュールは
両者をつなぐ薄い CLI ハンドラで、ビジネスロジックは持たない。
"""

from __future__ import annotations

import sys

from ..core import (
    Juice,
    ManifestError,
    is_vendored_workflow,
    load_manifest,
    write_deployment,
    write_schedule_deployment,
    write_vendored_workflow,
)
from . import backends
from ._errors import fail, fail_manifest


def _print_closure(closure: dict) -> None:
    """依存閉包（宣言 → 遡って解決した build 対象）を表示する。"""
    targets = closure.get("bundle", [])
    print(f"  build targets (bundle): {', '.join(targets) or '(none)'}")
    layers = ("subagent", "skill", "tool")
    deps = [f"{k}: {', '.join(closure[k])}" for k in layers if closure.get(k)]
    if deps:
        print(f"    ← deps  {'; '.join(deps)}")


def _build_deps(closure: dict) -> int:
    """依存閉包の bundle を宣言順に bundle→build まで起動する（docker）。rc を集約。"""
    juice = Juice()
    rc = 0
    for name in closure.get("bundle", []):
        gen = juice.bundle(name)
        print(f"(bundle) {name}: {len(gen.get('generated', []))} files", file=sys.stderr)
        r = backends.run(juice.build(name)["command"])
        if r != 0:
            rc = r
    return rc


def _build_workflow(name: str, file: str, out: str, target: str):
    """workflow のデプロイ成果物を生成し result dict を返す。失敗時は (None, rc)。

    registry に同梱 compose を持つ **vendored workflow**（終端・外部スタック）はそれを
    そのまま passthrough し、manifest は読まない。それ以外は manifest の steps から生成する。
    """
    juice = Juice()
    if is_vendored_workflow(juice.registries, name):
        if target != "compose":
            return None, fail(
                f"vendored workflow '{name}' は compose のみ（--target {target} は不可）"
            )
        return write_vendored_workflow(juice.registries, name, out_dir=out), 0
    try:
        manifest = load_manifest(file)
    except ManifestError as e:
        return None, fail_manifest(file, e)
    try:
        return write_deployment(manifest, name, out_dir=out, target=target), 0
    except KeyError:
        return None, fail(
            f"workflow が見つかりません: {name}（{file} に workflows で宣言してください）"
        )
    except ValueError as e:  # 未対応 target
        return None, fail(str(e))


def workflow_build(name: str, file: str, out: str, target: str, build_deps: bool) -> int:
    """workflow からデプロイ成果物（docker-compose.yml 等）を生成する（不正なら 1）。"""
    result, rc = _build_workflow(name, file, out, target)
    if result is None:
        return rc
    if result.get("vendored"):
        print(f"deployed (vendored): {result['out']} ({result['services']} services, 終端)")
    else:
        print(
            f"deployed: {result['out']} (target={result['target']}, {result['services']} services)"
        )
    _print_closure(result["closure"])
    return _build_deps(result["closure"]) if build_deps else 0


def workflow_apply(
    name: str, file: str, out: str, target: str, detach: bool, build_deps: bool
) -> int:
    """workflow を build してから target のバックエンドで実起動する（compose=up / k8s=apply）。

    生成は core（決定的・冪等）、実起動は backends（docker / kubectl）。`bundle run` と同型。
    """
    result, rc = _build_workflow(name, file, out, target)
    if result is None:
        return rc
    _print_closure(result["closure"])
    if build_deps and (rc := _build_deps(result["closure"])) != 0:
        return rc
    return backends.apply_built(target, result["out"], detach=detach)


def schedule_build(name: str, file: str, out: str, target: str, build_deps: bool) -> int:
    """schedule からデプロイ成果物（CronJob 等）を生成する（不正なら 1）。"""
    try:
        manifest = load_manifest(file)
    except ManifestError as e:
        return fail_manifest(file, e)
    try:
        result = write_schedule_deployment(manifest, name, out_dir=out, target=target)
    except KeyError:
        return fail(f"schedule が見つかりません: {name}（{file} に schedules で宣言してください）")
    except ValueError as e:  # 未対応 target
        return fail(str(e))
    print(f"deployed: {result['out']} (target={result['target']}, {result['services']} services)")
    _print_closure(result["closure"])
    return _build_deps(result["closure"]) if build_deps else 0

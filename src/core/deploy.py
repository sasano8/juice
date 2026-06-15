"""workflow のデプロイ成果物生成（E001 第二歩）。

juice は workflow を **実行しない**。workflow 宣言から、実行基盤（docker compose / 将来 k8s）が
食える**デプロイ成果物を生成**するに留める。常駐・協調・監視は外部基盤（`docker compose up` /
k8s＋ArgoCD 等）が担う。設計原則「宣言的＝spec から生成、生成物は焼かず再生成」に従う
（`apply` が registries を、`build` が image を生成するのと同型）。

- **mcp_bundled = image**（`bundle → build` で焼いた deployable な成果物）。
- **workflow = デプロイ宣言**。各 step が参照する mcp_bundled image を、実行基盤の単位
  （compose の service 等）へ写像し、長期常駐（`restart: unless-stopped`）させる成果物を生成する。
- **target は pluggable**：docker-compose（`compose`）と Kubernetes manifest（`k8s`）。

`build_deployment` は同じ Manifest からは常に同じ (ファイル名, テキスト) を返す（決定的・冪等）。
実起動・スケジューラ・並行制御は持たない（YAGNI。次段階）。
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .manifest import Manifest, McpBundledSpec, WorkflowSpec

# デプロイ成果物の既定の出力ルート（`deploy/<workflow>/<target ファイル>`）。
DEPLOY_DIR = "deploy"
DEFAULT_TARGET = "compose"

_HEADER = "# 生成物。手で編集しない（`juice workflow build` で再生成）。\n"


def find_workflow(manifest: Manifest, name: str) -> WorkflowSpec:
    """manifest から名前で workflow を引く。無ければ KeyError。"""
    for w in manifest.workflows:
        if w.name == name:
            return w
    raise KeyError(name)


def _image(bundle: McpBundledSpec) -> str:
    """mcp_bundled の image 名（規約 `juice/<name>`、version があれば tag を付ける）。"""
    base = f"juice/{bundle.name}"
    return f"{base}:{bundle.version}" if bundle.version else base


def build_compose(manifest: Manifest, workflow: WorkflowSpec) -> dict:
    """workflow を docker-compose（v2）の dict へ決定的に変換する。

    各 step（mcp_bundled 参照）を 1 service にし、image は規約名、`input` は環境変数、
    `schedule` は label に持たせる（compose に cron は無く外部スケジューラ用のメタ）。
    service は長期常駐（`restart: unless-stopped`）。同一 bundle の複数 step は連番で衝突を避ける。
    """
    bundles = {b.name: b for b in manifest.mcp_bundled}
    services: dict = {}
    used: dict[str, int] = {}
    for step in workflow.steps:
        bundle = bundles[step.mcp_bundled]  # parse 時に参照検証済み
        svc = step.mcp_bundled
        used[svc] = used.get(svc, 0) + 1
        if used[svc] > 1:
            svc = f"{svc}-{used[svc]}"
        service: dict = {"image": _image(bundle), "restart": "unless-stopped"}
        if step.input:
            service["environment"] = {k: str(v) for k, v in step.input.items()}
        labels = {"juice.workflow": workflow.name}
        if workflow.schedule:
            labels["juice.schedule"] = workflow.schedule
        service["labels"] = labels
        services[svc] = service
    return {"name": workflow.name, "services": services}


def _container(step_svc: str, bundle: McpBundledSpec, step_input: dict) -> dict:
    """k8s container spec（image／env）を組む。image は規約名、env は input を文字列化。"""
    container: dict = {"name": step_svc, "image": _image(bundle)}
    if step_input:
        container["env"] = [{"name": k, "value": str(v)} for k, v in step_input.items()]
    return container


def build_k8s(manifest: Manifest, workflow: WorkflowSpec) -> list[dict]:
    """workflow を Kubernetes manifest（複数リソース）へ決定的に変換する。

    `schedule` があれば各 step を CronJob、無ければ Deployment（長期常駐 replicas:1）にする。
    image/env/label は compose と揃える。出力は multi-doc YAML（ArgoCD 向け）。
    """
    bundles = {b.name: b for b in manifest.mcp_bundled}
    resources: list[dict] = []
    used: dict[str, int] = {}
    for step in workflow.steps:
        bundle = bundles[step.mcp_bundled]  # parse 時に参照検証済み
        svc = step.mcp_bundled
        used[svc] = used.get(svc, 0) + 1
        if used[svc] > 1:
            svc = f"{svc}-{used[svc]}"
        name = f"{workflow.name}-{svc}"
        pod_labels = {"app": svc, "juice.workflow": workflow.name}
        container = _container(svc, bundle, step.input)
        meta = {"name": name, "labels": {"juice.workflow": workflow.name}}
        if workflow.schedule:
            resources.append(
                {
                    "apiVersion": "batch/v1",
                    "kind": "CronJob",
                    "metadata": meta,
                    "spec": {
                        "schedule": workflow.schedule,
                        "jobTemplate": {
                            "spec": {
                                "template": {
                                    "metadata": {"labels": pod_labels},
                                    "spec": {
                                        "restartPolicy": "OnFailure",
                                        "containers": [container],
                                    },
                                }
                            }
                        },
                    },
                }
            )
        else:
            resources.append(
                {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "metadata": meta,
                    "spec": {
                        "replicas": 1,
                        "selector": {"matchLabels": {"app": svc}},
                        "template": {
                            "metadata": {"labels": pod_labels},
                            "spec": {"containers": [container]},
                        },
                    },
                }
            )
    return resources


def _dump(data, multi_doc: bool) -> str:
    """デプロイ成果物を決定的に直列化する（YAML＋生成物ヘッダ）。multi_doc なら複数ドキュメント。"""
    dumper = yaml.safe_dump_all if multi_doc else yaml.safe_dump
    body = dumper(data, sort_keys=False, allow_unicode=True, default_flow_style=False)
    return _HEADER + body


# target 名 -> (builder, 出力ファイル名, multi_doc)。新 target はここに足す。
_TARGETS: dict[str, tuple] = {
    "compose": (build_compose, "docker-compose.yml", False),
    "k8s": (build_k8s, "manifests.yaml", True),
}


def build_deployment(
    manifest: Manifest, workflow: WorkflowSpec, target: str = DEFAULT_TARGET
) -> tuple[str, str]:
    """(出力ファイル名, テキスト) を返す。target は pluggable（`compose` / `k8s`）。"""
    if target not in _TARGETS:
        raise ValueError(f"未対応の target: {target}（対応: {', '.join(_TARGETS)}）")
    builder, filename, multi_doc = _TARGETS[target]
    return filename, _dump(builder(manifest, workflow), multi_doc)


def write_deployment(
    manifest: Manifest,
    workflow_name: str,
    out_dir: str = DEPLOY_DIR,
    target: str = DEFAULT_TARGET,
) -> dict:
    """workflow のデプロイ成果物を `out_dir/<workflow>/<file>` に書き出す（冪等）。要約を返す。"""
    workflow = find_workflow(manifest, workflow_name)
    filename, text = build_deployment(manifest, workflow, target)
    dest = Path(out_dir) / workflow.name / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    return {"out": str(dest), "target": target, "services": len(workflow.steps)}

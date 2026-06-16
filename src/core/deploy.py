"""workflow / schedule のデプロイ成果物生成（E001）。

juice は実行しない。宣言から実行基盤が食える**デプロイ成果物を生成**するに留め、常駐・協調・監視・
定期実行は外部基盤（docker compose / k8s＋ArgoCD / 外部 cron）に委譲する（`apply`＝registries 生成、
`build`＝image 生成と同型）。**target は pluggable**（`compose` / `k8s`）。

定義（何を動かすか）とトリガ（いつ動かすか）を分ける（k8s の Deployment↔CronJob、Argo の
WorkflowTemplate↔CronWorkflow と同型）:

- **workflow = 常駐サービス群の定義**（時間非依存）。compose service（`restart: unless-stopped`）/
  k8s **Deployment**（replicas:1）として常駐させる。
- **schedule = 定期実行のトリガ**（cron を持つ）。k8s **CronJob** として生成。
  compose は cron 非対応なので自動起動しない one-shot service にする
  （`restart: "no"`＋`profiles: [scheduled]`、外部 cron が起動。cron は label）。

`build_*` は同じ Manifest からは常に同じ (ファイル名, テキスト) を返す（決定的・冪等）。
実起動・スケジューラ稼働・step 協調は持たない（YAGNI。生成のみ）。
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .manifest import BundleSpec, Manifest, ScheduleSpec, WorkflowSpec
from .registry import RegistryArray

DEPLOY_DIR = "deploy"
DEFAULT_TARGET = "compose"
# vendored workflow（終端：依存 bundle を持たず、compose を直に同梱）のファイル名。
VENDORED_COMPOSE = "docker-compose.yml"
_EMPTY_CLOSURE = {"bundle": [], "subagent": [], "skill": [], "tool": []}

_HEADER = "# 生成物。手で編集しない（`juice workflow build` / `juice schedule build` で再生成）。\n"


def find_workflow(manifest: Manifest, name: str) -> WorkflowSpec:
    """manifest から名前で workflow を引く。無ければ KeyError。"""
    for w in manifest.workflows:
        if w.name == name:
            return w
    raise KeyError(name)


def find_schedule(manifest: Manifest, name: str) -> ScheduleSpec:
    """manifest から名前で schedule を引く。無ければ KeyError。"""
    for s in manifest.schedules:
        if s.name == name:
            return s
    raise KeyError(name)


def dependency_closure(manifest: Manifest, steps: list) -> dict:
    """steps が参照する bundle と、その依存（subagent/skill/tool）を**遡って**解決する。

    返り値 `{bundle, subagent, skill, tool}`（各レイヤの名前リスト、宣言順・重複なし）。
    **ビルド対象は bundle**（`bundle` が subagent/skill/tool を vendoring して image 化）。
    「宣言 → 依存物を遡る」の起点になる。実 docker ビルドの起動はしない（呼び出し側の責務）。
    """
    bundles = {b.name: b for b in manifest.bundles}
    wanted: list[str] = []
    for st in steps:
        if st.bundle not in wanted:
            wanted.append(st.bundle)
    subagents: list[str] = []
    skills: list[str] = []
    tools: list[str] = []
    for name in wanted:
        b = bundles.get(name)
        if b is None:
            continue
        if b.subagent and b.subagent not in subagents:
            subagents.append(b.subagent)
        for sk in b.skills:
            if sk not in skills:
                skills.append(sk)
        for t in b.tools:
            if t.from_name not in tools:
                tools.append(t.from_name)
    return {"bundle": wanted, "subagent": subagents, "skill": skills, "tool": tools}


def is_vendored_workflow(registries: RegistryArray, name: str) -> bool:
    """workflow `name` が vendored（registry に `docker-compose.yml` を直に持つ終端）か。

    juice bundle を steps で組む生成型 workflow に対し、外部スタック（例: langfuse）を
    そのまま持つ終端 workflow。依存物（bundle）が無いので dependency_closure は空になる。
    """
    return registries.exists("workflow", name, VENDORED_COMPOSE)


def write_vendored_workflow(
    registries: RegistryArray, name: str, out_dir: str = DEPLOY_DIR
) -> dict:
    """vendored workflow の同梱 compose を生成せず deploy へ**そのまま passthrough** する。

    registry の `workflows/<name>/docker-compose.yml` を `out_dir/<name>/` へ写すだけ。
    終端なので closure は空。target は compose のみ（外部 compose を k8s 変換はしない）。
    """
    text = registries.read("workflow", name, VENDORED_COMPOSE)
    dest = Path(out_dir) / name / VENDORED_COMPOSE
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    data = yaml.safe_load(text)
    services = len(data.get("services", {})) if isinstance(data, dict) else 0
    return {
        "out": str(dest),
        "target": "compose",
        "vendored": True,
        "services": services,
        "closure": dict(_EMPTY_CLOSURE),
    }


def _image(bundle: BundleSpec) -> str:
    """bundle の image 名（規約 `juice/<name>`、version があれば tag を付ける）。"""
    base = f"juice/{bundle.name}"
    return f"{base}:{bundle.version}" if bundle.version else base


def _named_steps(steps: list):
    """(service 名, step) を決定的に列挙する。同一 bundle の複数 step は連番で衝突回避。"""
    used: dict[str, int] = {}
    for step in steps:
        svc = step.bundle
        used[svc] = used.get(svc, 0) + 1
        if used[svc] > 1:
            svc = f"{svc}-{used[svc]}"
        yield svc, step


def _env_list(step_input: dict) -> list[dict]:
    """input を k8s env（[{name, value}]）へ。値は文字列化。"""
    return [{"name": k, "value": str(v)} for k, v in step_input.items()]


def _container(svc: str, bundle: BundleSpec, step_input: dict) -> dict:
    container: dict = {"name": svc, "image": _image(bundle)}
    if step_input:
        container["env"] = _env_list(step_input)
    return container


# --- workflow（常駐サービス群） -------------------------------------------------


def build_compose(manifest: Manifest, workflow: WorkflowSpec) -> dict:
    """workflow を docker-compose（v2）の dict へ決定的に変換する（常駐 service）。

    step 間の協調＝**宣言順の直列 `depends_on`**（2 番目以降の service が直前の service に依存）。
    これは compose の意味での**起動順**であって「完了待ち」ではない（pipeline 的な完了待ち・
    データ受け渡しは別概念）。順序モデルは直列のみ（DAG は YAGNI）。単一 step には付かない。
    k8s（build_k8s）には depends_on 相当が無いので**順序を持たない**（Argo 等で別途）。
    """
    bundles = {b.name: b for b in manifest.bundles}
    services: dict = {}
    prev: str | None = None
    for svc, step in _named_steps(workflow.steps):
        service: dict = {"image": _image(bundles[step.bundle]), "restart": "unless-stopped"}
        if step.input:
            service["environment"] = {k: str(v) for k, v in step.input.items()}
        if prev is not None:
            service["depends_on"] = [prev]  # 宣言順の直列起動（直前の service に依存）
        service["labels"] = {"juice.workflow": workflow.name}
        services[svc] = service
        prev = svc
    return {"name": workflow.name, "services": services}


def build_k8s(manifest: Manifest, workflow: WorkflowSpec) -> list[dict]:
    """workflow を k8s Deployment（複数リソース）へ決定的に変換する（常駐 replicas:1）。"""
    bundles = {b.name: b for b in manifest.bundles}
    resources: list[dict] = []
    for svc, step in _named_steps(workflow.steps):
        pod_labels = {"app": svc, "juice.workflow": workflow.name}
        container = _container(svc, bundles[step.bundle], step.input)
        resources.append(
            {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {
                    "name": f"{workflow.name}-{svc}",
                    "labels": {"juice.workflow": workflow.name},
                },
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


# --- schedule（定期実行のトリガ） -----------------------------------------------


def build_schedule_compose(manifest: Manifest, schedule: ScheduleSpec) -> dict:
    """schedule を docker-compose へ。cron は無いので自動起動しない one-shot service にする。

    `restart: "no"`＋`profiles: [scheduled]`（`docker compose up` で勝手に起動しない）。
    cron 値は label に保持し、外部 cron が `docker compose run <svc>` で起動する想定。
    """
    bundles = {b.name: b for b in manifest.bundles}
    services: dict = {}
    for svc, step in _named_steps(schedule.steps):
        service: dict = {"image": _image(bundles[step.bundle]), "restart": "no"}
        if step.input:
            service["environment"] = {k: str(v) for k, v in step.input.items()}
        service["profiles"] = ["scheduled"]
        service["labels"] = {"juice.schedule": schedule.schedule, "juice.scheduled": schedule.name}
        services[svc] = service
    return {"name": schedule.name, "services": services}


def build_schedule_k8s(manifest: Manifest, schedule: ScheduleSpec) -> list[dict]:
    """schedule を k8s CronJob（複数リソース）へ決定的に変換する。"""
    bundles = {b.name: b for b in manifest.bundles}
    resources: list[dict] = []
    for svc, step in _named_steps(schedule.steps):
        pod_labels = {"app": svc, "juice.scheduled": schedule.name}
        resources.append(
            {
                "apiVersion": "batch/v1",
                "kind": "CronJob",
                "metadata": {
                    "name": f"{schedule.name}-{svc}",
                    "labels": {"juice.scheduled": schedule.name},
                },
                "spec": {
                    "schedule": schedule.schedule,
                    "jobTemplate": {
                        "spec": {
                            "template": {
                                "metadata": {"labels": pod_labels},
                                "spec": {
                                    "restartPolicy": "OnFailure",
                                    "containers": [
                                        _container(svc, bundles[step.bundle], step.input)
                                    ],
                                },
                            }
                        }
                    },
                },
            }
        )
    return resources


# --- target ディスパッチ / 書き出し ---------------------------------------------


def _dump(data, multi_doc: bool) -> str:
    """デプロイ成果物を決定的に直列化する（YAML＋生成物ヘッダ）。multi_doc なら複数ドキュメント。"""
    dumper = yaml.safe_dump_all if multi_doc else yaml.safe_dump
    body = dumper(data, sort_keys=False, allow_unicode=True, default_flow_style=False)
    return _HEADER + body


# target 名 -> (builder, 出力ファイル名, multi_doc)。新 target はここに足す。
_WF_TARGETS: dict[str, tuple] = {
    "compose": (build_compose, "docker-compose.yml", False),
    "k8s": (build_k8s, "manifests.yaml", True),
}
_SCHED_TARGETS: dict[str, tuple] = {
    "compose": (build_schedule_compose, "docker-compose.yml", False),
    "k8s": (build_schedule_k8s, "manifests.yaml", True),
}


def _build(manifest: Manifest, spec, target: str, targets: dict) -> tuple[str, str]:
    if target not in targets:
        raise ValueError(f"未対応の target: {target}（対応: {', '.join(targets)}）")
    builder, filename, multi_doc = targets[target]
    return filename, _dump(builder(manifest, spec), multi_doc)


def build_deployment(
    manifest: Manifest, workflow: WorkflowSpec, target: str = DEFAULT_TARGET
) -> tuple[str, str]:
    """workflow の (出力ファイル名, テキスト) を返す。target は `compose` / `k8s`。"""
    return _build(manifest, workflow, target, _WF_TARGETS)


def build_schedule_deployment(
    manifest: Manifest, schedule: ScheduleSpec, target: str = DEFAULT_TARGET
) -> tuple[str, str]:
    """schedule の (出力ファイル名, テキスト) を返す。target は `compose` / `k8s`。"""
    return _build(manifest, schedule, target, _SCHED_TARGETS)


def _write(out_dir: str, name: str, filename: str, text: str, target: str, count: int) -> dict:
    dest = Path(out_dir) / name / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    return {"out": str(dest), "target": target, "services": count}


def write_deployment(
    manifest: Manifest,
    workflow_name: str,
    out_dir: str = DEPLOY_DIR,
    target: str = DEFAULT_TARGET,
) -> dict:
    """workflow のデプロイ成果物を `out_dir/<name>/<file>` に冪等書き出し。要約を返す。"""
    workflow = find_workflow(manifest, workflow_name)
    filename, text = build_deployment(manifest, workflow, target)
    res = _write(out_dir, workflow.name, filename, text, target, len(workflow.steps))
    res["closure"] = dependency_closure(manifest, workflow.steps)
    return res


def write_schedule_deployment(
    manifest: Manifest,
    schedule_name: str,
    out_dir: str = DEPLOY_DIR,
    target: str = DEFAULT_TARGET,
) -> dict:
    """schedule のデプロイ成果物を `out_dir/<name>/<file>` に冪等書き出し。要約を返す。"""
    schedule = find_schedule(manifest, schedule_name)
    filename, text = build_schedule_deployment(manifest, schedule, target)
    res = _write(out_dir, schedule.name, filename, text, target, len(schedule.steps))
    res["closure"] = dependency_closure(manifest, schedule.steps)
    return res

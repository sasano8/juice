"""workflow / schedule デプロイ成果物生成（deploy.py / E001）のテスト。"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.core.deploy import (
    build_compose,
    build_deployment,
    build_k8s,
    build_schedule_compose,
    build_schedule_deployment,
    build_schedule_k8s,
    dependency_closure,
    find_schedule,
    find_workflow,
    is_vendored_workflow,
    write_deployment,
    write_schedule_deployment,
    write_vendored_workflow,
)
from src.core.manifest import parse_manifest

MANIFEST = """\
apiVersion: juice/v1
bundles:
  - name: mcp_weather-bot
    version: 0.0.1
  - name: news-bot
workflows:
  - name: live-bots
    steps:
      - bundle: mcp_weather-bot
        input:
          city: "Tokyo"
      - bundle: news-bot
schedules:
  - name: morning-brief
    schedule: "0 7 * * *"
    steps:
      - bundle: mcp_weather-bot
        input:
          city: "Tokyo"
"""


def _manifest():
    return parse_manifest(MANIFEST)


# --- workflow（常駐サービス群） -------------------------------------------------


def test_build_compose_structure():
    m = _manifest()
    compose = build_compose(m, find_workflow(m, "live-bots"))
    assert compose["name"] == "live-bots"
    svc = compose["services"]["mcp_weather-bot"]
    assert svc["image"] == "juice/mcp_weather-bot:0.0.1"  # version があれば tag
    assert svc["restart"] == "unless-stopped"  # 常駐
    assert svc["environment"] == {"city": "Tokyo"}  # input は環境変数
    assert svc["labels"] == {"juice.workflow": "live-bots"}
    assert "juice.schedule" not in svc["labels"]  # workflow は schedule を持たない


def test_build_compose_image_without_version():
    m = _manifest()
    compose = build_compose(m, find_workflow(m, "live-bots"))
    assert compose["services"]["news-bot"]["image"] == "juice/news-bot"


def test_build_compose_serial_depends_on():
    # step 間は宣言順の直列 depends_on（2 番目以降が直前に依存）。先頭は持たない。
    m = _manifest()
    services = build_compose(m, find_workflow(m, "live-bots"))["services"]
    assert "depends_on" not in services["mcp_weather-bot"]  # 先頭
    assert services["news-bot"]["depends_on"] == ["mcp_weather-bot"]  # 直前に依存


def test_build_compose_single_step_has_no_depends_on():
    m = parse_manifest(
        "apiVersion: juice/v1\n"
        "bundles:\n  - name: bot\n"
        "workflows:\n  - name: solo\n    steps:\n      - bundle: bot\n"
    )
    svc = build_compose(m, find_workflow(m, "solo"))["services"]["bot"]
    assert "depends_on" not in svc


def test_build_compose_depends_on_chains_numbered_services():
    # 同一 bundle の連番 service でも宣言順に決定的に連鎖する（bot → bot-2 → bot-3）。
    m = parse_manifest(
        "apiVersion: juice/v1\n"
        "bundles:\n  - name: bot\n"
        "workflows:\n  - name: w\n    steps:\n"
        "      - bundle: bot\n      - bundle: bot\n      - bundle: bot\n"
    )
    services = build_compose(m, find_workflow(m, "w"))["services"]
    assert "depends_on" not in services["bot"]
    assert services["bot-2"]["depends_on"] == ["bot"]
    assert services["bot-3"]["depends_on"] == ["bot-2"]


def test_k8s_and_schedule_have_no_depends_on():
    # depends_on は workflow/compose 限定。k8s（Deployment）と schedule には付かない。
    m = _manifest()
    for dep in build_k8s(m, find_workflow(m, "live-bots")):
        assert "depends_on" not in dep["spec"]
        assert "dependsOn" not in dep["spec"]
    sched = build_schedule_compose(m, find_schedule(m, "morning-brief"))
    assert all("depends_on" not in s for s in sched["services"].values())


def test_build_deployment_compose_filename_and_header():
    m = _manifest()
    filename, text = build_deployment(m, find_workflow(m, "live-bots"))
    assert filename == "docker-compose.yml"
    assert text.startswith("# 生成物")
    data = yaml.safe_load(text)
    assert set(data["services"]) == {"mcp_weather-bot", "news-bot"}


def test_build_deployment_is_deterministic():
    m = _manifest()
    assert build_deployment(m, find_workflow(m, "live-bots")) == build_deployment(
        m, find_workflow(m, "live-bots")
    )


def test_unknown_target_errors():
    m = _manifest()
    with pytest.raises(ValueError, match="未対応の target"):
        build_deployment(m, find_workflow(m, "live-bots"), target="nomad")


def test_find_workflow_missing():
    with pytest.raises(KeyError):
        find_workflow(_manifest(), "ghost")


def test_write_deployment_path_and_idempotent(tmp_path: Path):
    m = _manifest()
    out = str(tmp_path / "deploy")
    r1 = write_deployment(m, "live-bots", out_dir=out)
    assert r1["out"] == str(tmp_path / "deploy" / "live-bots" / "docker-compose.yml")
    assert r1["services"] == 2
    first = Path(r1["out"]).read_text(encoding="utf-8")
    write_deployment(m, "live-bots", out_dir=out)
    assert Path(r1["out"]).read_text(encoding="utf-8") == first  # 冪等


def test_duplicate_bundle_steps_get_unique_service_names():
    m = parse_manifest(
        "apiVersion: juice/v1\n"
        "bundles:\n  - name: bot\n"
        "workflows:\n  - name: w\n    steps:\n"
        "      - bundle: bot\n      - bundle: bot\n"
    )
    compose = build_compose(m, find_workflow(m, "w"))
    assert set(compose["services"]) == {"bot", "bot-2"}


def test_workflow_k8s_is_deployment():
    m = _manifest()
    docs = build_k8s(m, find_workflow(m, "live-bots"))
    assert {d["kind"] for d in docs} == {"Deployment"}
    dep = docs[0]
    assert dep["apiVersion"] == "apps/v1"
    assert dep["spec"]["replicas"] == 1
    assert dep["metadata"]["name"] == "live-bots-mcp_weather-bot"


# --- workflow lifecycle hooks（Helm 流・成果物に焼き込む） -----------------------

_HOOKS = """\
apiVersion: juice/v1
bundles:
  - name: bot
  - name: migrate
  - name: smoke
workflows:
  - name: svc
    hooks:
      - event: pre_deploy
        bundle: migrate
        input: {DB_URL: x}
      - event: post_deploy
        bundle: smoke
    steps:
      - bundle: bot
"""


def _hooks_manifest():
    return parse_manifest(_HOOKS)


def test_compose_pre_deploy_hook_gates_first_step():
    m = _hooks_manifest()
    services = build_compose(m, find_workflow(m, "svc"))["services"]
    # pre フックは one-shot（自動再起動しない）＋ juice.hook ラベル
    assert services["migrate"]["restart"] == "no"
    assert services["migrate"]["labels"]["juice.hook"] == "pre_deploy"
    assert services["migrate"]["environment"] == {"DB_URL": "x"}
    # 先頭 step は pre フックの「完了」を待つ（long 構文）
    assert services["bot"]["depends_on"] == {
        "migrate": {"condition": "service_completed_successfully"}
    }


def test_compose_post_deploy_hook_waits_for_step():
    m = _hooks_manifest()
    services = build_compose(m, find_workflow(m, "svc"))["services"]
    assert services["smoke"]["restart"] == "no"
    assert services["smoke"]["labels"]["juice.hook"] == "post_deploy"
    # post フックは本体 step の起動後に走る
    assert services["smoke"]["depends_on"] == {"bot": {"condition": "service_started"}}


def test_compose_output_order_pre_steps_post():
    m = _hooks_manifest()
    services = build_compose(m, find_workflow(m, "svc"))["services"]
    assert list(services) == ["migrate", "bot", "smoke"]


def test_k8s_hooks_are_jobs_around_deployment():
    m = _hooks_manifest()
    docs = build_k8s(m, find_workflow(m, "svc"))
    assert [(d["kind"], d["metadata"]["name"]) for d in docs] == [
        ("Job", "svc-migrate"),
        ("Deployment", "svc-bot"),
        ("Job", "svc-smoke"),
    ]
    pre = docs[0]
    assert pre["metadata"]["labels"]["juice.hook"] == "pre_deploy"
    assert pre["spec"]["template"]["spec"]["restartPolicy"] == "OnFailure"


def test_no_hooks_compose_unchanged():
    # フックが無ければ従来どおり（depends_on は短縮リスト、hook ラベル無し）。
    services = build_compose(_manifest(), find_workflow(_manifest(), "live-bots"))["services"]
    assert services["news-bot"]["depends_on"] == ["mcp_weather-bot"]
    assert "juice.hook" not in services["mcp_weather-bot"]["labels"]


def test_write_deployment_closure_includes_hook_bundles(tmp_path: Path):
    res = write_deployment(_hooks_manifest(), "svc", out_dir=str(tmp_path))
    assert res["hooks"] == 2
    # フックの bundle も build 対象（依存閉包）に含まれる（--build-deps 用）。
    assert set(res["closure"]["bundle"]) == {"bot", "migrate", "smoke"}


# --- vendored workflow（終端：外部 compose をそのまま同梱） ----------------------


def _put_vendored(bucket: str, name: str, body: str) -> None:
    wf = Path(bucket) / "namespaces" / "default" / "workflows" / name
    wf.mkdir(parents=True, exist_ok=True)
    (wf / "docker-compose.yml").write_text(body, encoding="utf-8")


def test_is_vendored_workflow_detects_compose(registries, bucket: str):
    assert not is_vendored_workflow(registries, "ghost")  # 無いものは False
    _put_vendored(bucket, "ext", "name: ext\nservices:\n  a:\n    image: nginx\n")
    assert is_vendored_workflow(registries, "ext")


def test_write_vendored_workflow_passthrough(registries, bucket: str, tmp_path: Path):
    _put_vendored(
        bucket, "ext", "name: ext\nservices:\n  a:\n    image: nginx\n  b:\n    image: redis\n"
    )
    out = str(tmp_path / "deploy")
    res = write_vendored_workflow(registries, "ext", out_dir=out)
    assert res["vendored"] is True
    assert res["services"] == 2
    assert res["closure"]["bundle"] == []  # 終端＝依存物なし（closure 空）
    # 生成せずそのまま写す（passthrough）。
    assert Path(res["out"]).read_text(encoding="utf-8").startswith("name: ext")


# --- schedule（定期実行のトリガ） -----------------------------------------------


def test_schedule_k8s_is_cronjob():
    m = _manifest()
    docs = build_schedule_k8s(m, find_schedule(m, "morning-brief"))
    assert {d["kind"] for d in docs} == {"CronJob"}
    cj = docs[0]
    assert cj["apiVersion"] == "batch/v1"
    assert cj["metadata"]["name"] == "morning-brief-mcp_weather-bot"
    assert cj["spec"]["schedule"] == "0 7 * * *"
    container = cj["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]
    assert container["image"] == "juice/mcp_weather-bot:0.0.1"
    assert container["env"] == [{"name": "city", "value": "Tokyo"}]


def test_schedule_compose_is_oneshot():
    m = _manifest()
    compose = build_schedule_compose(m, find_schedule(m, "morning-brief"))
    svc = compose["services"]["mcp_weather-bot"]
    assert svc["restart"] == "no"  # cron が無いので自動起動しない
    assert svc["profiles"] == ["scheduled"]
    assert svc["labels"]["juice.schedule"] == "0 7 * * *"
    assert svc["labels"]["juice.scheduled"] == "morning-brief"


def test_build_schedule_deployment_k8s_filename():
    m = _manifest()
    filename, text = build_schedule_deployment(m, find_schedule(m, "morning-brief"), target="k8s")
    assert filename == "manifests.yaml"
    docs = list(yaml.safe_load_all(text))
    assert [d["kind"] for d in docs] == ["CronJob"]


def test_write_schedule_deployment(tmp_path: Path):
    m = _manifest()
    out = str(tmp_path / "deploy")
    r = write_schedule_deployment(m, "morning-brief", out_dir=out, target="k8s")
    assert r["out"].endswith("deploy/morning-brief/manifests.yaml")
    assert r["target"] == "k8s"


def test_find_schedule_missing():
    with pytest.raises(KeyError):
        find_schedule(_manifest(), "ghost")


# --- 依存閉包（宣言 → 依存物を遡る） -------------------------------------------

_RICH = """\
apiVersion: juice/v1
mcp_servers:
  - name: weather
    command: npx -y @example/mcp-weather
subagents:
  - name: forecaster
    allow_tools: [weather]
skills:
  - name: report-weather
bundles:
  - name: mcp_weather-bot
    subagent: forecaster
    skills: [report-weather]
    tools:
      - bind: weather
        from: mcp_server:weather
schedules:
  - name: morning-brief
    schedule: "0 7 * * *"
    steps:
      - bundle: mcp_weather-bot
"""


def test_dependency_closure_traces_deps():
    m = parse_manifest(_RICH)
    closure = dependency_closure(m, find_schedule(m, "morning-brief").steps)
    # 宣言（schedule）→ bundle → subagent / skill / tool を遡って解決する。
    assert closure["bundle"] == ["mcp_weather-bot"]  # build 対象
    assert closure["subagent"] == ["forecaster"]
    assert closure["skill"] == ["report-weather"]
    assert closure["tool"] == ["weather"]


def test_write_deployment_includes_closure(tmp_path):
    m = parse_manifest(_RICH)
    r = write_schedule_deployment(m, "morning-brief", out_dir=str(tmp_path), target="k8s")
    assert r["closure"]["bundle"] == ["mcp_weather-bot"]

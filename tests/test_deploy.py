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
    write_deployment,
    write_schedule_deployment,
)
from src.core.manifest import parse_manifest

MANIFEST = """\
apiVersion: juice/v1
mcp_bundled:
  - name: weather-bot
    version: 0.0.1
  - name: news-bot
workflows:
  - name: live-bots
    steps:
      - mcp_bundled: weather-bot
        input:
          city: "Tokyo"
      - mcp_bundled: news-bot
schedules:
  - name: morning-brief
    schedule: "0 7 * * *"
    steps:
      - mcp_bundled: weather-bot
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
    svc = compose["services"]["weather-bot"]
    assert svc["image"] == "juice/weather-bot:0.0.1"  # version があれば tag
    assert svc["restart"] == "unless-stopped"  # 常駐
    assert svc["environment"] == {"city": "Tokyo"}  # input は環境変数
    assert svc["labels"] == {"juice.workflow": "live-bots"}
    assert "juice.schedule" not in svc["labels"]  # workflow は schedule を持たない


def test_build_compose_image_without_version():
    m = _manifest()
    compose = build_compose(m, find_workflow(m, "live-bots"))
    assert compose["services"]["news-bot"]["image"] == "juice/news-bot"


def test_build_deployment_compose_filename_and_header():
    m = _manifest()
    filename, text = build_deployment(m, find_workflow(m, "live-bots"))
    assert filename == "docker-compose.yml"
    assert text.startswith("# 生成物")
    data = yaml.safe_load(text)
    assert set(data["services"]) == {"weather-bot", "news-bot"}


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
        "mcp_bundled:\n  - name: bot\n"
        "workflows:\n  - name: w\n    steps:\n"
        "      - mcp_bundled: bot\n      - mcp_bundled: bot\n"
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
    assert dep["metadata"]["name"] == "live-bots-weather-bot"


# --- schedule（定期実行のトリガ） -----------------------------------------------


def test_schedule_k8s_is_cronjob():
    m = _manifest()
    docs = build_schedule_k8s(m, find_schedule(m, "morning-brief"))
    assert {d["kind"] for d in docs} == {"CronJob"}
    cj = docs[0]
    assert cj["apiVersion"] == "batch/v1"
    assert cj["metadata"]["name"] == "morning-brief-weather-bot"
    assert cj["spec"]["schedule"] == "0 7 * * *"
    container = cj["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]
    assert container["image"] == "juice/weather-bot:0.0.1"
    assert container["env"] == [{"name": "city", "value": "Tokyo"}]


def test_schedule_compose_is_oneshot():
    m = _manifest()
    compose = build_schedule_compose(m, find_schedule(m, "morning-brief"))
    svc = compose["services"]["weather-bot"]
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
mcp_bundled:
  - name: weather-bot
    subagent: forecaster
    skills: [report-weather]
    tools:
      - bind: weather
        from: mcp_server:weather
schedules:
  - name: morning-brief
    schedule: "0 7 * * *"
    steps:
      - mcp_bundled: weather-bot
"""


def test_dependency_closure_traces_deps():
    m = parse_manifest(_RICH)
    closure = dependency_closure(m, find_schedule(m, "morning-brief").steps)
    # 宣言（schedule）→ mcp_bundled → subagent / skill / tool を遡って解決する。
    assert closure["mcp_bundled"] == ["weather-bot"]  # build 対象
    assert closure["subagent"] == ["forecaster"]
    assert closure["skill"] == ["report-weather"]
    assert closure["tool"] == ["weather"]


def test_write_deployment_includes_closure(tmp_path):
    m = parse_manifest(_RICH)
    r = write_schedule_deployment(m, "morning-brief", out_dir=str(tmp_path), target="k8s")
    assert r["closure"]["mcp_bundled"] == ["weather-bot"]

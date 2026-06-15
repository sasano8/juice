"""workflow デプロイ成果物生成（deploy.py / E001 第二歩）のテスト。"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.core.deploy import (
    build_compose,
    build_deployment,
    find_workflow,
    write_deployment,
)
from src.core.manifest import parse_manifest

MANIFEST = """\
apiVersion: juice/v1
mcp_bundled:
  - name: weather-bot
    version: 0.0.1
  - name: news-bot
workflows:
  - name: morning-brief
    schedule: "0 7 * * *"
    steps:
      - mcp_bundled: weather-bot
        input:
          city: "Tokyo"
      - mcp_bundled: news-bot
"""


def _manifest():
    return parse_manifest(MANIFEST)


def test_build_compose_structure():
    m = _manifest()
    compose = build_compose(m, find_workflow(m, "morning-brief"))
    assert compose["name"] == "morning-brief"
    svc = compose["services"]["weather-bot"]
    assert svc["image"] == "juice/weather-bot:0.0.1"  # version があれば tag を付ける
    assert svc["restart"] == "unless-stopped"  # 長期常駐
    assert svc["environment"] == {"city": "Tokyo"}  # input は環境変数
    assert svc["labels"]["juice.workflow"] == "morning-brief"
    assert svc["labels"]["juice.schedule"] == "0 7 * * *"  # cron はメタとして label に


def test_build_compose_image_without_version():
    m = _manifest()
    compose = build_compose(m, find_workflow(m, "morning-brief"))
    # version 未指定の bundle は tag なしの規約名。
    assert compose["services"]["news-bot"]["image"] == "juice/news-bot"


def test_build_deployment_compose_filename_and_header():
    m = _manifest()
    filename, text = build_deployment(m, find_workflow(m, "morning-brief"))
    assert filename == "docker-compose.yml"
    assert text.startswith("# 生成物")
    # YAML として読め、services を 2 つ持つ。
    data = yaml.safe_load(text)
    assert set(data["services"]) == {"weather-bot", "news-bot"}


def test_build_deployment_is_deterministic():
    m = _manifest()
    a = build_deployment(m, find_workflow(m, "morning-brief"))
    b = build_deployment(m, find_workflow(m, "morning-brief"))
    assert a == b


def test_unknown_target_errors():
    m = _manifest()
    with pytest.raises(ValueError, match="未対応の target"):
        build_deployment(m, find_workflow(m, "morning-brief"), target="nomad")


def test_find_workflow_missing():
    with pytest.raises(KeyError):
        find_workflow(_manifest(), "ghost")


def test_write_deployment_path_and_idempotent(tmp_path: Path):
    m = _manifest()
    out = str(tmp_path / "deploy")
    r1 = write_deployment(m, "morning-brief", out_dir=out)
    assert r1["out"] == str(tmp_path / "deploy" / "morning-brief" / "docker-compose.yml")
    assert r1["services"] == 2
    first = Path(r1["out"]).read_text(encoding="utf-8")
    write_deployment(m, "morning-brief", out_dir=out)
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

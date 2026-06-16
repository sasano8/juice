"""メタデータインデックス生成と drift 検出（index.py / E004 要件 4）のテスト。"""

from __future__ import annotations

from pathlib import Path

from src.core import create_registries
from src.core.index import INDEX_VERSION, build_index, dump_index, index_status, write_index


def test_build_index_structure(registries) -> None:
    index = build_index(registries)
    assert index["indexVersion"] == INDEX_VERSION
    assert index["namespace"] == "default"
    assert index["digest"].startswith("sha256:")
    # 最小レジストリは tool/subagent/skill/mcp_bundled の 4 つ。
    names = {(p["layer"], p["dir"]) for p in index["packages"]}
    assert ("tool", "weather") in names
    assert ("mcp_bundled", "weather-bot") in names
    weather = next(p for p in index["packages"] if p["dir"] == "weather")
    assert weather["metadata"]["name"] == "weather"


def test_write_index_is_idempotent(registries, tmp_path: Path) -> None:
    out = str(tmp_path / "juice.index.yml")
    write_index(registries, out)
    first = Path(out).read_text(encoding="utf-8")
    write_index(registries, out)
    second = Path(out).read_text(encoding="utf-8")
    assert first == second
    assert first.startswith("# juice.index.yml")


def test_index_status_absent(registries, tmp_path: Path) -> None:
    status = index_status(registries, str(tmp_path / "nope.yml"))
    assert status["present"] is False
    assert status["drift"] is False
    assert status["found"] is None


def test_index_status_clean_after_write(registries, tmp_path: Path) -> None:
    out = str(tmp_path / "juice.index.yml")
    write_index(registries, out)
    status = index_status(registries, out)
    assert status["present"] is True
    assert status["drift"] is False
    assert status["found"] == status["expected"]


def test_index_status_detects_drift(bucket: str, tmp_path: Path) -> None:
    registries = create_registries(bucket=bucket, namespace="default")
    out = str(tmp_path / "juice.index.yml")
    write_index(registries, out)
    # registry 側に新パッケージを足すと index と drift する。
    new = Path(bucket) / "namespaces" / "default" / "skills" / "extra" / "SKILL.md"
    new.parent.mkdir(parents=True, exist_ok=True)
    new.write_text("---\nkind: skill\nname: extra\n---\n", encoding="utf-8")
    fresh = create_registries(bucket=bucket, namespace="default")
    status = index_status(fresh, out)
    assert status["present"] is True
    assert status["drift"] is True


def test_dump_index_deterministic(registries) -> None:
    a = dump_index(build_index(registries))
    b = dump_index(build_index(registries))
    assert a == b

"""Registry / RegistryArray のテスト。"""

from __future__ import annotations

from src.core import ALL_ORDER, RegistryArray


def test_list_single_layer(registries: RegistryArray) -> None:
    assert registries.list("tool") == ["weather"]
    assert registries.list("subagent") == ["forecaster"]
    assert registries.list("bundle") == ["mcp_weather-bot"]


def test_list_empty_layer(registries: RegistryArray) -> None:
    # workflow / instance は未配置なので空
    assert registries.list("workflow") == []
    assert registries.list("instance") == []


def test_list_all_preserves_all_order(registries: RegistryArray) -> None:
    result = registries.list_all()
    assert list(result.keys()) == ALL_ORDER


def test_namespace_property(registries: RegistryArray) -> None:
    assert registries.namespace == "default"


def test_read_entry_file_default(registries: RegistryArray) -> None:
    # 既定エントリ（tool -> index.md）を読む
    text = registries.read("tool", "weather")
    assert "kind: tool" in text


def test_exists(registries: RegistryArray) -> None:
    assert registries.exists("tool", "weather")
    assert not registries.exists("tool", "weather", "missing.py")


def test_list_files_of_package(registries: RegistryArray) -> None:
    assert registries.list_files("tool", "weather") == ["index.md", "server.py"]


def test_location_is_physical_path(registries: RegistryArray, bucket: str) -> None:
    loc = registries.location("tool", "weather")
    assert loc == f"{bucket}/namespaces/default/tools/weather"
    loc_entry = registries.location("tool", "weather", "server.py")
    assert loc_entry == f"{bucket}/namespaces/default/tools/weather/server.py"


def test_write_and_remove_roundtrip(registries: RegistryArray) -> None:
    registries.write("tool", "weather", "extra.txt", "hi")
    assert registries.exists("tool", "weather", "extra.txt")
    registries.remove("tool", "weather", "extra.txt")
    assert not registries.exists("tool", "weather", "extra.txt")

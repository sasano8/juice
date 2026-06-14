"""LocalStorage の挙動テスト。"""

from __future__ import annotations

from pathlib import Path

from src.core import LocalStorage


def test_list_dirs_returns_sorted_names(tmp_path: Path) -> None:
    for name in ("b", "a", "c"):
        (tmp_path / name).mkdir()
    (tmp_path / "file.txt").write_text("x", encoding="utf-8")
    storage = LocalStorage(root=tmp_path)
    # ディレクトリのみ・名前順
    assert storage.list_dirs("") == ["a", "b", "c"]


def test_list_dirs_missing_path_returns_empty(tmp_path: Path) -> None:
    storage = LocalStorage(root=tmp_path)
    assert storage.list_dirs("nope") == []


def test_write_then_read_roundtrip_creates_parents(tmp_path: Path) -> None:
    storage = LocalStorage(root=tmp_path)
    storage.write_text("deep/nested/file.txt", "こんにちは")
    assert storage.exists("deep/nested/file.txt")
    assert storage.read_text("deep/nested/file.txt") == "こんにちは"


def test_list_files_recursive_relative_sorted(tmp_path: Path) -> None:
    storage = LocalStorage(root=tmp_path)
    storage.write_text("pkg/a.txt", "a")
    storage.write_text("pkg/sub/b.txt", "b")
    assert storage.list_files("pkg") == ["a.txt", "sub/b.txt"]


def test_remove_file_and_dir(tmp_path: Path) -> None:
    storage = LocalStorage(root=tmp_path)
    storage.write_text("pkg/a.txt", "a")
    storage.remove("pkg/a.txt")
    assert not storage.exists("pkg/a.txt")
    # ディレクトリは再帰削除
    storage.write_text("dir/x/y.txt", "y")
    storage.remove("dir")
    assert not storage.exists("dir")
    # 無いパスの remove は無視
    storage.remove("missing")

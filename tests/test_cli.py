"""CLI のテスト。

list 系は読み取り専用なのでリポジトリ同梱の実レジストリ（registries/default）に対して
実行する。init/bundle/build/run の中身は test_bundle.py で tmp レジストリを使って検証済み。
"""

from __future__ import annotations

import pytest

from src.cli import _print_names, build_parser, main


def test_parser_requires_layer() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_parser_all_list() -> None:
    args = build_parser().parse_args(["all", "list"])
    assert args.layer == "all"
    assert args.action == "list"


def test_parser_run_defaults_to_api() -> None:
    args = build_parser().parse_args(["mcp_bundled", "run", "weather-bot"])
    assert args.action == "run"
    assert args.mode == "api"


def test_parser_run_rejects_unknown_mode() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["mcp_bundled", "run", "weather-bot", "bogus"])


def test_main_tool_list(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["tool", "list"])
    assert rc == 0
    out = capsys.readouterr().out.splitlines()
    assert "weather" in out


def test_main_all_list_prints_labels(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["all", "list"])
    assert rc == 0
    out = capsys.readouterr().out
    # 全レイヤのラベル見出しが出る
    assert "== tools ==" in out
    assert "== mcp_bundled ==" in out
    assert "weather-bot" in out


def test_main_instance_list(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["instance", "list"])
    assert rc == 0
    assert "tokyo-weather-bot" in capsys.readouterr().out.splitlines()


def test_main_manifest_validate_ok(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / "juice.yaml"
    p.write_text("apiVersion: juice/v1\nskills:\n  - name: report-weather\n", encoding="utf-8")
    rc = main(["manifest", "validate", "-f", str(p)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ok:" in out
    assert "report-weather" in out


def test_main_manifest_validate_reports_error(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / "juice.yaml"
    p.write_text("apiVersion: juice/v2\n", encoding="utf-8")
    rc = main(["manifest", "validate", "-f", str(p)])
    assert rc == 1
    assert "invalid manifest" in capsys.readouterr().err


_MANIFEST = """\
apiVersion: juice/v1
mcp_servers:
  - name: weather
    package: "@example/mcp-weather"
mcp_bundled:
  - name: weather-bot
    tools:
      - bind: weather
        from: mcp_server:weather
instances:
  - name: tokyo-weather-bot
    mcp_bundled: weather-bot
"""


def test_main_lock_writes_idempotent_file(tmp_path) -> None:
    src = tmp_path / "juice.yaml"
    src.write_text(_MANIFEST, encoding="utf-8")
    out = tmp_path / "juice.lock"

    rc = main(["lock", "-f", str(src), "-o", str(out)])
    assert rc == 0
    first = out.read_text(encoding="utf-8")
    assert first.startswith("# juice.lock")

    # 再実行してもバイト単位で同一（冪等）。
    rc = main(["lock", "-f", str(src), "-o", str(out)])
    assert rc == 0
    assert out.read_text(encoding="utf-8") == first


def test_main_lock_reports_error(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    src = tmp_path / "juice.yaml"
    src.write_text("apiVersion: juice/v2\n", encoding="utf-8")
    rc = main(["lock", "-f", str(src), "-o", str(tmp_path / "juice.lock")])
    assert rc == 1
    assert "invalid manifest" in capsys.readouterr().err


def test_parser_apply_flags() -> None:
    args = build_parser().parse_args(
        ["apply", "-f", "juice.yaml", "--dry-run", "--no-prune", "--frozen"]
    )
    assert args.layer == "apply"
    assert args.dry_run is True
    assert args.prune is False
    assert args.frozen is True
    assert args.lock == "juice.lock"


def test_parser_plan_flags() -> None:
    args = build_parser().parse_args(["plan", "-f", "j.yaml", "--lock", "j.lock", "--require-lock"])
    assert args.layer == "plan"
    assert args.lock == "j.lock"
    assert args.require_lock is True
    # plan には --dry-run は無い（常に dry-run）。
    assert not hasattr(args, "dry_run")


def test_toplevel_help_shows_workflow_examples() -> None:
    help_text = build_parser().format_help()
    assert "juice manifest validate" in help_text
    assert "juice lock" in help_text
    assert "juice apply" in help_text


@pytest.mark.parametrize(
    "argv,needle",
    [
        (["lock", "-h"], "juice lock -f juice.yaml -o juice.lock"),
        (["plan", "-h"], "juice plan -f juice.yaml"),
        (["apply", "-h"], "juice apply -f juice.yaml --dry-run"),
        (["manifest", "validate", "-h"], "juice manifest validate -f juice.yaml"),
    ],
)
def test_subcommand_help_has_example(argv, needle, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(argv)
    assert needle in capsys.readouterr().out


def test_main_apply_reports_error(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    # 不正な manifest は registries に触れる前に弾かれる（実レジストリ非依存）。
    src = tmp_path / "juice.yaml"
    src.write_text("apiVersion: juice/v2\n", encoding="utf-8")
    rc = main(["apply", "-f", str(src)])
    assert rc == 1
    assert "invalid manifest" in capsys.readouterr().err


def test_error_includes_file_path_and_hint(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / "juice.yaml"
    p.write_text("apiVersion: juice/v2\n", encoding="utf-8")
    rc = main(["manifest", "validate", "-f", str(p)])
    assert rc == 1
    err = capsys.readouterr().err
    assert str(p) in err  # どのファイルで失敗したか
    assert "ヒント" in err  # 次の一手


def test_missing_file_error_has_hint(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["manifest", "validate", "-f", str(tmp_path / "nope.yaml")])
    assert rc == 1
    err = capsys.readouterr().err
    assert "見つかりません" in err
    assert "ヒント" in err


def test_yaml_syntax_error_reports_line(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / "juice.yaml"
    p.write_text("apiVersion: [unclosed\n", encoding="utf-8")  # 壊れた flow sequence
    rc = main(["manifest", "validate", "-f", str(p)])
    assert rc == 1
    assert "line" in capsys.readouterr().err  # PyYAML の行情報が出る


def test_print_names_empty_reports_to_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    _print_names([], "instance")
    captured = capsys.readouterr()
    # 空リストは stdout を汚さず stderr に通知する
    assert captured.out.strip() == ""
    assert "no instance" in captured.err

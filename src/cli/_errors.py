"""CLI 共通のエラー報告（stderr ＋ 次の一手ヒント）。

cli/__init__ と cli/deploy が共有する。失敗は stderr に出して exit code 1 を返すのが共通経路。
"""

from __future__ import annotations

import sys

from ..core import ManifestError


def fail(msg: str) -> int:
    """エラーを stderr に出して exit code 1 を返す（CLI 失敗の共通経路）。"""
    print(msg, file=sys.stderr)
    return 1


def hint(message: str) -> str:
    """よくある失敗に「次の一手」のヒントを添える（無ければ空）。"""
    if "見つかりません" in message:
        return "\n  ヒント: パスを確認してください（-f でファイルを指定）。"
    if "apiVersion" in message:
        return "\n  ヒント: 対応する apiVersion は juice/v1 です。"
    if "YAML として解釈できません" in message:
        return "\n  ヒント: インデントや記号など YAML 構文を確認してください。"
    return ""


def fail_manifest(file: str, e: ManifestError) -> int:
    """manifest エラーをファイルパス＋ヒント付きで報告する。"""
    return fail(f"invalid manifest ({file}): {e}{hint(str(e))}")

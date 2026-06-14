"""最小限の SemVer（Semantic Versioning）ユーティリティ（C004）。

外部依存を足さず、`major.minor.patch`（任意で `-prerelease`）のパース・比較・単純な制約判定だけを
自前で持つ。まずは**検証**（妥当な SemVer か）を最優先とし、依存解決（範囲マッチや複数版共存）は
別タスクに切り出す（YAGNI）。

- `parse_version("1.0.0-rc.1")` … `Version` を返す。不正は `SemverError`。
- 比較は SemVer の優先順位に従う（prerelease 付きは無印より小さい）。
- `satisfies("1.2.3", ">=1.0.0")` … 単一制約（`==` / `>=` / `>` / `<=` / `<`、無印は `==`）の判定。

build metadata（`+...`）は当面サポートしない（必要になってから）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import total_ordering

# major.minor.patch（各々 leading zero 禁止）＋任意の prerelease。
_VERSION_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*))?$"
)

_OPERATORS = ("==", ">=", "<=", ">", "<")


class SemverError(ValueError):
    """SemVer として不正な文字列を渡されたときに投げる。"""


@total_ordering
@dataclass(frozen=True)
class Version:
    """SemVer のバージョン。prerelease は識別子のタプル（無ければ空）。"""

    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...] = ()

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        return f"{base}-{'.'.join(self.prerelease)}" if self.prerelease else base

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self._key() == other._key()

    def __lt__(self, other: Version) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self._key() < other._key()

    def __hash__(self) -> int:
        return hash((self.major, self.minor, self.patch, self.prerelease))

    def _key(self) -> tuple:
        # コア（major.minor.patch）を比較し、同値なら prerelease で比較する。
        # prerelease 無し（リリース）は prerelease 有りより大きい（= 後ろ）。
        return (self.major, self.minor, self.patch, _PrereleaseKey(self.prerelease))


@total_ordering
class _PrereleaseKey:
    """prerelease の SemVer 優先順位比較。無印を最大に、識別子は数値<英数で比較する。"""

    def __init__(self, ids: tuple[str, ...]) -> None:
        self.ids = ids

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, _PrereleaseKey):
            return NotImplemented
        return self.ids == other.ids

    def __lt__(self, other: _PrereleaseKey) -> bool:
        # prerelease 無しは「大きい」。両方無印は等しい（上の __eq__ が処理）。
        if not self.ids:
            return False
        if not other.ids:
            return True
        for a, b in zip(self.ids, other.ids, strict=False):
            if a == b:
                continue
            an, bn = a.isdigit(), b.isdigit()
            if an and bn:
                return int(a) < int(b)
            if an != bn:
                return an  # 数値識別子は英数識別子より低い優先度（小さい）
            return a < b
        return len(self.ids) < len(other.ids)  # 全て一致なら短い方が小さい


def parse_version(text: str) -> Version:
    """SemVer 文字列を `Version` にパースする。不正なら `SemverError`。"""
    if not isinstance(text, str):
        raise SemverError(f"version は文字列である必要があります（got {type(text).__name__}）")
    m = _VERSION_RE.match(text.strip())
    if not m:
        raise SemverError(f"SemVer として不正です: {text!r}（例: 1.2.3 / 1.0.0-rc.1）")
    major, minor, patch, pre = m.groups()
    prerelease = tuple(pre.split(".")) if pre else ()
    return Version(int(major), int(minor), int(patch), prerelease)


def is_valid(text: str) -> bool:
    """SemVer として妥当なら True。"""
    try:
        parse_version(text)
        return True
    except SemverError:
        return False


def satisfies(version: str, constraint: str) -> bool:
    """`version` が単一制約 `constraint` を満たすか判定する。

    制約は `==` / `>=` / `<=` / `>` / `<` のいずれか（演算子なしは `==` 扱い）。
    """
    v = parse_version(version)
    op, target = _split_constraint(constraint)
    t = parse_version(target)
    if op == "==":
        return v == t
    if op == ">=":
        return v >= t
    if op == "<=":
        return v <= t
    if op == ">":
        return v > t
    if op == "<":
        return v < t
    raise SemverError(f"未対応の制約演算子です: {op}")  # 到達しない


def _split_constraint(constraint: str) -> tuple[str, str]:
    s = constraint.strip()
    for op in _OPERATORS:  # 2 文字演算子を先に判定（== / >= / <=）
        if s.startswith(op):
            return op, s[len(op) :].strip()
    return "==", s

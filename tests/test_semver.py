"""SemVer ユーティリティ（semver）のテスト（C004）。"""

from __future__ import annotations

import pytest

from src.core.semver import SemverError, Version, is_valid, parse_version, satisfies


def test_parse_basic():
    v = parse_version("1.2.3")
    assert (v.major, v.minor, v.patch, v.prerelease) == (1, 2, 3, ())
    assert str(v) == "1.2.3"


def test_parse_prerelease():
    v = parse_version("1.0.0-rc.1")
    assert v.prerelease == ("rc", "1")
    assert str(v) == "1.0.0-rc.1"


@pytest.mark.parametrize(
    "bad",
    ["1.2", "1.2.3.4", "v1.2.3", "01.2.3", "1.2.3-", "1.2.x", "", "1.2.-3"],
)
def test_parse_invalid(bad):
    assert not is_valid(bad)
    with pytest.raises(SemverError):
        parse_version(bad)


def test_ordering_core():
    assert parse_version("1.0.0") < parse_version("1.0.1")
    assert parse_version("1.2.0") < parse_version("2.0.0")
    assert parse_version("1.2.3") == parse_version("1.2.3")


def test_prerelease_precedence():
    # prerelease 付きはリリースより小さい。
    assert parse_version("1.0.0-rc.1") < parse_version("1.0.0")
    # 数値識別子は英数識別子より小さい。
    assert parse_version("1.0.0-1") < parse_version("1.0.0-alpha")
    # 識別子数が少ない方が小さい（前方一致時）。
    assert parse_version("1.0.0-alpha") < parse_version("1.0.0-alpha.1")


def test_sorting():
    versions = ["1.0.0", "1.0.0-rc.1", "1.0.0-rc.2", "0.9.9", "2.0.0"]
    ordered = sorted(versions, key=parse_version)
    assert ordered == ["0.9.9", "1.0.0-rc.1", "1.0.0-rc.2", "1.0.0", "2.0.0"]


@pytest.mark.parametrize(
    "version,constraint,expected",
    [
        ("1.2.3", "1.2.3", True),
        ("1.2.3", "==1.2.3", True),
        ("1.2.3", ">=1.0.0", True),
        ("1.2.3", ">=2.0.0", False),
        ("1.2.3", ">1.2.3", False),
        ("1.2.3", "<=1.2.3", True),
        ("1.2.3", "<2.0.0", True),
    ],
)
def test_satisfies(version, constraint, expected):
    assert satisfies(version, constraint) is expected


def test_version_is_hashable():
    assert len({parse_version("1.0.0"), parse_version("1.0.0"), parse_version("1.0.1")}) == 2


def test_version_dataclass_equality():
    assert Version(1, 0, 0) == parse_version("1.0.0")

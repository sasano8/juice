"""registry パッケージのメタデータ抽出と name 検証（E004 の第一歩）。

各レイヤのエントリファイル（[config.py](config.py) の `ENTRY_FILES`）からメタデータを取り出す。
2 形式を扱う:
- **md frontmatter**（tool / subagent / skill / workflow）… 先頭 `---` で囲んだ YAML ブロック。
- **純 YAML**（bundle の bundle.yml / instance の index.yml）… ファイル全体が YAML。

E004 の核となる検証を 2 つ提供する:
- **name 検証**（`verify_names`）… メタデータの `name` がディレクトリ名に一致するか。
- **OKF 適合検証**（`verify_okf`）… .md concept document が OKF 必須の `type` を持つか。
いずれも **検出して報告するだけ**で自動修正はしない（コピー流用か移動かを機械判断できないため、
人間に修正を委ねる）。メタデータインデックス（高速化）は [index.py](index.py) を参照。
"""

from __future__ import annotations

from dataclasses import dataclass

import yaml

from .config import ENTRY_FILES, LAYERS
from .registry import RegistryArray

# OKF（Open Knowledge Format, Google Cloud v0.1）は **.md の concept document** に非空の
# `type` フィールドを必須とする（推奨フィールド title/description/resource/tags/timestamp は任意）。
# juice では .md をエントリにするレイヤ（tool / skill / subagent / workflow）が OKF の対象。
# bundle / instance は純 YAML の juice マニフェスト（apiVersion/kind ＝ k8s 流儀）で、
# OKF の .md concept document ではないため対象外。
OKF_MD_LAYERS: list[str] = [layer for layer, f in ENTRY_FILES.items() if f.endswith(".md")]


def parse_metadata(text: str) -> dict:
    """エントリファイルのテキストからメタデータ dict を取り出す。

    先頭が `---` なら frontmatter ブロックを、そうでなければ全体を YAML として読む。
    解釈できない・dict でない場合は空 dict を返す（検証側で `name` 欠落として扱える）。
    """
    s = text.lstrip("﻿")  # BOM があれば落とす
    block = _frontmatter_block(s) if s.startswith("---") else s
    try:
        data = yaml.safe_load(block)
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def _frontmatter_block(s: str) -> str:
    """先頭 `---` 〜 次の `---` の間（YAML ブロック）を返す。閉じが無ければ空。"""
    lines = s.splitlines()
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[1:i])
    return ""  # 閉じフェンス無し → frontmatter として不成立


def extract_name(text: str) -> str | None:
    """メタデータの `name` を返す（無ければ None）。"""
    name = parse_metadata(text).get("name")
    return name if isinstance(name, str) else None


@dataclass
class NameIssue:
    """name 検証で見つかった不一致。"""

    layer: str  # 単数形レイヤ名（tool / subagent / ...）
    dir_name: str  # registry 上のディレクトリ名（= あるべき name）
    declared: str | None  # メタデータに宣言された name（無ければ None）
    reason: str  # "missing"（name 欠落）/ "mismatch"（dir と不一致）

    def message(self) -> str:
        loc = f"{LAYERS[self.layer]}/{self.dir_name}"
        if self.reason == "missing":
            return f"{loc}: メタデータに name がありません（'{self.dir_name}' を指定してください）"
        return (
            f"{loc}: name '{self.declared}' がディレクトリ名 '{self.dir_name}' と一致しません"
            f"（コピー流用や移動の可能性。手で修正してください）"
        )


def verify_names(registries: RegistryArray) -> list[NameIssue]:
    """全レイヤの各パッケージで `name` とディレクトリ名の一致を検証する。

    不一致（name 欠落 / dir と不一致）を列挙して返す。自動修正はしない。
    """
    issues: list[NameIssue] = []
    for layer in LAYERS:
        for dir_name in registries.list(layer):
            declared = extract_name(registries.read(layer, dir_name))
            if declared is None:
                issues.append(NameIssue(layer, dir_name, None, "missing"))
            elif declared != dir_name:
                issues.append(NameIssue(layer, dir_name, declared, "mismatch"))
    return issues


@dataclass
class OkfIssue:
    """OKF 適合検証で見つかった不備（concept type の欠落）。"""

    layer: str  # 単数形レイヤ名（tool / subagent / ...）
    dir_name: str  # registry 上のディレクトリ名
    declared_type: str | None  # 宣言された type（欠落・非文字列・空なら None）

    def message(self) -> str:
        loc = f"{LAYERS[self.layer]}/{self.dir_name}"
        return (
            f"{loc}: OKF 必須の `type`（concept type）がありません"
            f"（例: '{self.layer}' を frontmatter に指定してください）"
        )


def verify_okf(registries: RegistryArray) -> list[OkfIssue]:
    """.md concept document（OKF 対象レイヤ）が非空の `type` を持つか検証する。

    OKF v0.1 の適合規則「非予約 .md は非空の `type` を持つ」を確認する。欠落を列挙して返す。
    自動修正はしない（[verify_names] と同方針＝人間に委ねる）。純 YAML マニフェスト
    （bundle / instance）は OKF の .md concept document ではないため検査対象外。
    """
    issues: list[OkfIssue] = []
    for layer in OKF_MD_LAYERS:
        for dir_name in registries.list(layer):
            declared = parse_metadata(registries.read(layer, dir_name)).get("type")
            if not isinstance(declared, str) or not declared.strip():
                kept = declared if isinstance(declared, str) else None
                issues.append(OkfIssue(layer, dir_name, kept))
    return issues

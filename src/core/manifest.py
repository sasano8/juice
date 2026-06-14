"""宣言的ワークスペース manifest（juice.yaml）のパーサ。

`juice.yaml` は「何を・どう結線するか」を 1 ファイルで宣言する唯一の正
（source of truth）。全レイヤ（mcp_server / subagent / skill / mcp_bundled / instance）を
名前参照で結線する（設計は docs/workspace.md を参照）。

このモジュールは manifest を **型付きの構造（Manifest）へパースし、構造と相互参照を検証**する
ところまでを担う。依存解決（lock）や registries/ への反映（apply）は後続レイヤ（C002 / C003）の
責務で、ここには持ち込まない（層の分離・YAGNI）。検証エラーは `ManifestError` で、どのフィールド／
どの名前が問題かを含めて投げる。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .semver import SemverError, parse_version

# このパーサが解釈する manifest のスキーマ版。
API_VERSION = "juice/v1"
DEFAULT_NAMESPACE = "default"

# `from: mcp_server:weather` の取り込み元として現在サポートする型。
SUPPORTED_BIND_KINDS = ("mcp_server",)


class ManifestError(ValueError):
    """manifest の構造・参照が不正なときに投げる。"""


@dataclass
class McpServerSpec:
    """能力の提供元（最下層）。command/env を宣言するだけで命令的ビルドはしない。"""

    name: str
    package: str | None = None
    command: str | None = None
    env: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    version: str | None = None  # 任意。SemVer（不正なら parse 時に弾く）


@dataclass
class SubagentSpec:
    """標準フォーマット（Claude Code 準拠）の subagent 宣言。"""

    name: str
    model: str | None = None
    allow_tools: list[str] = field(default_factory=list)
    prompt: str | None = None
    version: str | None = None


@dataclass
class SkillSpec:
    """手順（skill）の宣言。"""

    name: str
    description: str | None = None
    version: str | None = None


@dataclass
class ToolBinding:
    """mcp_bundled が mcp_server の tool を結線する 1 本の束縛。"""

    bind: str  # bundle 内での tool 名
    from_kind: str  # 取り込み元の型（現状は "mcp_server"）
    from_name: str  # 取り込み元リソース名
    env: list[str] = field(default_factory=list)  # 値は書かず env 名の参照のみ


@dataclass
class McpBundledSpec:
    """集約層：subagent + skill + mcp_server(tool) を結線する。"""

    name: str
    subagent: str | None = None
    skills: list[str] = field(default_factory=list)
    tools: list[ToolBinding] = field(default_factory=list)
    version: str | None = None


@dataclass
class InstanceSpec:
    """具象：mcp_bundled に変数既定値を与えた deployable な実個体。"""

    name: str
    mcp_bundled: str
    defaults: dict = field(default_factory=dict)
    secrets: dict = field(default_factory=dict)


@dataclass
class Manifest:
    """juice.yaml 全体。全レイヤを保持する。"""

    api_version: str
    namespace: str
    mcp_servers: list[McpServerSpec] = field(default_factory=list)
    subagents: list[SubagentSpec] = field(default_factory=list)
    skills: list[SkillSpec] = field(default_factory=list)
    mcp_bundled: list[McpBundledSpec] = field(default_factory=list)
    instances: list[InstanceSpec] = field(default_factory=list)

    def names(self, layer: str) -> list[str]:
        """指定レイヤ（複数形キー）に含まれるリソース名の一覧を返す。"""
        items = getattr(self, layer)
        return [item.name for item in items]


# --- パース本体 ---------------------------------------------------------------


def parse_manifest(text: str) -> Manifest:
    """juice.yaml のテキストをパースし、構造と相互参照を検証して Manifest を返す。

    不正があれば最初に見つかった問題で `ManifestError` を投げる。
    """
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as e:  # YAML 自体が壊れている
        raise ManifestError(f"YAML として解釈できません: {e}") from e

    if raw is None:
        raise ManifestError("manifest が空です")
    if not isinstance(raw, dict):
        raise ManifestError(
            f"manifest のトップレベルはマッピングである必要があります（got {type(raw).__name__}）"
        )

    api_version = raw.get("apiVersion")
    if not api_version:
        raise ManifestError("apiVersion が必要です")
    if api_version != API_VERSION:
        raise ManifestError(f"未対応の apiVersion: {api_version}（対応: {API_VERSION}）")

    namespace = raw.get("namespace") or DEFAULT_NAMESPACE
    if not isinstance(namespace, str):
        raise ManifestError(
            f"namespace は文字列である必要があります（got {type(namespace).__name__}）"
        )

    manifest = Manifest(
        api_version=api_version,
        namespace=namespace,
        mcp_servers=[_parse_mcp_server(it) for it in _items(raw, "mcp_servers")],
        subagents=[_parse_subagent(it) for it in _items(raw, "subagents")],
        skills=[_parse_skill(it) for it in _items(raw, "skills")],
        mcp_bundled=[_parse_mcp_bundled(it) for it in _items(raw, "mcp_bundled")],
        instances=[_parse_instance(it) for it in _items(raw, "instances")],
    )
    _validate(manifest)
    return manifest


def load_manifest(path: str | Path) -> Manifest:
    """ファイルパスから juice.yaml を読み込んでパースする。"""
    p = Path(path)
    if not p.exists():
        raise ManifestError(f"manifest が見つかりません: {p}")
    return parse_manifest(p.read_text(encoding="utf-8"))


# --- レイヤ毎のパース ----------------------------------------------------------


def _parse_mcp_server(item: dict) -> McpServerSpec:
    name = _require_name(item, "mcp_servers")
    return McpServerSpec(
        name=name,
        package=_opt_str(item, "package", "mcp_servers", name),
        command=_opt_str(item, "command", "mcp_servers", name),
        env=_str_list(item, "env", "mcp_servers", name),
        tools=_str_list(item, "tools", "mcp_servers", name),
        version=_opt_version(item, "mcp_servers", name),
    )


def _parse_subagent(item: dict) -> SubagentSpec:
    name = _require_name(item, "subagents")
    return SubagentSpec(
        name=name,
        model=_opt_str(item, "model", "subagents", name),
        allow_tools=_str_list(item, "allow_tools", "subagents", name),
        prompt=_opt_str(item, "prompt", "subagents", name),
        version=_opt_version(item, "subagents", name),
    )


def _parse_skill(item: dict) -> SkillSpec:
    name = _require_name(item, "skills")
    return SkillSpec(
        name=name,
        description=_opt_str(item, "description", "skills", name),
        version=_opt_version(item, "skills", name),
    )


def _parse_mcp_bundled(item: dict) -> McpBundledSpec:
    name = _require_name(item, "mcp_bundled")
    return McpBundledSpec(
        name=name,
        subagent=_opt_str(item, "subagent", "mcp_bundled", name),
        skills=_str_list(item, "skills", "mcp_bundled", name),
        tools=[
            _parse_tool_binding(t, name) for t in _sub_items(item, "tools", "mcp_bundled", name)
        ],
        version=_opt_version(item, "mcp_bundled", name),
    )


def _parse_tool_binding(item: dict, owner: str) -> ToolBinding:
    where = f"mcp_bundled '{owner}' の tools[]"
    if not isinstance(item, dict):
        raise ManifestError(f"{where} の各要素はマッピングである必要があります")
    bind = item.get("bind")
    if not bind or not isinstance(bind, str):
        raise ManifestError(f"{where} に bind（文字列）が必要です")
    src = item.get("from")
    if not src or not isinstance(src, str):
        raise ManifestError(f"{where} '{bind}' に from（例: mcp_server:weather）が必要です")
    if ":" not in src:
        raise ManifestError(
            f"{where} '{bind}' の from は '<kind>:<name>' 形式が必要です（got {src}）"
        )
    kind, _, from_name = src.partition(":")
    if kind not in SUPPORTED_BIND_KINDS:
        raise ManifestError(
            f"{where} '{bind}' の from kind '{kind}' は未対応です"
            f"（対応: {', '.join(SUPPORTED_BIND_KINDS)}）"
        )
    if not from_name:
        raise ManifestError(f"{where} '{bind}' の from にリソース名がありません（got {src}）")
    return ToolBinding(
        bind=bind,
        from_kind=kind,
        from_name=from_name,
        env=_str_list(item, "env", "mcp_bundled", f"{owner}.tools.{bind}"),
    )


def _parse_instance(item: dict) -> InstanceSpec:
    name = _require_name(item, "instances")
    mcp_bundled = item.get("mcp_bundled")
    if not mcp_bundled or not isinstance(mcp_bundled, str):
        raise ManifestError(f"instance '{name}' に mcp_bundled（文字列）が必要です")
    return InstanceSpec(
        name=name,
        mcp_bundled=mcp_bundled,
        defaults=_mapping(item, "defaults", "instances", name),
        secrets=_mapping(item, "secrets", "instances", name),
    )


# --- 相互参照の検証 ------------------------------------------------------------


def _validate(m: Manifest) -> None:
    """レイヤ内の名前重複と、レイヤ間の参照解決を検証する。"""
    for layer in ("mcp_servers", "subagents", "skills", "mcp_bundled", "instances"):
        _check_unique(m.names(layer), layer)

    servers = set(m.names("mcp_servers"))
    subagents = set(m.names("subagents"))
    skills = set(m.names("skills"))
    bundles = set(m.names("mcp_bundled"))

    for sa in m.subagents:
        for tool in sa.allow_tools:
            if tool not in servers:
                raise ManifestError(
                    f"subagent '{sa.name}': allow_tools が未定義の mcp_server を参照: {tool}"
                )

    for b in m.mcp_bundled:
        if b.subagent is not None and b.subagent not in subagents:
            raise ManifestError(f"mcp_bundled '{b.name}': 未定義の subagent を参照: {b.subagent}")
        for skill in b.skills:
            if skill not in skills:
                raise ManifestError(f"mcp_bundled '{b.name}': 未定義の skill を参照: {skill}")
        for t in b.tools:
            if t.from_name not in servers:
                raise ManifestError(
                    f"mcp_bundled '{b.name}' の tool '{t.bind}': "
                    f"未定義の mcp_server を参照: {t.from_name}"
                )

    for inst in m.instances:
        if inst.mcp_bundled not in bundles:
            raise ManifestError(
                f"instance '{inst.name}': 未定義の mcp_bundled を参照: {inst.mcp_bundled}"
            )


def _check_unique(names: list[str], layer: str) -> None:
    seen: set[str] = set()
    for name in names:
        if name in seen:
            raise ManifestError(f"{layer} に重複した name があります: {name}")
        seen.add(name)


# --- 小さな型チェックヘルパ ----------------------------------------------------


def _items(raw: dict, layer: str) -> list[dict]:
    """トップレベルのレイヤキーをリストとして取り出す（未指定なら空）。"""
    value = raw.get(layer)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ManifestError(f"{layer} はリストである必要があります（got {type(value).__name__}）")
    for it in value:
        if not isinstance(it, dict):
            raise ManifestError(f"{layer} の各要素はマッピングである必要があります")
    return value


def _sub_items(item: dict, key: str, layer: str, name: str) -> list:
    value = item.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ManifestError(
            f"{layer} '{name}' の {key} はリストである必要があります（got {type(value).__name__}）"
        )
    return value


def _require_name(item: dict, layer: str) -> str:
    name = item.get("name")
    if not name or not isinstance(name, str):
        raise ManifestError(f"{layer} の各要素に name（文字列）が必要です")
    return name


def _opt_version(item: dict, layer: str, name: str) -> str | None:
    """任意の `version` を取り出し、SemVer として妥当か検証する（不正なら ManifestError）。

    YAML は `1.2` 等を float に解釈するため、文字列以外も含めて SemVer 検証に委ねる
    （非文字列はそもそも妥当な SemVer ではないので不正として弾かれる）。
    """
    value = item.get("version")
    if value is None:
        return None
    try:
        parse_version(value)
    except SemverError as e:
        raise ManifestError(f"{layer} '{name}' の version が不正です: {e}") from e
    return value


def _opt_str(item: dict, key: str, layer: str, name: str) -> str | None:
    value = item.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ManifestError(
            f"{layer} '{name}' の {key} は文字列である必要があります（got {type(value).__name__}）"
        )
    return value


def _str_list(item: dict, key: str, layer: str, name: str) -> list[str]:
    value = item.get(key)
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ManifestError(f"{layer} '{name}' の {key} は文字列のリストである必要があります")
    return value


def _mapping(item: dict, key: str, layer: str, name: str) -> dict:
    value = item.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ManifestError(
            f"{layer} '{name}' の {key} はマッピングが必要です（got {type(value).__name__}）"
        )
    return value

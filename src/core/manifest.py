"""宣言的ワークスペース manifest（juice.yaml）のパーサ。

`juice.yaml` は「何を・どう結線するか」を 1 ファイルで宣言する唯一の正
（source of truth）。全レイヤ（mcp_server / subagent / skill / bundle / instance / workflow）を
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

from .semver import SemverError, parse_version, satisfies

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
    """bundle が mcp_server の tool を結線する 1 本の束縛。"""

    bind: str  # bundle 内での tool 名
    from_kind: str  # 取り込み元の型（現状は "mcp_server"）
    from_name: str  # 取り込み元リソース名
    env: list[str] = field(default_factory=list)  # 値は書かず env 名の参照のみ
    constraint: str | None = None  # 任意の version 制約（例: ">=1.0.0"）。`@` 無しなら None


@dataclass
class BundleSpec:
    """集約層：subagent + skill + mcp_server(tool) を結線する。"""

    name: str
    subagent: str | None = None
    skills: list[str] = field(default_factory=list)
    tools: list[ToolBinding] = field(default_factory=list)
    version: str | None = None


@dataclass
class InstanceSpec:
    """具象：bundle に変数既定値を与えた deployable な実個体。"""

    name: str
    bundle: str
    defaults: dict = field(default_factory=dict)
    secrets: dict = field(default_factory=dict)


@dataclass
class WorkflowStep:
    """1 ステップ。指定 bundle を input 付きで動かす（workflow / schedule で共用）。"""

    bundle: str
    input: dict = field(default_factory=dict)


@dataclass
class WorkflowSpec:
    """協調層：複数 bundle を**常駐**させる定義（時間非依存）。

    「何を・どう動かすか」だけを持つ。「いつ定期実行するか」は別概念 [ScheduleSpec] の責務
    （定義とトリガの分離。k8s の Job↔CronJob、Argo の WorkflowTemplate↔CronWorkflow と同型）。
    """

    name: str
    steps: list[WorkflowStep] = field(default_factory=list)
    version: str | None = None


@dataclass
class ScheduleSpec:
    """スケジューラの持ち物：`schedule`（cron）で steps を**定期実行**するトリガ宣言。

    workflow と違い `schedule` を必須で持つ（定期実行＝有限ジョブ）。steps の形は workflow と共用。
    """

    name: str
    schedule: str  # cron 式（必須。例: "0 7 * * *"）
    steps: list[WorkflowStep] = field(default_factory=list)
    version: str | None = None


@dataclass
class Manifest:
    """juice.yaml 全体。全レイヤを保持する。"""

    api_version: str
    namespace: str
    mcp_servers: list[McpServerSpec] = field(default_factory=list)
    subagents: list[SubagentSpec] = field(default_factory=list)
    skills: list[SkillSpec] = field(default_factory=list)
    bundles: list[BundleSpec] = field(default_factory=list)
    instances: list[InstanceSpec] = field(default_factory=list)
    workflows: list[WorkflowSpec] = field(default_factory=list)
    schedules: list[ScheduleSpec] = field(default_factory=list)

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
        bundles=[_parse_bundle(it) for it in _items(raw, "bundles")],
        instances=[_parse_instance(it) for it in _items(raw, "instances")],
        workflows=[_parse_workflow(it) for it in _items(raw, "workflows")],
        schedules=[_parse_schedule(it) for it in _items(raw, "schedules")],
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


def _parse_bundle(item: dict) -> BundleSpec:
    name = _require_name(item, "bundles")
    return BundleSpec(
        name=name,
        subagent=_opt_str(item, "subagent", "bundles", name),
        skills=_str_list(item, "skills", "bundles", name),
        tools=[_parse_tool_binding(t, name) for t in _sub_items(item, "tools", "bundles", name)],
        version=_opt_version(item, "bundles", name),
    )


def _parse_tool_binding(item: dict, owner: str) -> ToolBinding:
    where = f"bundle '{owner}' の tools[]"
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
    kind, _, ref = src.partition(":")
    if kind not in SUPPORTED_BIND_KINDS:
        raise ManifestError(
            f"{where} '{bind}' の from kind '{kind}' は未対応です"
            f"（対応: {', '.join(SUPPORTED_BIND_KINDS)}）"
        )
    # `<name>@<制約>` を分解する（`@` 無しなら制約なし）。
    from_name, sep, constraint = ref.partition("@")
    if not from_name:
        raise ManifestError(f"{where} '{bind}' の from にリソース名がありません（got {src}）")
    if sep and not constraint.strip():
        raise ManifestError(f"{where} '{bind}' の from に version 制約がありません（got {src}）")
    return ToolBinding(
        bind=bind,
        from_kind=kind,
        from_name=from_name,
        env=_str_list(item, "env", "bundles", f"{owner}.tools.{bind}"),
        constraint=constraint.strip() if sep else None,
    )


def _parse_instance(item: dict) -> InstanceSpec:
    name = _require_name(item, "instances")
    bundle = item.get("bundle")
    if not bundle or not isinstance(bundle, str):
        raise ManifestError(f"instance '{name}' に bundle（文字列）が必要です")
    return InstanceSpec(
        name=name,
        bundle=bundle,
        defaults=_mapping(item, "defaults", "instances", name),
        secrets=_mapping(item, "secrets", "instances", name),
    )


def _parse_workflow(item: dict) -> WorkflowSpec:
    name = _require_name(item, "workflows")
    steps = [_parse_step(s, name, "workflow") for s in _sub_items(item, "steps", "workflows", name)]
    return WorkflowSpec(
        name=name,
        steps=steps,
        version=_opt_version(item, "workflows", name),
    )


def _parse_schedule(item: dict) -> ScheduleSpec:
    name = _require_name(item, "schedules")
    schedule = item.get("schedule")
    if not schedule or not isinstance(schedule, str):
        raise ManifestError(f"schedule '{name}' に schedule（cron 文字列）が必要です")
    steps = [_parse_step(s, name, "schedule") for s in _sub_items(item, "steps", "schedules", name)]
    return ScheduleSpec(
        name=name,
        schedule=schedule,
        steps=steps,
        version=_opt_version(item, "schedules", name),
    )


def _parse_step(item: dict, owner: str, kind: str) -> WorkflowStep:
    where = f"{kind} '{owner}' の steps[]"
    if not isinstance(item, dict):
        raise ManifestError(f"{where} の各要素はマッピングである必要があります")
    bundled = item.get("bundle")
    if not bundled or not isinstance(bundled, str):
        raise ManifestError(f"{where} に bundle（文字列）が必要です")
    raw_input = item.get("input")
    if raw_input is None:
        raw_input = {}
    elif not isinstance(raw_input, dict):
        raise ManifestError(
            f"{where} '{bundled}' の input はマッピングが必要です（got {type(raw_input).__name__}）"
        )
    return WorkflowStep(bundle=bundled, input=raw_input)


# --- 相互参照の検証 ------------------------------------------------------------


def _validate(m: Manifest) -> None:
    """レイヤ内の名前重複と、レイヤ間の参照解決を検証する。"""
    for layer in (
        "mcp_servers",
        "subagents",
        "skills",
        "bundles",
        "instances",
        "workflows",
        "schedules",
    ):
        _check_unique(m.names(layer), layer)

    servers = set(m.names("mcp_servers"))
    subagents = set(m.names("subagents"))
    skills = set(m.names("skills"))
    bundles = set(m.names("bundles"))
    server_versions = {s.name: s.version for s in m.mcp_servers}

    for sa in m.subagents:
        for tool in sa.allow_tools:
            if tool not in servers:
                raise ManifestError(
                    f"subagent '{sa.name}': allow_tools が未定義の mcp_server を参照: {tool}"
                )

    for b in m.bundles:
        if b.subagent is not None and b.subagent not in subagents:
            raise ManifestError(f"bundle '{b.name}': 未定義の subagent を参照: {b.subagent}")
        for skill in b.skills:
            if skill not in skills:
                raise ManifestError(f"bundle '{b.name}': 未定義の skill を参照: {skill}")
        for t in b.tools:
            if t.from_name not in servers:
                raise ManifestError(
                    f"bundle '{b.name}' の tool '{t.bind}': "
                    f"未定義の mcp_server を参照: {t.from_name}"
                )
            if t.constraint is not None:
                _check_constraint(b, t, server_versions[t.from_name])

    for inst in m.instances:
        if inst.bundle not in bundles:
            raise ManifestError(f"instance '{inst.name}': 未定義の bundle を参照: {inst.bundle}")

    for wf in m.workflows:
        for step in wf.steps:
            if step.bundle not in bundles:
                raise ManifestError(f"workflow '{wf.name}': 未定義の bundle を参照: {step.bundle}")

    for sch in m.schedules:
        for step in sch.steps:
            if step.bundle not in bundles:
                raise ManifestError(f"schedule '{sch.name}': 未定義の bundle を参照: {step.bundle}")


def _check_constraint(b: BundleSpec, t: ToolBinding, server_version: str | None) -> None:
    """tool 束縛の version 制約を、参照先 mcp_server の宣言 version と照合する。"""
    where = f"bundle '{b.name}' の tool '{t.bind}'"
    if server_version is None:
        raise ManifestError(
            f"{where}: version 制約 '{t.constraint}' があるが "
            f"mcp_server '{t.from_name}' に version が宣言されていません"
        )
    try:
        ok = satisfies(server_version, t.constraint)
    except SemverError as e:
        raise ManifestError(f"{where}: version 制約が不正です: {e}") from e
    if not ok:
        raise ManifestError(
            f"{where}: mcp_server '{t.from_name}' の version {server_version} が "
            f"制約 '{t.constraint}' を満たしません"
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

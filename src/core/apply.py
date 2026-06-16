"""juice apply: 宣言（juice.yaml）を registries/ へ冪等反映する（C003）。

`juice.yaml`（[Manifest](manifest.py)）の desired state を、依存順（mcp_server → skill / subagent →
mcp_bundled → instance）に下層から registry レイアウトへ materialize（reconcile）する。
宣言にない既存パッケージは prune し、何度実行しても同じ状態へ収束する（冪等）。

材料化（materialize）先は現行の registry エントリ形式（docs/build.md「registry レイアウト」）:
- mcp_server → `tools/<name>/index.md`（frontmatter: kind/name/type/command/args/env）
- subagent   → `subagents/<name>/index.md`（frontmatter＋本文 = prompt）
- skill      → `skills/<name>/SKILL.md`
- mcp_bundled→ `bundles/<name>/bundle.yml`
- instance   → `instances/<name>/index.yml`
- workflow   → `workflows/<name>/index.md`（frontmatter: kind/name/type/steps）
- schedule   → `schedules/<name>/index.md`（frontmatter: kind/name/type/schedule/steps）

`dry_run=True` なら書き込まず、行われる変更（written / pruned）だけを返す。

> 注意: apply は registry をこの宣言の出力先として上書き・prune する。実レジストリ
> （registries/namespaces/default）を壊さないよう、テストは必ず tmp レジストリで行うこと。
> 外部 digest 取得（lock）や remote backend は範囲外（C002 / 将来）。
"""

from __future__ import annotations

import yaml

from .config import ENTRY_FILES
from .manifest import (
    InstanceSpec,
    Manifest,
    McpBundledSpec,
    McpServerSpec,
    ScheduleSpec,
    SkillSpec,
    SubagentSpec,
    WorkflowSpec,
)
from .registry import RegistryArray

# (manifest 属性, registry レイヤ) を依存順（下層 → 上層）に並べる。
# workflow / schedule は mcp_bundled を参照する最上位なので末尾に置く。
_LAYER_ORDER: list[tuple[str, str]] = [
    ("mcp_servers", "tool"),
    ("skills", "skill"),
    ("subagents", "subagent"),
    ("mcp_bundled", "mcp_bundled"),
    ("instances", "instance"),
    ("workflows", "workflow"),
    ("schedules", "schedule"),
]


def apply_manifest(
    registries: RegistryArray,
    manifest: Manifest,
    prune: bool = True,
    dry_run: bool = False,
) -> dict:
    """manifest を registries へ冪等反映する。要約（written / pruned）を返す。"""
    ns = registries.namespace
    written: list[str] = []
    pruned: list[str] = []

    for attr, layer in _LAYER_ORDER:
        entry = ENTRY_FILES[layer]
        desired = {item.name: _materialize(layer, item, ns) for item in getattr(manifest, attr)}
        existing = set(registries.list(layer))

        for name in sorted(desired):
            text = desired[name]
            if (
                registries.exists(layer, name, entry)
                and registries.read(layer, name, entry) == text
            ):
                continue  # 既に同一内容 → 冪等に skip
            if not dry_run:
                registries.write(layer, name, entry, text)
            written.append(f"{layer}/{name}")

        if prune:
            for name in sorted(existing - set(desired)):
                if not dry_run:
                    registries.remove(layer, name, "")  # パッケージのディレクトリごと削除
                pruned.append(f"{layer}/{name}")

    return {"namespace": ns, "written": written, "pruned": pruned, "dry_run": dry_run}


# --- レイヤ別の materialize -----------------------------------------------------


def _materialize(layer: str, item, ns: str) -> str:
    if layer == "tool":
        return _tool(item)
    if layer == "subagent":
        return _subagent(item)
    if layer == "skill":
        return _skill(item)
    if layer == "mcp_bundled":
        return _bundle(item, ns)
    if layer == "instance":
        return _instance(item)
    if layer == "workflow":
        return _workflow(item)
    if layer == "schedule":
        return _schedule(item)
    raise ValueError(f"unknown layer: {layer}")  # 到達しない（_LAYER_ORDER に閉じている）


def _tool(s: McpServerSpec) -> str:
    # command 文字列を「先頭=コマンド / 残り=args」に分解する（例: "npx -y pkg"）。
    parts = (s.command or "").split()
    command = parts[0] if parts else "python"
    args = parts[1:]
    meta: dict = {
        "kind": "tool",
        "name": s.name,
        "type": "mcp-server",
        "command": command,
        "args": args,
        "env": _env_refs(s.env),
    }
    if s.package:
        meta["package"] = s.package
    return _frontmatter(meta, f"# {s.name}\n")


def _subagent(s: SubagentSpec) -> str:
    # `type` は OKF 必須の concept type、`kind` は juice のレイヤ分類（metadata.verify_okf）。
    meta: dict = {"kind": "subagent", "name": s.name, "type": "subagent"}
    if s.model:
        meta["model"] = s.model
    meta["tools"] = list(s.allow_tools)  # registry の subagent は許可 tool を `tools:` で持つ
    body = (s.prompt or "").strip()
    return _frontmatter(meta, body + "\n" if body else "")


def _skill(s: SkillSpec) -> str:
    # `type` は OKF 必須の concept type、`kind` は juice のレイヤ分類（metadata.verify_okf）。
    meta: dict = {"kind": "skill", "name": s.name, "type": "skill"}
    if s.description:
        meta["description"] = s.description
    return _frontmatter(meta, f"# {s.name}\n")


def _bundle(b: McpBundledSpec, ns: str) -> str:
    data: dict = {
        "apiVersion": "juice/v1",
        "kind": "mcp_bundled",
        "name": b.name,
        "namespace": ns,
    }
    if b.subagent:
        data["subagent"] = b.subagent
    if b.skills:
        data["skills"] = list(b.skills)
    # bundle.yml の tools は tool パッケージ名（= mcp_server 名 = from_name）でキーする。
    tools: dict = {}
    for t in b.tools:
        spec = tools.setdefault(t.from_name, {})
        if t.env:
            spec["env"] = _env_refs(t.env)
    if tools:
        data["tools"] = tools
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def _instance(i: InstanceSpec) -> str:
    data: dict = {
        "kind": "instance",
        "name": i.name,
        "mcp_bundled": i.mcp_bundled,
        "status": "stopped",
    }
    if i.secrets:
        data["env"] = dict(i.secrets)  # secret は env 名参照のまま（値は書かない）
    if i.defaults:
        data["defaults"] = dict(i.defaults)
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def _workflow(w: WorkflowSpec) -> str:
    # workflow は .md concept doc。`type` は OKF 必須、`kind` は juice 分類（metadata.verify_okf）。
    # workflow は常駐サービス群の定義（時間非依存）。schedule は別概念（ScheduleSpec）の持ち物。
    meta: dict = {"kind": "workflow", "name": w.name, "type": "workflow"}
    meta["steps"] = [
        {"mcp_bundled": s.mcp_bundled, **({"input": dict(s.input)} if s.input else {})}
        for s in w.steps
    ]
    return _frontmatter(meta, f"# {w.name}\n")


def _schedule(s: ScheduleSpec) -> str:
    # schedule は .md concept doc。`type` は OKF 必須。cron（いつ動かすか）を持つトリガ。
    meta: dict = {"kind": "schedule", "name": s.name, "type": "schedule", "schedule": s.schedule}
    meta["steps"] = [
        {"mcp_bundled": st.mcp_bundled, **({"input": dict(st.input)} if st.input else {})}
        for st in s.steps
    ]
    return _frontmatter(meta, f"# {s.name}\n")


# --- 小さなヘルパ --------------------------------------------------------------


def _env_refs(names: list[str]) -> dict[str, str]:
    """env 名のリストを `{NAME: ${NAME}}` の参照マッピングにする（値は書かない）。"""
    return {n: "${" + n + "}" for n in names}


def _frontmatter(meta: dict, body: str) -> str:
    """YAML frontmatter（`---` で囲む）＋本文の Markdown を組み立てる。"""
    fm = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{fm}\n---\n\n{body}"

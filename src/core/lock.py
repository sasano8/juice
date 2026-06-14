"""juice.lock の生成（C002）。

`juice.yaml`（[Manifest](manifest.py)）から、再現性のための解決結果を `juice.lock` に固める。
再現性は「committed な spec（juice.yaml）＋ lock」で担保する（docs/workspace.md 参照）。

現状の lock が固定するもの:
- **manifestDigest** … manifest の宣言内容のハッシュ。spec と lock の不整合（drift）検出に使う。
- **mcp_servers** … 各 server の `package` / `command` を pin。外部パッケージの `digest`（npm / OCI
  等）の取得元は未決の論点のため、欄は用意して値は `None`（TODO）にしておく。
- **instances** … instance ごとの deployable な依存閉包（mcp_bundled → subagent / skills /
  結線された mcp_server）を解決して固定する。

`build_lock` は純関数で、同じ Manifest からは常に同じ Lock を返す。`dump_lock` も決定的に直列化する
ため、同じ juice.yaml からは**バイト単位で同一の juice.lock** が得られる（冪等）。
digest の取得などの副作用は持たない。
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .manifest import Manifest, load_manifest

# juice.lock のフォーマット版。スキーマを変えたら上げる。
LOCK_VERSION = 1


class LockError(Exception):
    """lock の要求（--frozen / --require-lock）に反したときに投げる。"""


# 生成物であることを示すヘッダ（手編集を抑止）。
_LOCK_HEADER = "# juice.lock — 生成物。手で編集しない（`juice lock` で再生成する）。\n"


@dataclass
class LockedServer:
    """pin された mcp_server。digest は外部取得が未実装のため当面 None。"""

    name: str
    package: str | None
    command: str | None
    digest: str | None = None  # TODO: npm / OCI 等から取得して pin する


@dataclass
class LockedInstance:
    """instance の deployable な依存閉包（解決済み）。"""

    name: str
    mcp_bundled: str
    subagent: str | None
    skills: list[str] = field(default_factory=list)
    mcp_servers: list[str] = field(default_factory=list)  # 結線された mcp_server 名


@dataclass
class Lock:
    """juice.lock 全体。"""

    lock_version: int
    api_version: str
    namespace: str
    manifest_digest: str
    mcp_servers: list[LockedServer] = field(default_factory=list)
    instances: list[LockedInstance] = field(default_factory=list)


def manifest_digest(manifest: Manifest) -> str:
    """manifest の宣言内容から決定的な `sha256:...` ダイジェストを作る。

    YAML の整形やコメントに依存しないよう、構造を正規化（キーソートした JSON）してからハッシュする。
    """
    canonical = json.dumps(
        dataclasses.asdict(manifest),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_lock(manifest: Manifest) -> Lock:
    """Manifest を解決して Lock を構築する（純関数・冪等）。"""
    servers = [
        LockedServer(name=s.name, package=s.package, command=s.command)
        for s in manifest.mcp_servers
    ]

    bundles = {b.name: b for b in manifest.mcp_bundled}
    instances: list[LockedInstance] = []
    for inst in manifest.instances:
        bundle = bundles.get(inst.mcp_bundled)
        # 参照は parse 時に検証済みだが、念のため欠落は空閉包として扱う。
        subagent = bundle.subagent if bundle else None
        skills = list(bundle.skills) if bundle else []
        server_names = _dedup(t.from_name for t in bundle.tools) if bundle else []
        instances.append(
            LockedInstance(
                name=inst.name,
                mcp_bundled=inst.mcp_bundled,
                subagent=subagent,
                skills=skills,
                mcp_servers=server_names,
            )
        )

    return Lock(
        lock_version=LOCK_VERSION,
        api_version=manifest.api_version,
        namespace=manifest.namespace,
        manifest_digest=manifest_digest(manifest),
        mcp_servers=servers,
        instances=instances,
    )


def lock_to_dict(lock: Lock) -> dict:
    """juice.lock として書き出す決定的な dict（キー順を固定）に変換する。"""
    return {
        "lockVersion": lock.lock_version,
        "apiVersion": lock.api_version,
        "namespace": lock.namespace,
        "manifestDigest": lock.manifest_digest,
        "mcp_servers": [
            {
                "name": s.name,
                "package": s.package,
                "command": s.command,
                "digest": s.digest,
            }
            for s in lock.mcp_servers
        ],
        "instances": [
            {
                "name": i.name,
                "mcp_bundled": i.mcp_bundled,
                "subagent": i.subagent,
                "skills": i.skills,
                "mcp_servers": i.mcp_servers,
            }
            for i in lock.instances
        ],
    }


def dump_lock(lock: Lock) -> str:
    """Lock を juice.lock のテキスト（YAML＋ヘッダ）に決定的に直列化する。"""
    body = yaml.safe_dump(
        lock_to_dict(lock),
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    return _LOCK_HEADER + body


def lock_manifest_text(text: str) -> Lock:
    """juice.yaml のテキストから Lock を構築する（parse → build）。"""
    from .manifest import parse_manifest

    return build_lock(parse_manifest(text))


def write_lock(manifest_path: str, out_path: str) -> dict:
    """manifest を読み、Lock を生成して out_path に書き出す。要約 dict を返す。

    冪等: 同じ manifest からは毎回同一バイトの juice.lock を書く。
    """
    manifest = load_manifest(manifest_path)
    lock = build_lock(manifest)
    text = dump_lock(lock)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)
    return {
        "out": out_path,
        "manifestDigest": lock.manifest_digest,
        "mcp_servers": [s.name for s in lock.mcp_servers],
        "instances": [i.name for i in lock.instances],
    }


def read_lock(path: str) -> dict | None:
    """juice.lock を読み YAML を dict で返す。ファイルが無ければ None。"""
    p = Path(path)
    if not p.exists():
        return None
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def lock_status(manifest: Manifest, lock_path: str) -> dict:
    """manifest と juice.lock の整合状態を返す。

    `{present, drift, expected, found}`:
    - present … lock ファイルが存在するか
    - drift   … lock の `manifestDigest` が manifest と食い違うか（present のときのみ意味を持つ）
    - expected… manifest から計算した現在の digest
    - found   … lock に記録されている digest（無ければ None）
    """
    expected = manifest_digest(manifest)
    lock = read_lock(lock_path)
    if lock is None:
        return {"present": False, "drift": False, "expected": expected, "found": None}
    found = lock.get("manifestDigest")
    return {"present": True, "drift": found != expected, "expected": expected, "found": found}


def _dedup(items) -> list[str]:
    """出現順を保ったまま重複を除く。"""
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out

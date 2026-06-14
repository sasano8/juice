"""モック mcp_server（自動生成）。

stdio 上の JSON-RPC（MCP の簡易版）で initialize / tools/list / tools/call に応答する。
get_forecast(city) はダミー予報を返す。実 server に差し替えるまでの接続確認用。
"""

from __future__ import annotations

import json
import sys

TOOLS = [
    {
        "name": "get_forecast",
        "description": "都市の天気予報を返す（モック）",
        "inputSchema": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    }
]


def handle(req: dict) -> dict:
    method = req.get("method")
    if method == "initialize":
        return {"serverInfo": {"name": "mock-weather", "version": "0.0.1"}, "capabilities": {"tools": {}}}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        args = (req.get("params") or {}).get("arguments", {})
        city = args.get("city", "?")
        return {"content": [{"type": "text", "text": f"{city}: 晴れ 26C（モック予報）"}]}
    raise ValueError(f"unknown method: {method}")


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = json.loads(line)
        try:
            resp = {"jsonrpc": "2.0", "id": req.get("id"), "result": handle(req)}
        except Exception as e:  # noqa: BLE001
            resp = {"jsonrpc": "2.0", "id": req.get("id"), "error": {"message": str(e)}}
        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

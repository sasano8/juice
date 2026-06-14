"""juice bundle のエントリポイント（自動生成）。

この bundle 自体を 1 つの **mcp_server** として stdio(JSON-RPC) で公開する（actor = mcp_server）。
公開する tool は内部のバック server（ここではモック mock_server.py）へ proxy する。
MCP の簡易版で、標準ライブラリのみで動く。

疎通確認（応答例）:
    echo '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_forecast","arguments":{"city":"Tokyo"}}}' | python entrypoint.py
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).parent
NAME = "weather-bot"


class StdioClient:
    """stdio 上の JSON-RPC でバック mcp_server に話す最小クライアント。"""

    def __init__(self, command: list[str]) -> None:
        self.proc = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, cwd=str(HERE)
        )
        self._id = 0

    def call(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        req = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}}
        self.proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        return json.loads(self.proc.stdout.readline())

    def close(self) -> None:
        self.proc.stdin.close()
        self.proc.terminate()


def serve() -> None:
    """この bundle を mcp_server として stdin/stdout で公開し、バック server へ proxy する。"""
    backing = StdioClient([sys.executable, str(HERE / "mock_server.py")])
    backing.call("initialize")
    tools = backing.call("tools/list")["result"]["tools"]

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = json.loads(line)
        method = req.get("method")
        try:
            if method == "initialize":
                result = {"serverInfo": {"name": NAME, "version": "0.0.1"}, "capabilities": {"tools": {}}}
            elif method == "tools/list":
                result = {"tools": tools}
            elif method == "tools/call":
                result = backing.call("tools/call", req.get("params") or {})["result"]
            else:
                raise ValueError(f"unknown method: {method}")
            resp = {"jsonrpc": "2.0", "id": req.get("id"), "result": result}
        except Exception as e:  # noqa: BLE001
            resp = {"jsonrpc": "2.0", "id": req.get("id"), "error": {"message": str(e)}}
        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    backing.close()


if __name__ == "__main__":
    serve()

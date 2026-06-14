"""エントリポイント（自動生成）。mode に応じてサービスを起動する。

    api         … 会話 API（FastAPI / uvicorn, OpenAI 互換）
    ui          … LangGraph Studio（langgraph dev）
    mcp_server  … バック MCP server（stdio）

mode は docker run の引数（CMD）または環境変数 MODE で渡す。既定は api。
"""

from __future__ import annotations

import os
import sys

MODE = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("MODE", "api")).strip()
PORT = os.environ.get("PORT", "8000")


def main() -> int:
    if MODE == "api":
        os.execvp("uvicorn", ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", PORT])
    if MODE == "ui":
        os.execvp("langgraph", ["langgraph", "dev", "--host", "0.0.0.0", "--port", PORT, "--no-browser"])
    if MODE == "mcp_server":
        import json
        import pathlib

        here = pathlib.Path(__file__).parent
        servers = (json.loads((here / "agent.json").read_text(encoding="utf-8")).get("mcp_servers") or {})
        if not servers:
            print("no mcp_servers in agent.json", file=sys.stderr)
            return 2
        srv = next(iter(servers.values()))  # 先頭 tool の server を起動
        args = [str(here / a) if isinstance(a, str) and a.endswith(".py") else a for a in srv.get("args", [])]
        os.execvp(srv["command"], [srv["command"], *args])
    print(f"unknown mode: {MODE} (use api / ui / mcp_server)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any, Dict, Optional

from .resources import DashboardResourceRegistry
from .tools import DashboardToolRegistry


class MCPJsonRpcServer:
    def __init__(
        self,
        *,
        tools: DashboardToolRegistry,
        resources: DashboardResourceRegistry,
        name: str = "ds4-dashboard",
        version: str = "0.1.0",
    ) -> None:
        self.tools = tools
        self.resources = resources
        self.name = name
        self.version = version

    async def handle(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        request_id = payload.get("id")
        method = payload.get("method")
        params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
        try:
            result = await self._dispatch(str(method), params)
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32000, "message": str(exc)},
            }

    async def _dispatch(self, method: str, params: Dict[str, Any]) -> Any:
        if method == "initialize":
            return {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": self.name, "version": self.version},
                "capabilities": {"tools": {}, "resources": {}},
            }
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": self.tools.list_tools()}
        if method == "tools/call":
            name = str(params.get("name", ""))
            arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
            result = self.tools.call_tool(name, arguments)
            return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}], "structuredContent": result}
        if method == "resources/list":
            return {"resources": self.resources.list_resources()}
        if method == "resources/read":
            uri = str(params.get("uri", ""))
            result = self.resources.read_resource(uri)
            return {"contents": [{"uri": uri, "mimeType": "application/json", "text": json.dumps(result, indent=2)}]}
        raise KeyError(f"Unsupported MCP method: {method}")


async def run_stdio(server: MCPJsonRpcServer) -> None:
    loop = asyncio.get_running_loop()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            break
        try:
            payload = json.loads(line)
            response = await server.handle(payload)
        except json.JSONDecodeError as exc:
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": str(exc)},
            }
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


def main() -> None:
    from dashboard import mcp_rpc_server

    asyncio.run(run_stdio(mcp_rpc_server))


if __name__ == "__main__":
    main()

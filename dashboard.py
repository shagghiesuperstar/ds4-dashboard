from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from benchmarks.runner import BenchmarkRunner
from bridge.config_manager import DS4ConfigManager
from bridge.engine_client import DS4EngineClient, EngineClientConfig
from bridge.system_metrics import MacSystemMetrics
from mcp.resources import DashboardResourceRegistry
from mcp.server import MCPJsonRpcServer
from mcp.tools import DashboardToolRegistry
from updater.updater import DS4Updater


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

DS4_HOME = Path(os.environ.get("DS4_HOME", "~/ds4")).expanduser()
DS4_BINARY = Path(os.environ.get("DS4_BINARY", str(DS4_HOME / "ds4-server"))).expanduser()
DS4_MODEL = Path(os.environ.get("DS4_MODEL", str(DS4_HOME / "ds4flash.gguf"))).expanduser()
DS4_MTP = Path(
    os.environ.get("DS4_MTP", str(DS4_HOME / "gguf/DeepSeek-V4-Flash-MTP-Q4K-Q8_0-F32.gguf"))
).expanduser()
DS4_METAL_DIR = Path(os.environ.get("DS4_METAL_DIR", str(DS4_HOME / "metal"))).expanduser()
DS4_KV_CACHE = Path(os.environ.get("DS4_KV_CACHE", "/tmp/ds4-kv")).expanduser()

DS4_PRIMARY_PORT = int(os.environ.get("DS4_PRIMARY_PORT", "8001"))
DS4_TELEM_URL = os.environ.get("DS4_TELEM_URL", f"http://127.0.0.1:{DS4_PRIMARY_PORT}/telem")
DS4_METRICS_URL = os.environ.get("DS4_METRICS_URL", f"http://127.0.0.1:{DS4_PRIMARY_PORT}/metrics")
DS4_COMPLETION_URL = os.environ.get(
    "DS4_COMPLETION_URL",
    f"http://127.0.0.1:{DS4_PRIMARY_PORT}/v1/chat/completions",
)
DS4_CONTEXT_WINDOW = int(os.environ.get("DS4_CONTEXT_WINDOW", "131072"))
DS4_KV_CACHE_BUDGET_MIB = int(os.environ.get("DS4_KV_CACHE_BUDGET_MIB", "51200"))
DS4_GITHUB_REPO = os.environ.get("DS4_GITHUB_REPO", "antirez/ds4")


app = FastAPI(
    title="DS4 Dwarfstar Dashboard",
    description="Local Dwarfstar dashboard for DS4 telemetry, config, benchmarks, updates, and MCP.",
    version="0.1.0",
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR), check_dir=False), name="static")

engine_client = DS4EngineClient(
    EngineClientConfig(
        host="127.0.0.1",
        port=DS4_PRIMARY_PORT,
        telem_url=DS4_TELEM_URL,
        metrics_url=DS4_METRICS_URL,
        completion_url=DS4_COMPLETION_URL,
        binary_path=DS4_BINARY,
    )
)
config_manager = DS4ConfigManager(
    binary_path=DS4_BINARY,
    telem_url=DS4_TELEM_URL,
    kv_cache_path=DS4_KV_CACHE,
    metal_dir=DS4_METAL_DIR,
    defaults={
        "binary": str(DS4_BINARY),
        "primary_port": DS4_PRIMARY_PORT,
        "telem_url": DS4_TELEM_URL,
        "metrics_url": DS4_METRICS_URL,
        "completion_url": DS4_COMPLETION_URL,
        "model": str(DS4_MODEL),
        "mtp": str(DS4_MTP),
        "context_window": DS4_CONTEXT_WINDOW,
        "kv_disk_cache": str(DS4_KV_CACHE),
        "kv_cache_budget_mib": DS4_KV_CACHE_BUDGET_MIB,
        "metal_shader_dir": str(DS4_METAL_DIR),
        "poll_interval_ms": 2000,
    },
)
system_metrics = MacSystemMetrics()
benchmark_runner = BenchmarkRunner(engine_client)
updater = DS4Updater(repo=DS4_GITHUB_REPO, binary_path=DS4_BINARY)


class ConfigUpdate(BaseModel):
    key: str
    value: Any


class BenchmarkRunRequest(BaseModel):
    suite_id: str = "quick_smoke"
    iterations: int = 1
    compare_label: Optional[str] = None


class UpdateRequest(BaseModel):
    apply: bool = False
    asset_url: Optional[str] = None
    sha256: Optional[str] = None


def get_dashboard_config() -> Dict[str, Any]:
    return config_manager.get_config()


def get_config_schema() -> Dict[str, Dict[str, Any]]:
    return config_manager.get_schema()


def get_status_payload() -> Dict[str, Any]:
    status = engine_client.get_status()
    config = config_manager.get_config()
    kv_cache = config.get("kv_disk_cache", {})
    system = system_metrics.get_metrics(
        pid=status.get("pid"),
        kv_cache_path=Path(str(kv_cache.get("path", DS4_KV_CACHE))).expanduser(),
        kv_budget_bytes=kv_cache.get("budget_bytes"),
    )

    telemetry_kv = status.get("telemetry", {}).get("kv_cache", {})
    disk_kv = system.get("kv_disk_cache") or {}
    status["config"] = config
    status["system"] = system
    status["kv_cache"] = {
        "path": kv_cache.get("path"),
        "budget_mib": kv_cache.get("budget_mib"),
        "budget_bytes": kv_cache.get("budget_bytes"),
        "disk_used_bytes": disk_kv.get("used_bytes"),
        "disk_fill_percent": disk_kv.get("fill_percent"),
        **telemetry_kv,
    }
    return status


def get_metrics_payload() -> Dict[str, Any]:
    status = get_status_payload()
    return {
        "checked_at": status.get("checked_at"),
        "state": status.get("state"),
        "running": status.get("running"),
        "port": status.get("port"),
        "telemetry": status.get("telemetry"),
        "kv_cache": status.get("kv_cache"),
        "system": status.get("system"),
    }


tool_registry = DashboardToolRegistry(
    status_provider=get_status_payload,
    metrics_provider=get_metrics_payload,
    config_manager=config_manager,
    benchmark_runner=benchmark_runner,
    updater=updater,
)
resource_registry = DashboardResourceRegistry(
    telemetry_provider=get_metrics_payload,
    config_manager=config_manager,
    benchmark_runner=benchmark_runner,
)
mcp_rpc_server = MCPJsonRpcServer(tools=tool_registry, resources=resource_registry)


@app.get("/", include_in_schema=False)
async def index() -> Response:
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return HTMLResponse("<h1>DS4 Dashboard</h1><p>Static shell has not been generated yet.</p>")


@app.get("/api/status")
async def api_status() -> Dict[str, Any]:
    return get_status_payload()


@app.get("/api/metrics")
async def api_metrics() -> Dict[str, Any]:
    return get_metrics_payload()


@app.get("/api/config")
async def api_config() -> Dict[str, Any]:
    return config_manager.get_config()


@app.get("/api/config-schema")
async def api_config_schema(refresh: bool = False) -> Dict[str, Dict[str, Any]]:
    return config_manager.get_schema(force_refresh=refresh)


@app.patch("/api/config")
async def api_update_config(update: ConfigUpdate) -> Dict[str, Any]:
    try:
        updated = config_manager.set_override(update.key, update.value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "updated": updated, "config": config_manager.get_config()}


@app.delete("/api/config/{key}")
async def api_clear_config(key: str) -> Dict[str, Any]:
    removed = config_manager.clear_override(key)
    return {"ok": True, "removed": removed, "config": config_manager.get_config()}


@app.get("/api/config-overrides")
async def api_config_overrides() -> Dict[str, Any]:
    return config_manager.get_overrides()


@app.get("/api/benchmarks")
async def api_benchmark_suites() -> Dict[str, Any]:
    return {"suites": benchmark_runner.list_suites(), "last_results": benchmark_runner.get_last_results()}


@app.post("/api/benchmarks/run")
async def api_run_benchmark(request: BenchmarkRunRequest) -> Dict[str, Any]:
    try:
        result = benchmark_runner.run_suite(
            request.suite_id,
            iterations=request.iterations,
            compare_label=request.compare_label,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return result


@app.get("/api/benchmarks/results")
async def api_benchmark_results() -> Dict[str, Any]:
    return {"results": benchmark_runner.get_last_results()}


@app.get("/api/update/check")
async def api_update_check() -> Dict[str, Any]:
    return updater.check_latest_release()


@app.post("/api/update")
async def api_update(request: UpdateRequest) -> Dict[str, Any]:
    return updater.update(apply=request.apply, asset_url=request.asset_url, sha256=request.sha256)


@app.get("/api/mcp/manifest")
async def api_mcp_manifest() -> Dict[str, Any]:
    return {"tools": tool_registry.list_tools(), "resources": resource_registry.list_resources()}


@app.post("/api/mcp/tools/{tool_name}")
async def api_mcp_tool(tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    try:
        return tool_registry.call_tool(tool_name, arguments or {})
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/mcp/resources")
async def api_mcp_resources() -> Dict[str, Any]:
    return {"resources": resource_registry.list_resources()}


@app.get("/api/mcp/resources/read")
async def api_mcp_resource_read(uri: str) -> Dict[str, Any]:
    try:
        return resource_registry.read_resource(uri)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/mcp")
async def api_mcp_jsonrpc(payload: Dict[str, Any]) -> Dict[str, Any]:
    return await mcp_rpc_server.handle(payload)


@app.get("/mcp/sse")
async def api_mcp_sse() -> StreamingResponse:
    async def events():
        while True:
            payload = json.dumps(get_metrics_payload(), separators=(",", ":"))
            yield f"event: telemetry\ndata: {payload}\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(events(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("dashboard:app", host="127.0.0.1", port=8765, reload=True)

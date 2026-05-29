from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from bridge.engine_client import DS4EngineClient, EngineClientConfig
from bridge.system_metrics import MacSystemMetrics


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
DS4_CONTEXT_WINDOW = int(os.environ.get("DS4_CONTEXT_WINDOW", "131072"))
DS4_KV_CACHE_BUDGET_MIB = int(os.environ.get("DS4_KV_CACHE_BUDGET_MIB", "51200"))


app = FastAPI(
    title="DS4 Inference Engine Dashboard",
    description="Local Dwarfstar dashboard for DS4 engine telemetry and configuration.",
    version="0.1.0",
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR), check_dir=False), name="static")

engine_client = DS4EngineClient(
    EngineClientConfig(
        host="127.0.0.1",
        port=DS4_PRIMARY_PORT,
        telem_url=DS4_TELEM_URL,
        binary_path=DS4_BINARY,
    )
)
system_metrics = MacSystemMetrics()


def _path_info(path: Path) -> Dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.exists(),
        "is_symlink": path.is_symlink(),
        "resolved": str(path.resolve()) if path.exists() else None,
    }


def _count_metal_shaders() -> int:
    if not DS4_METAL_DIR.is_dir():
        return 0
    return len([path for path in DS4_METAL_DIR.iterdir() if path.is_file() and path.suffix == ".metal"])


def get_dashboard_config() -> Dict[str, Any]:
    return {
        "engine": "ds4",
        "binary": _path_info(DS4_BINARY),
        "primary_port": DS4_PRIMARY_PORT,
        "telem_url": DS4_TELEM_URL,
        "model": _path_info(DS4_MODEL),
        "mtp": _path_info(DS4_MTP),
        "context_window": DS4_CONTEXT_WINDOW,
        "kv_disk_cache": {
            "path": str(DS4_KV_CACHE),
            "budget_mib": DS4_KV_CACHE_BUDGET_MIB,
            "exists": DS4_KV_CACHE.exists(),
        },
        "metal": {
            "path": str(DS4_METAL_DIR),
            "shader_count": _count_metal_shaders(),
        },
        "poll_interval_ms": 2000,
    }


def get_config_schema() -> Dict[str, Dict[str, Any]]:
    return {
        "primary_port": {
            "type": "int",
            "default": DS4_PRIMARY_PORT,
            "desc": "DS4 primary server and telemetry port.",
        },
        "telem_url": {
            "type": "string",
            "default": DS4_TELEM_URL,
            "desc": "DS4 telemetry endpoint polled by the dashboard.",
        },
        "model": {
            "type": "path",
            "default": str(DS4_MODEL),
            "desc": "Main GGUF model path or symlink.",
        },
        "mtp": {
            "type": "path",
            "default": str(DS4_MTP),
            "desc": "MTP draft model GGUF path.",
        },
        "context_window": {
            "type": "int",
            "default": DS4_CONTEXT_WINDOW,
            "desc": "Configured DS4 context window.",
        },
        "kv_disk_cache": {
            "type": "path",
            "default": str(DS4_KV_CACHE),
            "desc": "KV disk cache directory.",
        },
        "kv_cache_budget_mib": {
            "type": "int",
            "default": DS4_KV_CACHE_BUDGET_MIB,
            "desc": "KV disk cache budget in MiB.",
        },
        "metal_shader_dir": {
            "type": "path",
            "default": str(DS4_METAL_DIR),
            "desc": "Directory containing Metal shader sources.",
        },
    }


@app.get("/", include_in_schema=False)
async def index() -> Response:
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return HTMLResponse("<h1>DS4 Dashboard</h1><p>Static shell has not been generated yet.</p>")


@app.get("/api/status")
async def api_status() -> Dict[str, Any]:
    status = engine_client.get_status()
    status["config"] = get_dashboard_config()
    status["system"] = system_metrics.get_metrics()
    return status


@app.get("/api/config")
async def api_config() -> Dict[str, Any]:
    return get_dashboard_config()


@app.get("/api/config-schema")
async def api_config_schema() -> Dict[str, Dict[str, Any]]:
    return get_config_schema()


# ── Config Editor ────────────────────────────────────────────────────

from pydantic import BaseModel

class ConfigUpdate(BaseModel):
    key: str
    value: str

_CONFIG_OVERRIDES: Dict[str, str] = {}

@app.patch("/api/config")
async def api_update_config(update: ConfigUpdate) -> Dict[str, Any]:
    key = update.key.strip()
    value = update.value.strip()
    _CONFIG_OVERRIDES[key] = value
    # Return the merged config so the frontend sees the new value immediately
    return {"ok": True, "key": key, "value": value}

@app.get("/api/config-overrides")
async def api_config_overrides() -> Dict[str, str]:
    return dict(_CONFIG_OVERRIDES)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("dashboard:app", host="127.0.0.1", port=8765, reload=True)

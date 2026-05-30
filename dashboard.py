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
from bridge.model_averages import ModelRunningAverages
from bridge.model_discovery import discover_models, fetch_model_card_description
from bridge.system_metrics import MacSystemMetrics
from mcp.resources import DashboardResourceRegistry
from mcp.server import MCPJsonRpcServer, run_stdio
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
DS4_KV_CACHE = Path(os.environ.get("DS4_KV_CACHE", "/Volumes/OWC_MODELS_TB5/DS4/cache")).expanduser()

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

model_averages = ModelRunningAverages()

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

# Directories to scan for available GGUF models
MODEL_SEARCH_PATHS = [
    DS4_HOME,
    DS4_HOME / "gguf",
    Path("~/Downloads").expanduser(),
    Path("~/models").expanduser(),
    Path("/Volumes/OWC_MODELS_TB5").expanduser(),
    Path("/Volumes/OWC_MODELS_TB5/DS4").expanduser(),
    Path("/Volumes/OWC_MODELS_TB5/DS4/gguf").expanduser(),
]


def current_model_path_from_config(config: Optional[Dict[str, Any]] = None) -> str:
    config = config or config_manager.get_config()
    model = config.get("model", "")
    if isinstance(model, dict):
        return str(model.get("path") or "")
    return str(model or "")


def model_average_stats_for_model(model_path: str) -> Dict[str, Any]:
    candidates = [model_path]
    if model_path:
        candidates.append(Path(model_path).name)
    candidates.append("ds4")

    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        stats = model_averages.get_stats(candidate)
        if stats.get("count", 0) > 0:
            return stats
    return model_averages.get_stats(model_path)


def current_model_average_stats() -> Dict[str, Any]:
    return model_average_stats_for_model(current_model_path_from_config())


engine_client.set_model_averages_provider(current_model_average_stats)

benchmark_runner = BenchmarkRunner(engine_client, model_averages=model_averages)
updater = DS4Updater(repo=DS4_GITHUB_REPO, binary_path=DS4_BINARY)


class ConfigUpdate(BaseModel):
    key: str
    value: Any


class BenchmarkRunRequest(BaseModel):
    suite_id: str = "quick_smoke"
    suite: Optional[str] = None
    iterations: int = 1
    compare_label: Optional[str] = None
    config_overrides: Optional[Dict[str, Any]] = None


class BenchmarkCompareRequest(BaseModel):
    suite: str = "quick_smoke"
    iterations: int = 1
    config_a: Any
    config_b: Any


class UpdateRequest(BaseModel):
    apply: bool = False
    asset_url: Optional[str] = None
    sha256: Optional[str] = None


def get_dashboard_config() -> Dict[str, Any]:
    return config_manager.get_config()


def get_config_schema(*, force_refresh: bool = False) -> Dict[str, Dict[str, Any]]:
    schema = config_manager.get_schema(force_refresh=force_refresh)
    enriched: Dict[str, Dict[str, Any]] = {}
    for key, meta in schema.items():
        item = dict(meta)
        default = item.get("default")
        current = item.get("current", default)
        item["current"] = current
        item["overridden"] = not config_values_equal(default, current)
        enriched[key] = item
    return enriched


def config_values_equal(left: Any, right: Any) -> bool:
    try:
        return json.dumps(left, sort_keys=True, default=str) == json.dumps(right, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return str(left) == str(right)


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
    # telemetry_kv first, then config values override — prevents null telemetry
    # from overwriting the real budget_bytes from config_manager
    status["kv_cache"] = {
        **telemetry_kv,
        "path": kv_cache.get("path"),
        "budget_mib": kv_cache.get("budget_mib"),
        "budget_bytes": kv_cache.get("budget_bytes"),
        "disk_used_bytes": disk_kv.get("used_bytes"),
        "disk_fill_percent": disk_kv.get("fill_percent"),
    }

    # Attach per-model running averages for the currently-active model
    current_model = current_model_path_from_config(config)
    status["model_averages"] = model_average_stats_for_model(current_model)
    status["model_averages_all"] = model_averages.get_all_stats()
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


def normalize_benchmark_config(raw: Any, fallback_label: str) -> Dict[str, Any]:
    label = fallback_label
    profile_id = fallback_label.lower().replace(" ", "-")
    overrides: Dict[str, Any] = {}

    if isinstance(raw, dict):
        label = str(raw.get("label") or raw.get("name") or fallback_label)
        profile_id = str(raw.get("id") or label.lower().replace(" ", "-"))
        raw_overrides = raw.get("overrides") or raw.get("config_overrides") or {}
        if isinstance(raw_overrides, dict):
            overrides.update(raw_overrides)

        model_path = raw.get("model_path") or raw.get("model") or raw.get("path")
        if isinstance(model_path, dict):
            model_path = model_path.get("path")
        if model_path:
            overrides["model"] = str(model_path)
    elif isinstance(raw, str):
        label = raw
        profile_id = raw.lower().replace(" ", "-")
        if raw.endswith((".gguf", ".ggufv2", ".ggufv3")) or "/" in raw:
            label = Path(raw).name
            overrides["model"] = raw

    return {"id": profile_id, "label": label, "overrides": overrides}


def restore_config_overrides(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    current = config_manager.get_overrides()
    changed_keys = set(current) ^ set(snapshot)
    for key in set(current).intersection(snapshot):
        if current[key] != snapshot[key]:
            changed_keys.add(key)

    for key in list(current):
        config_manager.clear_override(key)

    applied = []
    for key, value in snapshot.items():
        applied.append(config_manager.set_override(key, value))

    return {
        "applied": applied,
        "restart_needed": any(config_manager.key_requires_restart(key) for key in changed_keys),
    }


def apply_benchmark_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    applied = []
    restart_needed = False
    for key, value in (profile.get("overrides") or {}).items():
        updated = config_manager.set_override(key, value)
        applied.append(updated)
        restart_needed = restart_needed or bool(updated.get("restart_needed"))

    restart = {"triggered": False, "exit_code": 0, "stdout": "", "stderr": "", "method": "none"}
    if restart_needed:
        restart = config_manager.restart_ds4(restart_script=RESTART_SCRIPT)

    return {"applied": applied, "restart_needed": restart_needed, "restart": restart}


def run_benchmark_with_profile(
    *,
    suite_id: str,
    iterations: int,
    profile: Dict[str, Any],
    compare_label: Optional[str],
    side: str,
) -> Dict[str, Any]:
    apply_result = apply_benchmark_profile(profile)
    result = benchmark_runner.run_suite(
        suite_id,
        iterations=iterations,
        compare_label=compare_label or profile["label"],
        config_overrides=profile.get("overrides") or {},
    )
    result["compare_side"] = side
    result["compare_config"] = profile
    return {"profile": profile, "apply": apply_result, "result": result}


def metric_diff(a_value: Any, b_value: Any, *, higher_is_better: bool) -> Dict[str, Any]:
    if a_value is None or b_value is None:
        return {
            "a": a_value,
            "b": b_value,
            "delta": None,
            "higher_is_better": higher_is_better,
            "improved": None,
        }
    if not isinstance(a_value, (int, float)) or not isinstance(b_value, (int, float)):
        return {
            "a": a_value,
            "b": b_value,
            "delta": None,
            "higher_is_better": higher_is_better,
            "improved": None,
        }
    delta = b_value - a_value
    improved = delta > 0 if higher_is_better else delta < 0
    if delta == 0:
        improved = None
    return {
        "a": a_value,
        "b": b_value,
        "delta": delta,
        "higher_is_better": higher_is_better,
        "improved": improved,
    }


def compare_task_results(result_a: Dict[str, Any], result_b: Dict[str, Any]) -> list[Dict[str, Any]]:
    tasks_a = {task["task_id"]: task for task in (result_a.get("tasks") or [])}
    tasks_b = {task["task_id"]: task for task in (result_b.get("tasks") or [])}
    task_rows = []
    for task_id in sorted(set(tasks_a) | set(tasks_b)):
        task_a = tasks_a.get(task_id) or {}
        task_b = tasks_b.get(task_id) or {}
        task_rows.append(
            {
                "task_id": task_id,
                "title": task_b.get("title") or task_a.get("title") or task_id,
                "passed": metric_diff(task_a.get("passed"), task_b.get("passed"), higher_is_better=True),
                "score": metric_diff(task_a.get("score"), task_b.get("score"), higher_is_better=True),
                "tok_s": metric_diff(task_a.get("tok_s"), task_b.get("tok_s"), higher_is_better=True),
                "latency_seconds": metric_diff(
                    task_a.get("latency_seconds"),
                    task_b.get("latency_seconds"),
                    higher_is_better=False,
                ),
            }
        )
    return task_rows


def build_benchmark_comparison(request: BenchmarkCompareRequest) -> Dict[str, Any]:
    suite_id = request.suite
    iterations = max(1, min(int(request.iterations), 10))
    profile_a = normalize_benchmark_config(request.config_a, "Config A")
    profile_b = normalize_benchmark_config(request.config_b, "Config B")

    if profile_a["id"] == profile_b["id"] and profile_a["overrides"] == profile_b["overrides"]:
        raise ValueError("Config A and Config B must be different.")

    original_overrides = config_manager.get_overrides()
    restore_result: Optional[Dict[str, Any]] = None
    try:
        restore_config_overrides(original_overrides)
        run_a = run_benchmark_with_profile(
            suite_id=suite_id,
            iterations=iterations,
            profile=profile_a,
            compare_label=f"{profile_a['label']}:{suite_id}",
            side="a",
        )
        restore_config_overrides(original_overrides)
        run_b = run_benchmark_with_profile(
            suite_id=suite_id,
            iterations=iterations,
            profile=profile_b,
            compare_label=f"{profile_b['label']}:{suite_id}",
            side="b",
        )
    finally:
        restore_result = restore_config_overrides(original_overrides)
        if restore_result.get("restart_needed"):
            restore_result["restart"] = config_manager.restart_ds4(restart_script=RESTART_SCRIPT)

    result_a = run_a["result"]
    result_b = run_b["result"]
    metrics = {
        "tok_s_avg": metric_diff(result_a.get("tok_s_avg"), result_b.get("tok_s_avg"), higher_is_better=True),
        "latency_p50_seconds": metric_diff(
            result_a.get("latency_p50_seconds"),
            result_b.get("latency_p50_seconds"),
            higher_is_better=False,
        ),
        "latency_p95_seconds": metric_diff(
            result_a.get("latency_p95_seconds"),
            result_b.get("latency_p95_seconds"),
            higher_is_better=False,
        ),
        "pass_rate": metric_diff(result_a.get("pass_rate"), result_b.get("pass_rate"), higher_is_better=True),
        "duration_seconds": metric_diff(
            result_a.get("duration_seconds"),
            result_b.get("duration_seconds"),
            higher_is_better=False,
        ),
        "output_tokens": metric_diff(result_a.get("output_tokens"), result_b.get("output_tokens"), higher_is_better=True),
    }
    return {
        "suite": suite_id,
        "iterations": iterations,
        "config_a": profile_a,
        "config_b": profile_b,
        "run_a": run_a,
        "run_b": run_b,
        "diffs": metrics,
        "task_diffs": compare_task_results(result_a, result_b),
        "restore": restore_result,
    }


tool_registry = DashboardToolRegistry(
    status_provider=get_status_payload,
    metrics_provider=get_metrics_payload,
    schema_provider=get_config_schema,
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
    return get_config_schema(force_refresh=refresh)


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

# ── Config Apply & Restart ────────────────────────────────────

RESTART_SCRIPT = str(BASE_DIR / "scripts" / "restart-ds4.sh")

class ConfigApplyRequest(BaseModel):
    key: str
    value: Any
    restart: bool = True

@app.post("/api/config/apply")
async def api_apply_config(request: ConfigApplyRequest) -> Dict[str, Any]:
    """Apply a config override and optionally restart DS4 if the key requires it."""
    try:
        result = config_manager.apply_and_restart(
            request.key,
            request.value,
            restart_script=RESTART_SCRIPT,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "result": result, "config": config_manager.get_config()}

@app.post("/api/restart")
async def api_restart_ds4() -> Dict[str, Any]:
    """Restart DS4 via launchctl without changing any config."""
    result = config_manager.restart_ds4(restart_script=RESTART_SCRIPT)
    return {"ok": result.get("exit_code") == 0, **result}


@app.get("/api/config-overrides")
async def api_config_overrides() -> Dict[str, Any]:
    return config_manager.get_overrides()


# ── Model Discovery & Switching ──────────────────────────────────

@app.get("/api/models")
async def api_list_models() -> Dict[str, Any]:
    """List available GGUF models from known search paths."""
    config = config_manager.get_config()
    current_model_path = current_model_path_from_config(config)
    models = discover_models(model_paths=MODEL_SEARCH_PATHS)
    return {
        "models": models,
        "current_model": current_model_path or config.get("model", ""),
        "averages": model_averages.get_all_stats(),
    }


@app.get("/api/model-descriptions")
async def api_model_descriptions() -> Dict[str, str]:
    """Return Hugging Face model-card descriptions keyed by local model path."""
    models = discover_models(model_paths=MODEL_SEARCH_PATHS)

    def load_descriptions() -> Dict[str, str]:
        descriptions: Dict[str, str] = {}
        for model in models:
            path = str(model.get("path") or "")
            repo = str(model.get("repo") or "")
            if not path:
                continue
            descriptions[path] = fetch_model_card_description(repo) if repo else ""
        return descriptions

    return await asyncio.to_thread(load_descriptions)


class SwitchModelRequest(BaseModel):
    model_path: str
    restart: bool = True

@app.post("/api/models/switch")
async def api_switch_model(request: SwitchModelRequest) -> Dict[str, Any]:
    """Switch to a different GGUF model and restart DS4."""
    path = Path(request.model_path).expanduser().resolve()
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Model path does not exist: {path}")

    if not path.suffix in (".gguf", ".ggufv2", ".ggufv3"):
        raise HTTPException(status_code=400, detail="Not a GGUF file")

    result = config_manager.apply_and_restart(
        "model",
        str(path),
        restart_script=RESTART_SCRIPT,
    )
    return {"ok": True, "result": result, "config": config_manager.get_config()}


@app.get("/api/benchmarks")
async def api_benchmark_suites() -> Dict[str, Any]:
    return {"suites": benchmark_runner.list_suites(), "last_results": benchmark_runner.get_last_results()}


@app.post("/api/benchmarks/run")
async def api_run_benchmark(request: BenchmarkRunRequest) -> Dict[str, Any]:
    suite_id = request.suite or request.suite_id
    try:
        if request.config_overrides:
            original_overrides = config_manager.get_overrides()
            profile = normalize_benchmark_config(
                {"label": request.compare_label or "Benchmark config", "overrides": request.config_overrides},
                "Benchmark config",
            )
            try:
                result = await asyncio.to_thread(
                    run_benchmark_with_profile,
                    suite_id=suite_id,
                    iterations=request.iterations,
                    profile=profile,
                    compare_label=request.compare_label,
                    side="single",
                )
            finally:
                restore_result = restore_config_overrides(original_overrides)
                if restore_result.get("restart_needed"):
                    config_manager.restart_ds4(restart_script=RESTART_SCRIPT)
            return result["result"]

        result = await asyncio.to_thread(
            benchmark_runner.run_suite,
            suite_id,
            iterations=request.iterations,
            compare_label=request.compare_label,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return result


@app.get("/api/benchmarks/results")
async def api_benchmark_results() -> Dict[str, Any]:
    return {"results": benchmark_runner.get_last_results()}


@app.get("/api/benchmarks/history")
async def api_benchmark_history() -> Dict[str, Any]:
    return {"history": benchmark_runner.get_history()}


@app.post("/api/benchmarks/compare")
async def api_run_benchmark_compare(request: BenchmarkCompareRequest) -> Dict[str, Any]:
    try:
        return await asyncio.to_thread(build_benchmark_comparison, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/benchmarks/compare")
async def api_benchmark_compare(baseline: str, target: str) -> Dict[str, Any]:
    """Compare two benchmark runs by compare_label or run_id.
    Returns side-by-side results with computed diffs for key metrics.
    """
    try:
        comparison = benchmark_runner.compare(baseline_label=baseline, target_label=target)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return comparison


@app.get("/api/update/check")
async def api_update_check() -> Dict[str, Any]:
    return updater.check_latest_release()


@app.post("/api/update")
async def api_update(request: UpdateRequest) -> Dict[str, Any]:
    return updater.update(apply=request.apply, asset_url=request.asset_url, sha256=request.sha256)


@app.post("/api/update/rollback")
async def api_update_rollback() -> Dict[str, Any]:
    return updater.rollback()


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
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="Run the DS4 Dwarfstar Dashboard.")
    parser.add_argument("--host", default=os.environ.get("DASHBOARD_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("DASHBOARD_PORT", "8765")))
    parser.add_argument("--reload", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--mcp-stdio", action="store_true", help="Run the MCP JSON-RPC server over stdio.")
    args = parser.parse_args()

    if args.mcp_stdio:
        asyncio.run(run_stdio(mcp_rpc_server))
        raise SystemExit(0)

    uvicorn.run("dashboard:app", host=args.host, port=args.port, reload=args.reload)

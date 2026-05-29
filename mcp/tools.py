from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from benchmarks.runner import BenchmarkRunner
from bridge.config_manager import DS4ConfigManager
from updater.updater import DS4Updater


class DashboardToolRegistry:
    def __init__(
        self,
        *,
        status_provider: Callable[[], Dict[str, Any]],
        metrics_provider: Callable[[], Dict[str, Any]],
        config_manager: DS4ConfigManager,
        benchmark_runner: BenchmarkRunner,
        updater: DS4Updater,
    ) -> None:
        self.status_provider = status_provider
        self.metrics_provider = metrics_provider
        self.config_manager = config_manager
        self.benchmark_runner = benchmark_runner
        self.updater = updater

    def list_tools(self) -> list[Dict[str, Any]]:
        return [
            {
                "name": "get_status",
                "description": "Current DS4 status, uptime, model, port, and dashboard config.",
                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            },
            {
                "name": "get_metrics",
                "description": "Live telemetry, KV cache, GPU, CPU, temperature, and memory metrics.",
                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            },
            {
                "name": "set_config",
                "description": "Apply an in-dashboard config override by key and value.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"key": {"type": "string"}, "value": {}},
                    "required": ["key", "value"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "get_config",
                "description": "Read the current dashboard config snapshot.",
                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            },
            {
                "name": "run_benchmark",
                "description": "Execute a predefined benchmark suite and return results.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "suite_id": {"type": "string"},
                        "iterations": {"type": "integer", "minimum": 1, "maximum": 10},
                        "compare_label": {"type": "string"},
                    },
                    "required": ["suite_id"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "restart_ds4",
                "description": "Restart DS4 through the configured launchd service.",
                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            },
            {
                "name": "update_ds4",
                "description": "Check for or apply a DS4 binary update from GitHub releases.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "apply": {"type": "boolean"},
                        "asset_url": {"type": "string"},
                        "sha256": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            },
            {
                "name": "get_schema",
                "description": "List all available DS4 config options discovered from defaults, --help, and telemetry.",
                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            },
        ]

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        args = arguments or {}
        if name == "get_status":
            return self.status_provider()
        if name == "get_metrics":
            return self.metrics_provider()
        if name == "set_config":
            result = self.config_manager.set_override(str(args.get("key", "")), args.get("value", ""))
            return {"ok": True, "updated": result, "config": self.config_manager.get_config()}
        if name == "get_config":
            return self.config_manager.get_config()
        if name == "run_benchmark":
            return self.benchmark_runner.run_suite(
                str(args.get("suite_id", "quick_smoke")),
                iterations=int(args.get("iterations", 1)),
                compare_label=args.get("compare_label"),
            )
        if name == "restart_ds4":
            result = self.config_manager.restart_ds4()
            return {"ok": result.get("exit_code") == 0, **result}
        if name == "update_ds4":
            return self.updater.update(
                apply=bool(args.get("apply", False)),
                asset_url=args.get("asset_url"),
                sha256=args.get("sha256"),
            )
        if name == "get_schema":
            return self.config_manager.get_schema()
        raise KeyError(f"Unknown MCP tool: {name}")

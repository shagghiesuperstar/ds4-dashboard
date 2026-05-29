from __future__ import annotations

from typing import Any, Callable, Dict

from benchmarks.runner import BenchmarkRunner
from bridge.config_manager import DS4ConfigManager


class DashboardResourceRegistry:
    def __init__(
        self,
        *,
        telemetry_provider: Callable[[], Dict[str, Any]],
        config_manager: DS4ConfigManager,
        benchmark_runner: BenchmarkRunner,
    ) -> None:
        self.telemetry_provider = telemetry_provider
        self.config_manager = config_manager
        self.benchmark_runner = benchmark_runner

    def list_resources(self) -> list[Dict[str, Any]]:
        return [
            {
                "uri": "telemetry://stream",
                "name": "Live Telemetry Stream",
                "description": "Subscribable status and metrics stream exposed over SSE.",
                "mimeType": "application/json",
            },
            {
                "uri": "config://current",
                "name": "Current Config",
                "description": "Current DS4 dashboard config snapshot.",
                "mimeType": "application/json",
            },
            {
                "uri": "benchmarks://results",
                "name": "Benchmark Results",
                "description": "Most recent benchmark run results.",
                "mimeType": "application/json",
            },
        ]

    def read_resource(self, uri: str) -> Dict[str, Any]:
        if uri == "telemetry://stream":
            return self.telemetry_provider()
        if uri == "config://current":
            return self.config_manager.get_config()
        if uri == "benchmarks://results":
            return {"results": self.benchmark_runner.get_last_results()}
        raise KeyError(f"Unknown MCP resource: {uri}")

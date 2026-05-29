from __future__ import annotations

import statistics
import time
import uuid
from typing import Any, Dict, List, Optional

from bridge.engine_client import DS4EngineClient

from .coding import score_response
from .suites import get_suite, list_suites


class BenchmarkRunner:
    def __init__(self, engine_client: DS4EngineClient) -> None:
        self.engine_client = engine_client
        self._last_results: List[Dict[str, Any]] = []

    def list_suites(self) -> List[Dict[str, Any]]:
        return list_suites()

    def get_last_results(self) -> List[Dict[str, Any]]:
        return list(self._last_results)

    def run_suite(
        self,
        suite_id: str,
        *,
        iterations: int = 1,
        compare_label: Optional[str] = None,
    ) -> Dict[str, Any]:
        suite = get_suite(suite_id)
        run_id = uuid.uuid4().hex[:12]
        started_at = time.time()
        iterations = max(1, min(int(iterations), 10))

        task_results: List[Dict[str, Any]] = []
        for iteration in range(iterations):
            for task in suite["tasks"]:
                generation = self.engine_client.generate(
                    str(task["prompt"]),
                    max_tokens=int(suite["max_tokens"]),
                    temperature=float(suite["temperature"]),
                )
                scoring = score_response(task, generation.get("text", ""))
                task_results.append(
                    {
                        "suite_id": suite_id,
                        "run_id": run_id,
                        "iteration": iteration + 1,
                        "task_id": task["id"],
                        "kind": task["kind"],
                        "title": task["title"],
                        "passed": scoring["passed"] if generation.get("ok") else False,
                        "score": scoring["score"] if generation.get("ok") else 0.0,
                        "marker_hits": scoring["marker_hits"] if generation.get("ok") else [],
                        "latency_seconds": generation.get("latency_seconds", 0.0),
                        "output_tokens": generation.get("output_tokens", 0),
                        "tok_s": generation.get("tok_s"),
                        "error": generation.get("error"),
                        "response_excerpt": generation.get("text", "")[:800],
                    }
                )

        completed_at = time.time()
        latencies = [float(item["latency_seconds"]) for item in task_results if item["latency_seconds"]]
        tok_s_values = [float(item["tok_s"]) for item in task_results if item.get("tok_s")]
        pass_count = len([item for item in task_results if item["passed"]])
        total_tokens = sum(int(item.get("output_tokens") or 0) for item in task_results)

        result = {
            "run_id": run_id,
            "suite_id": suite_id,
            "suite_name": suite["name"],
            "compare_label": compare_label,
            "started_at": started_at,
            "completed_at": completed_at,
            "duration_seconds": completed_at - started_at,
            "iterations": iterations,
            "task_count": len(task_results),
            "pass_count": pass_count,
            "pass_rate": pass_count / len(task_results) * 100 if task_results else 0.0,
            "latency_p50_seconds": self._percentile(latencies, 50),
            "latency_p95_seconds": self._percentile(latencies, 95),
            "tok_s_avg": statistics.fmean(tok_s_values) if tok_s_values else None,
            "output_tokens": total_tokens,
            "estimated_cost_usd": 0.0,
            "tasks": task_results,
        }
        self._last_results.insert(0, result)
        self._last_results = self._last_results[:20]
        return result

    def _percentile(self, values: List[float], percentile: int) -> Optional[float]:
        if not values:
            return None
        if len(values) == 1:
            return values[0]
        values = sorted(values)
        index = (len(values) - 1) * percentile / 100
        lower = int(index)
        upper = min(lower + 1, len(values) - 1)
        if lower == upper:
            return values[lower]
        weight = index - lower
        return values[lower] * (1 - weight) + values[upper] * weight

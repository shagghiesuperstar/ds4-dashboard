from __future__ import annotations

import statistics
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from bridge.engine_client import DS4EngineClient
from bridge.model_averages import ModelRunningAverages

from .coding import score_response
from .suites import get_suite, list_suites


class BenchmarkRunner:
    def __init__(self, engine_client: DS4EngineClient, *, model_averages: Optional[ModelRunningAverages] = None) -> None:
        self.engine_client = engine_client
        self.model_averages = model_averages
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
        config_overrides: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        suite = get_suite(suite_id)
        run_id = uuid.uuid4().hex[:12]
        started_at = time.time()
        iterations = max(1, min(int(iterations), 10))
        config_overrides = dict(config_overrides or {})
        model_override = config_overrides.get("model")
        model_name = Path(str(model_override)).name if model_override else suite.get("model_name", "ds4")

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
                # Feed generation metrics into per-model running averages
                if self.model_averages and generation.get("ok"):
                    self.model_averages.record(
                        model_name,
                        tok_s=generation.get("tok_s"),
                        latency_seconds=generation.get("latency_seconds"),
                        output_tokens=generation.get("output_tokens"),
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
            "config_overrides": config_overrides,
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
        return values[min(int(index), len(values) - 1)]

    def compare(self, baseline_label: str, target_label: str) -> Dict[str, Any]:
        """Find two results by compare_label (or run_id fallback) and return a diff."""
        baseline = None
        target = None
        for r in self._last_results:
            label = r.get("compare_label") or r.get("run_id")
            if label == baseline_label:
                baseline = r
            if label == target_label:
                target = r
        if not baseline:
            raise KeyError(f"No baseline result matching '{baseline_label}'")
        if not target:
            raise KeyError(f"No target result matching '{target_label}'")

        def _diff(b, t):
            if b is None and t is None:
                return None
            if b is None:
                return {"baseline": None, "target": t, "delta": None}
            if t is None:
                return {"baseline": b, "target": None, "delta": None}
            delta = t - b if isinstance(b, (int, float)) and isinstance(t, (int, float)) else None
            direction = "up" if delta and delta > 0 else "down" if delta and delta < 0 else "flat"
            return {"baseline": b, "target": t, "delta": delta, "direction": direction}

        # Aggregate diffs
        diffs = {
            "tok_s_avg": _diff(baseline.get("tok_s_avg"), target.get("tok_s_avg")),
            "pass_rate": _diff(baseline.get("pass_rate"), target.get("pass_rate")),
            "latency_p50_seconds": _diff(baseline.get("latency_p50_seconds"), target.get("latency_p50_seconds")),
            "latency_p95_seconds": _diff(baseline.get("latency_p95_seconds"), target.get("latency_p95_seconds")),
            "duration_seconds": _diff(baseline.get("duration_seconds"), target.get("duration_seconds")),
            "output_tokens": _diff(baseline.get("output_tokens"), target.get("output_tokens")),
            "task_count": _diff(baseline.get("task_count"), target.get("task_count")),
        }

        # Per-task diffs
        task_diffs = []
        baseline_tasks = {t["task_id"]: t for t in (baseline.get("tasks") or [])}
        target_tasks = {t["task_id"]: t for t in (target.get("tasks") or [])}
        all_task_ids = sorted(set(list(baseline_tasks.keys()) + list(target_tasks.keys())))
        for tid in all_task_ids:
            b = baseline_tasks.get(tid)
            t = target_tasks.get(tid)
            task_diffs.append({
                "task_id": tid,
                "title": (t or b).get("title"),
                "kind": (t or b).get("kind"),
                "passed": _diff(b["passed"] if b else None, t["passed"] if t else None),
                "score": _diff(b["score"] if b else None, t["score"] if t else None),
                "tok_s": _diff(b["tok_s"] if b else None, t["tok_s"] if t else None),
                "latency_seconds": _diff(b["latency_seconds"] if b else None, t["latency_seconds"] if t else None),
            })

        return {
            "baseline": {"label": baseline_label, "result": baseline},
            "target": {"label": target_label, "result": target},
            "diffs": diffs,
            "task_diffs": task_diffs,
        }

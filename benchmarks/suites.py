from __future__ import annotations

from typing import Any, Dict, List

from .agent_suite import AGENTIC_FULL_SUITE, AGENTIC_SMOKE_SUITE


BENCHMARK_SUITES: Dict[str, Dict[str, Any]] = {
    "quick_smoke": {
        "id": "quick_smoke",
        "name": "Quick Smoke Test",
        "description": "Fast coding and tool-reasoning probes for a live DS4 sanity check.",
        "max_tokens": 220,
        "temperature": 0.0,
        "tasks": [
            {
                "id": "fib_function",
                "kind": "coding",
                "title": "Fibonacci Function",
                "prompt": (
                    "Write a Python function `fib(n)` that returns the nth Fibonacci number. "
                    "Use an iterative implementation and include only code."
                ),
                "markers": ["def fib", "return"],
            },
            {
                "id": "tool_plan",
                "kind": "agentic",
                "title": "Tool-Calling Plan",
                "prompt": (
                    "You can call tools named get_metrics, set_config, and run_benchmark. "
                    "List the exact three tool calls you would make to compare current DS4 health "
                    "before and after changing context_window to 131072."
                ),
                "markers": ["get_metrics", "set_config", "run_benchmark"],
            },
        ],
    },
    "full_coding": {
        "id": "full_coding",
        "name": "Full Coding Eval",
        "description": "HumanEval-style function completion, generation, and bug-fix prompts.",
        "max_tokens": 420,
        "temperature": 0.0,
        "tasks": [
            {
                "id": "dedupe_preserve_order",
                "kind": "coding",
                "title": "Dedupe Preserve Order",
                "prompt": (
                    "Write Python code for `dedupe_preserve_order(items)` that returns a list with duplicates "
                    "removed while preserving first occurrence order. Include only the function."
                ),
                "markers": ["def dedupe_preserve_order", "set", "append", "return"],
            },
            {
                "id": "parse_duration",
                "kind": "coding",
                "title": "Parse Duration",
                "prompt": (
                    "Write a Python function `parse_duration(text)` that accepts strings like '2h 5m 9s' "
                    "and returns total seconds. Missing units should count as zero."
                ),
                "markers": ["def parse_duration", "seconds", "return"],
            },
            {
                "id": "bug_fix_average",
                "kind": "bugfix",
                "title": "Bug Fix Average",
                "prompt": (
                    "Fix this Python function and return only corrected code:\n"
                    "def average(values):\n"
                    "    total = 0\n"
                    "    for value in values:\n"
                    "        total = value\n"
                    "    return total / len(value)\n"
                ),
                "markers": ["for value in values", "+=", "len(values)", "return"],
            },
        ],
    },
    "agentic_smoke": AGENTIC_SMOKE_SUITE,
    "agentic_full": AGENTIC_FULL_SUITE,
    "agentic_endurance": {
        "id": "agentic_endurance",
        "name": "Agentic Endurance",
        "description": "Multi-turn planning and tool-use scenarios for sustained management behavior.",
        "max_tokens": 520,
        "temperature": 0.1,
        "tasks": [
            {
                "id": "diagnose_kv_pressure",
                "kind": "agentic",
                "title": "Diagnose KV Pressure",
                "prompt": (
                    "A DS4 dashboard reports KV cache fill at 91%, GPU utilization at 28%, and tok/s falling. "
                    "Describe a concise tool-driven response using get_metrics, get_config, set_config, "
                    "and run_benchmark. Include rollback criteria."
                ),
                "markers": ["get_metrics", "get_config", "set_config", "run_benchmark", "rollback"],
            },
            {
                "id": "compare_configs",
                "kind": "agentic",
                "title": "Compare Configs",
                "prompt": (
                    "Plan an experiment that compares two DS4 configurations for coding throughput. "
                    "Specify benchmark suite choice, metrics to capture, and how to decide the winner."
                ),
                "markers": ["benchmark", "tok", "latency", "pass"],
            },
            {
                "id": "update_safety",
                "kind": "agentic",
                "title": "Update Safety",
                "prompt": (
                    "List the steps an agent should take before calling update_ds4 on a production DS4 host. "
                    "Mention verification, backup, and rollback."
                ),
                "markers": ["verify", "backup", "rollback"],
            },
        ],
    },
}


def list_suites() -> List[Dict[str, Any]]:
    return [
        {
            "id": suite["id"],
            "name": suite["name"],
            "description": suite["description"],
            "task_count": len(suite["tasks"]),
            "max_tokens": suite["max_tokens"],
            "temperature": suite["temperature"],
        }
        for suite in BENCHMARK_SUITES.values()
    ]


def get_suite(suite_id: str) -> Dict[str, Any]:
    try:
        return BENCHMARK_SUITES[suite_id]
    except KeyError as exc:
        raise KeyError(f"Unknown benchmark suite: {suite_id}") from exc

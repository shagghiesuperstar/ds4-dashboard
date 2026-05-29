"""
Per-model running averages for tok/s, prefill tok/s, latency.
Tracks min/max/avg/count per model so the dashboard can display
meaningful numbers even when DS4 telemetry is unavailable.
"""

from __future__ import annotations

import statistics
from typing import Any, Dict, List, Optional


class ModelRunningAverages:
    """Thread-safe running averages per model name/path.

    Each generation call feeds in a datapoint. The dashboard reads
    the aggregated stats for the currently active model.
    """

    def __init__(self) -> None:
        self._models: Dict[str, List[Dict[str, Any]]] = {}

    def record(
        self,
        model: str,
        *,
        tok_s: Optional[float] = None,
        prefill_tok_s: Optional[float] = None,
        latency_seconds: Optional[float] = None,
        output_tokens: Optional[int] = None,
        prefill_ms: Optional[float] = None,
    ) -> None:
        if model not in self._models:
            self._models[model] = []
        self._models[model].append({
            "tok_s": tok_s,
            "prefill_tok_s": prefill_tok_s,
            "latency_seconds": latency_seconds,
            "output_tokens": output_tokens,
            "prefill_ms": prefill_ms,
        })

    def get_stats(self, model: str, *, window: int = 50) -> Dict[str, Any]:
        points = self._models.get(model, [])
        if not points:
            return {"count": 0}

        # Use only the last N for sliding window
        recent = points[-window:] if len(points) > window else points

        tok_s_values = [p["tok_s"] for p in recent if p["tok_s"] is not None]
        prefill_values = [p["prefill_tok_s"] for p in recent if p["prefill_tok_s"] is not None]
        latency_values = [p["latency_seconds"] for p in recent if p["latency_seconds"] is not None]
        output_tokens = [p["output_tokens"] for p in recent if p["output_tokens"] is not None]

        def _agg(values):
            if not values:
                return {"min": None, "max": None, "avg": None, "count": 0}
            return {
                "min": min(values),
                "max": max(values),
                "avg": statistics.fmean(values) if len(values) > 1 else values[0],
                "count": len(values),
            }

        return {
            "model": model,
            "total_calls": len(points),
            "window_size": len(recent),
            "tok_s": _agg(tok_s_values),
            "prefill_tok_s": _agg(prefill_values),
            "latency_seconds": _agg(latency_values),
            "output_tokens": _agg(output_tokens),
        }

    def get_all_stats(self) -> Dict[str, Any]:
        result = {}
        for model in self._models:
            result[model] = self.get_stats(model)
        return result

    def list_models(self) -> List[str]:
        return sorted(self._models.keys())

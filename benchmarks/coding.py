from __future__ import annotations

from typing import Any, Dict


def score_response(task: Dict[str, Any], response_text: str) -> Dict[str, Any]:
    markers = [str(marker) for marker in task.get("markers", [])]
    normalized = response_text.lower()
    hits = [marker for marker in markers if marker.lower() in normalized]
    score = len(hits) / len(markers) if markers else 0.0

    return {
        "score": score,
        "passed": bool(markers) and score >= 0.66,
        "marker_hits": hits,
        "marker_count": len(markers),
    }

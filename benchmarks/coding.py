from __future__ import annotations

import re
from typing import Any, Dict, List


COMMON_NON_TOOL_CALLS = {
    "abs",
    "all",
    "any",
    "bool",
    "dict",
    "enumerate",
    "float",
    "int",
    "len",
    "list",
    "max",
    "min",
    "open",
    "print",
    "range",
    "round",
    "set",
    "sorted",
    "str",
    "sum",
    "tuple",
}


def score_response(task: Dict[str, Any], response_text: str) -> Dict[str, Any]:
    if task.get("scoring"):
        return _score_agentic_response(task, response_text)

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


def _score_agentic_response(task: Dict[str, Any], response_text: str) -> Dict[str, Any]:
    scoring = task.get("scoring") or {}
    marker_hits = _marker_hits(task, response_text)
    criteria: Dict[str, Dict[str, Any]] = {
        "correct_tool_selection": _score_tool_selection(scoring, response_text),
        "correct_parameter_extraction": _score_parameter_extraction(scoring, response_text),
        "coherent_response_formatting": _score_response_formatting(scoring, response_text),
        "no_hallucinated_tools": _score_no_hallucinated_tools(scoring, response_text),
    }
    scores = [item["score"] for item in criteria.values()]
    score = sum(scores) / len(scores) if scores else 0.0
    passed = all(item["score"] >= 0.66 for item in criteria.values()) and criteria["no_hallucinated_tools"]["score"] == 1.0

    return {
        "score": score,
        "passed": passed,
        "marker_hits": marker_hits,
        "marker_count": len(task.get("markers", [])),
        "criteria": criteria,
    }


def _marker_hits(task: Dict[str, Any], response_text: str) -> List[str]:
    markers = [str(marker) for marker in task.get("markers", [])]
    normalized = _normalized(response_text)
    compact = _compact(response_text)
    return [
        marker
        for marker in markers
        if _normalized(marker) in normalized or _compact(marker) in compact
    ]


def _score_tool_selection(scoring: Dict[str, Any], response_text: str) -> Dict[str, Any]:
    required_tools = [str(tool) for tool in scoring.get("required_tools", [])]
    tool_counts = {str(tool): int(count) for tool, count in (scoring.get("tool_counts") or {}).items()}
    if not required_tools and not tool_counts:
        return {"score": 1.0, "passed": True, "detail": "No tool required."}

    checks = []
    for tool in sorted(set(required_tools) | set(tool_counts)):
        actual = _tool_call_count(response_text, tool)
        expected = tool_counts.get(tool)
        if expected is None:
            passed = actual >= 1
        else:
            passed = actual == expected
        checks.append({"tool": tool, "expected": expected or ">=1", "actual": actual, "passed": passed})

    passed_count = len([check for check in checks if check["passed"]])
    score = passed_count / len(checks) if checks else 1.0
    return {"score": score, "passed": score >= 0.66, "checks": checks}


def _score_parameter_extraction(scoring: Dict[str, Any], response_text: str) -> Dict[str, Any]:
    required_parameters = scoring.get("required_parameters") or []
    parameter_patterns = [str(pattern) for pattern in scoring.get("parameter_patterns", [])]
    checks = []

    for expected in required_parameters:
        alternatives = expected if isinstance(expected, list) else [expected]
        hit = any(_contains_text(response_text, str(alt)) for alt in alternatives)
        checks.append({"expected": alternatives, "passed": hit})

    for pattern in parameter_patterns:
        try:
            hit = re.search(pattern, response_text, flags=re.IGNORECASE | re.MULTILINE) is not None
        except re.error:
            hit = False
        checks.append({"pattern": pattern, "passed": hit})

    if not checks:
        return {"score": 1.0, "passed": True, "detail": "No parameters required."}

    passed_count = len([check for check in checks if check["passed"]])
    score = passed_count / len(checks)
    return {"score": score, "passed": score >= 0.66, "checks": checks}


def _score_response_formatting(scoring: Dict[str, Any], response_text: str) -> Dict[str, Any]:
    format_markers = [str(marker) for marker in scoring.get("format_markers", [])]
    if not format_markers:
        return {"score": 1.0, "passed": True, "detail": "No response format required."}

    checks = [
        {"marker": marker, "passed": _contains_text(response_text, marker)}
        for marker in format_markers
    ]
    passed_count = len([check for check in checks if check["passed"]])
    score = passed_count / len(checks)
    return {"score": score, "passed": score >= 0.66, "checks": checks}


def _score_no_hallucinated_tools(scoring: Dict[str, Any], response_text: str) -> Dict[str, Any]:
    allowed_tools = {str(tool) for tool in scoring.get("allowed_tools", [])}
    called_tools = _called_tool_names(response_text)
    unexpected = sorted(called_tools - allowed_tools - COMMON_NON_TOOL_CALLS)
    return {
        "score": 0.0 if unexpected else 1.0,
        "passed": not unexpected,
        "allowed_tools": sorted(allowed_tools),
        "called_tools": sorted(called_tools),
        "unexpected_tools": unexpected,
    }


def _tool_call_count(response_text: str, tool: str) -> int:
    pattern = re.compile(rf"\b{re.escape(tool)}\s*\(", flags=re.IGNORECASE)
    return len(pattern.findall(response_text))


def _called_tool_names(response_text: str) -> set[str]:
    pattern = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
    return {match.group(1) for match in pattern.finditer(response_text)}


def _contains_text(response_text: str, expected: str) -> bool:
    return _normalized(expected) in _normalized(response_text) or _compact(expected) in _compact(response_text)


def _normalized(value: str) -> str:
    return " ".join(str(value).lower().split())


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", str(value).lower())

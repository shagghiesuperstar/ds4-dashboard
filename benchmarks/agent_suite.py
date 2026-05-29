from __future__ import annotations

from typing import Any, Dict, List


SCORING_CRITERIA: List[str] = [
    "correct_tool_selection",
    "correct_parameter_extraction",
    "coherent_response_formatting",
    "no_hallucinated_tools",
]


def _agentic_task(
    *,
    task_id: str,
    title: str,
    prompt: str,
    markers: List[str],
    required_tools: List[str] | None = None,
    tool_counts: Dict[str, int] | None = None,
    required_parameters: List[str | List[str]] | None = None,
    parameter_patterns: List[str] | None = None,
    format_markers: List[str] | None = None,
    allowed_tools: List[str] | None = None,
) -> Dict[str, Any]:
    return {
        "id": task_id,
        "kind": "agentic",
        "title": title,
        "prompt": prompt,
        "markers": markers,
        "scoring": {
            "criteria": SCORING_CRITERIA,
            "required_tools": required_tools or [],
            "tool_counts": tool_counts or {},
            "required_parameters": required_parameters or [],
            "parameter_patterns": parameter_patterns or [],
            "format_markers": format_markers or [],
            "allowed_tools": allowed_tools if allowed_tools is not None else required_tools or [],
        },
    }


AGENTIC_SMOKE_SUITE: Dict[str, Any] = {
    "id": "agentic_smoke",
    "name": "Agentic Smoke Test",
    "description": "Multi-turn reasoning and tool-calling probes for agentic DS4 behavior.",
    "max_tokens": 620,
    "temperature": 0.0,
    "tasks": [
        _agentic_task(
            task_id="weather_three_cities",
            title="Weather Lookup",
            prompt=(
                "You can call exactly one tool: get_weather(city). The user asks: "
                "'What is the weather in Tokyo, Paris, and Chicago?' "
                "Call get_weather(city) once for each city, then write a compact summary. "
                "Use this shape: Tool calls, then Summary."
            ),
            markers=["get_weather", "Tokyo", "Paris", "Chicago", "Summary"],
            required_tools=["get_weather"],
            tool_counts={"get_weather": 3},
            required_parameters=["Tokyo", "Paris", "Chicago"],
            format_markers=["Tool calls", "Summary"],
            allowed_tools=["get_weather"],
        ),
        _agentic_task(
            task_id="calculator_chain",
            title="Calculator Chain",
            prompt=(
                "You can call exactly one tool: calculate(expr). The user gives this "
                "multi-step arithmetic task: Start with 84. Add 16, multiply by 3, "
                "divide by 5, then subtract 7. Break the work into sequential "
                "calculate(expr) calls and report the final answer."
            ),
            markers=["calculate", "84", "16", "3", "5", "7", "Final"],
            required_tools=["calculate"],
            tool_counts={"calculate": 4},
            required_parameters=["84", "16", "3", "5", "7"],
            parameter_patterns=[r"\+", r"\*|x|multiply", r"/|divide", r"-|subtract"],
            format_markers=["Step", "Final"],
            allowed_tools=["calculate"],
        ),
        _agentic_task(
            task_id="python_execution_output",
            title="Code Execution",
            prompt=(
                "You can call exactly one tool: run_code(code). The user says: "
                "'run this Python and tell me the output.'\n\n"
                "values = [2, 4, 6]\n"
                "print(sum(v * v for v in values))\n\n"
                "Call run_code(code), then interpret the result for the user."
            ),
            markers=["run_code", "values", "sum", "56", "Output"],
            required_tools=["run_code"],
            tool_counts={"run_code": 1},
            required_parameters=["values = [2, 4, 6]", "sum(v * v for v in values)"],
            format_markers=["Output"],
            allowed_tools=["run_code"],
        ),
        _agentic_task(
            task_id="fact_verification",
            title="Fact Verification",
            prompt=(
                "The user asks: 'Was the first person to win two Nobel Prizes also "
                "the first woman to win a Nobel Prize?' Decompose the question into "
                "sub-queries, verify each fact, then synthesize the answer. Do not "
                "invent or call tools."
            ),
            markers=["Marie Curie", "Nobel", "Physics", "Chemistry", "yes"],
            required_parameters=[
                ["first person to win two Nobel Prizes", "two Nobel Prizes"],
                ["first woman to win a Nobel Prize", "first woman"],
                "Marie Curie",
            ],
            format_markers=["Sub-queries", "Verification", "Conclusion"],
            allowed_tools=[],
        ),
        _agentic_task(
            task_id="migration_plan",
            title="Planning",
            prompt=(
                "The user gives a high-level goal: Move a local DS4 dashboard from "
                "a laptop to a new Mac mini with minimal downtime. Create a "
                "step-by-step plan with estimated time per step, verification, and "
                "rollback. Do not invent or call tools."
            ),
            markers=["Step", "Estimated", "backup", "install", "verify", "rollback"],
            required_parameters=["DS4 dashboard", "Mac mini", "minimal downtime"],
            format_markers=["Step", "Estimated", "Verification", "Rollback"],
            allowed_tools=[],
        ),
    ],
}

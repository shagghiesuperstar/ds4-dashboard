# DS4 Dashboard — Phase 3

## Current State
Phase 1 and 2 are complete. Dashboard runs at port 8765 with DS4 on port 8001. All existing Python files pass syntax checks.

## Phase 3 Tasks (implement in order)

### Task 1 — Agentic Benchmark Suite
Create `benchmarks/agent_suite.py` with multi-turn reasoning and tool-calling scenarios:

- **Tool-calling scenarios** (3 tasks):
  - Weather lookup: user asks for weather in 3 cities, model must call `get_weather(city)` for each and format a summary
  - Calculator chain: user gives a multi-step arithmetic problem, model must break into steps using `calculate(expr)`
  - Code execution: user asks "run this Python and tell me the output", model must call `run_code(code)` and interpret result
- **Multi-turn reasoning** (2 tasks):
  - Fact verification: user asks a complex factual question, model must decompose into sub-queries, verify each, then synthesize
  - Planning: user gives a high-level goal, model must create a step-by-step plan with estimated time per step
- **Scoring**: Each task scored on (a) correct tool selection, (b) correct parameter extraction, (c) coherent response formatting, (d) no hallucinated tools
- **Suite registration**: Register as `agentic_smoke` in `benchmarks/suites.py` with label "Agentic Smoke Test"

### Task 2 — Historical Benchmark Chart
Add a Chart.js time-series chart to the dashboard showing historical benchmark results:

- **Backend** (`dashboard.py`):
  - Add `GET /api/benchmarks/history` endpoint that returns all previous benchmark runs with timestamps, suite name, tok/s, pass rate
  - Store history in a simple JSON file `benchmarks/history.json` (append-only, max 200 entries)
  - Each history entry: `{timestamp, suite, label, tasks: [{name, duration_s, tok_s, passed, total}]}`

- **Frontend** (`static/index.html`):
  - Add a "Benchmark History" section below the benchmark panel with a Chart.js canvas
  - Include `<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>` in head

- **Frontend** (`static/dashboard.js`):
  - Add `renderBenchmarkHistory()` function that fetches `/api/benchmarks/history` and renders a Chart.js line chart
  - X-axis: timestamp labels, Y-axis: tok/s
  - Multiple colored lines per suite label
  - Hover tooltip shows suite name, date, tok/s, pass rate

### Task 3 — Rollback Updater
Enhance `updater/updater.py` with rollback support:

- On update, backup current binary to `{binary_path}.bak.{timestamp}`
- Store backup list in `updater/backups.json` (max 5 entries)
- Add `POST /api/update/rollback` endpoint that swaps the most recent backup back
- Dashboard "Update" panel gets a "Rollback" button next to "Check Release"

### Task 4 — Auto-Discovery Polish
The `/api/config-schema` endpoint already auto-discovers options. Enhance it to:

- Detect when a config key's value differs from its default and mark it as "overridden"
- Return `{key: {desc, type, default, current, overridden: bool}}`
- In the UI, highlight overridden keys with a cyan accent (they have `schema-item.overridden` class)

### Task 5 — Dashboard Layout Polish
The dashboard-grid layout has been fixed (hero panel now spans 2 columns via `.panel-span-2`). Verify and polish:

- Ensure all 6 panels (hero, monitoring, config, model, benchmark, MCP) flow correctly in the 2-column grid
- At <1040px, switch to single-column (already has media query)
- Fix any visual gaps or misalignments

## Implementation Rules
- All Python files must pass `python3 -c "import ast; ast.parse(open(f).read())"` syntax check
- Commit after each task with `git commit -m "Phase 3: <task description>"`
- Do NOT delete existing files — only add or modify
- Dashboard.js must remain functional after changes (test with curl + browser)
- Do not modify bridge/config_manager.py or bridge/system_metrics.py unless absolutely needed

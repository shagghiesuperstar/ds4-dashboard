# DS4 Dashboard

A cyberpunk-themed web dashboard and MCP server for DS4 (DeepSeek V4 Flash inference engine). Features real-time telemetry, auto-discovered configuration, one-click benchmarks, and agentic control via MCP.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.9+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)
![MCP](https://img.shields.io/badge/MCP-1.0+-purple.svg)

---

## Features

### 🎨 Cyberpunk Interface
- Dark matrix-green aesthetic (`#00ff41` on `#0a0a0a`)
- Animated white-dwarf logo with gravitational lensing
- Glass-morphism panels with subtle glow effects
- Real-time memory gauge with color-coded accretion disk

### 📡 Live Telemetry
- `tok_s`, `prefill_tok_s` / `prefill_tokens_sec`, `prefill_latency_ms`
- `kv_cache` (budget_bytes / used_bytes)
- GPU/CPU utilization, die temperatures via `sysctl`/`powermetrics`
- Memory pressure (`pressure_level`: normal/warning/critical) and swap usage (`swap_bytes`)
- 2-second polling interval with smooth updates

### ⚙️ Auto-Discovering Configuration
- Parses DS4 binary `--help` output and merges with built-in schema
- Dynamically renders config editor for any discovered option
- Apply changes with one click; `launchctl kickstart` restarts DS4 automatically when needed

### 🧪 One-Click Benchmarks
- Suites: `quick_smoke`, `full_coding`, `agentic_smoke`, `agentic_full`, `agentic_endurance`
- Coding + multi-turn tool-calling scenarios
- Historical results chart with Chart.js
- Compare panel: runs two config profiles back-to-back with automatic restoration via `POST /api/benchmarks/compare`

### 🔌 MCP Server (Dual Transport)
- stdio transport for Claude Code, Codex, Cursor
- HTTP/SSE transport for agents and web clients
- Tools: `get_status`, `get_metrics`, `set_config`, `get_config`, `run_benchmark`, `restart_ds4`, `update_ds4`, `rollback_ds4`, `get_schema`
- Resources (read-only): `telemetry://stream`, `config://current`, `benchmarks://results`

### 🚀 Launchd Integration (macOS)
- Auto-start DS4 and dashboard at login
- Zero-downtime config reload via `launchctl kickstart`
- Structured logging to `/tmp`

---

## A/B Configuration Testing & Benchmarking

The dashboard supports systematic A/B testing of DS4 configurations through **config profiles** (YAML files in `config-profiles/`) and the `POST /api/benchmarks/compare` endpoint.

### How it actually works

1. **Config profiles** are named YAML files containing a `label`, optional `description`/`tags`/`hardware_hint`, and a dict of `overrides`. They are created/imported via the UI or `POST /api/config-profiles/import`.
2. **The Compare panel** (in `static/index.html`) lets you select two saved profiles as A and B plus a benchmark suite and iteration count.
3. **Behind the scenes**, `build_benchmark_comparison()` (dashboard.py:525) does the following:
   - Snapshots the current `config_overrides`
   - Applies profile A via `apply_benchmark_profile`, runs the suite (results tagged with `compare_label = "<label>:<suite_id>"`), records in `_last_results` ring buffer (20 entries) and `history.json`
   - Restores the snapshot
   - Applies profile B, runs the suite, records
   - Always restores the original overrides in a `finally` block; if any key required a restart, it calls `restart_ds4`
4. **The response** contains `config_a`, `config_b`, `run_a`, `run_b`, `diffs` (per-metric `metric_diff` objects with `a`, `b`, `delta`, `higher_is_better`, `improved`), and `task_diffs`.

### A/B workflow (manual, in the UI)

1. Save current overrides as a profile (e.g. `baseline`).
2. Change one or more discovered options in the Configuration panel and save as `candidate`.
3. Open the Compare panel, select `baseline` as A and `candidate` as B, choose a suite (e.g. `quick_smoke`), set iterations (1–10).
4. Click **Compare**. Both runs execute with automatic restore. Diffs appear in the panel.
5. The live DS4 config is restored to its pre-comparison state.

### A/B workflow (programmatic, via HTTP)

There is no MCP tool for comparison or profile management. Use the HTTP API:

```bash
# 1. Import a profile from YAML (repeat for each profile you want to test)
curl -X POST http://127.0.0.1:8765/api/config-profiles/import \
  -H "Content-Type: application/json" \
  -d @profile.yaml

# 2. Run a comparison. The overrides keys are whatever the auto-discovered
#    schema provides (use GET /api/config/schema to list them).
curl -X POST http://127.0.0.1:8765/api/benchmarks/compare \
  -H "Content-Type: application/json" \
  -d '{
    "suite": "quick_smoke",
    "iterations": 3,
    "config_a": {"label": "baseline", "overrides": {}},
    "config_b": {"label": "candidate", "overrides": {}}
  }'
```

The response includes `run_a`, `run_b`, `diffs` (per-metric `a`/`b`/`delta`/`higher_is_better`/`improved`), and `task_diffs`.

### Comparing apples-to-apples

- Use the same `suite` and `iterations` for every run in a sweep.
- Results are tagged with `compare_label` for grouping.
- `history.json` records: `timestamp`, `suite`, `suite_name`, `compare_label`, `tok_s` (avg), `pass_rate`, and grouped per-task `duration_s`/`tok_s`/`passed`/`total`.
- The full `config_overrides` for a run is stored only in the in-memory `_last_results` ring buffer (last 20 runs). It is **not** persisted to `history.json`.
- Original overrides are always restored after a comparison.

### Limitations (verified)

- **No config fingerprinting or commit hash.** `history.json` does not store the full override snapshot or DS4 binary version. Only `compare_label` and summary metrics are recorded.
- **No deterministic seed.** Temperature is fixed per suite, but task ordering and generation are not seeded.
- **No KV cache / memory pressure in compare diffs.** The `diffs` object covers only `tok_s_avg`, `latency_p50_seconds`, `latency_p95_seconds`, `pass_rate`, `duration_seconds`, and `output_tokens`. Use `telemetry://stream` or `GET /metrics` separately for memory analysis.
- **No "click history to reload config" feature.** The history chart is read-only. Reproducing a past run requires the original profile YAML.
- **MCP resources are read-only.** `telemetry://stream`, `config://current`, and `benchmarks://results` support only `resources/read`. No subscription mechanism is implemented.
- **Two different compare mechanisms exist:**
  - `POST /api/benchmarks/compare` → runs fresh A/B via `build_benchmark_comparison` (preferred for testing).
  - `GET /api/benchmarks/compare?baseline=...&target=...` → diffs two existing runs from the in-memory ring buffer via `BenchmarkRunner.compare()`.

---

## Quick Start

### Prerequisites
- macOS (tested on Apple Silicon)
- Python 3.9+
- DS4 binary at `$DS4_HOME/ds4-server`
- (Optional) launchd for auto-start

### Installation

```bash
git clone https://github.com/<your-org>/ds4-dashboard.git
cd ds4-dashboard

# Create virtualenv and install deps
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run the dashboard
python -m uvicorn dashboard:app --host 127.0.0.1 --port 8765
```

Open http://127.0.0.1:8765

### Launchd (Recommended)

The `install-launchd.sh` script renders the plist templates (substituting path placeholders with values detected on your machine) and bootstraps them under your user launchd domain. By default it installs both the engine and the dashboard.

```bash
# Install both (engine + dashboard)
bash scripts/install-launchd.sh

# Install just the dashboard
bash scripts/install-launchd.sh --component dashboard

# Install just the engine
bash scripts/install-launchd.sh --component engine
```

Path defaults can be overridden with `DS4_HOME`, `DS4_DASHBOARD_DIR`, `PYTHON_PATH`, or `DS4_BINARY` env vars. The script will refuse to bootstrap a service whose plist still contains un-rendered placeholders or whose Python cannot import `fastapi`+`uvicorn`.

Uninstall:

```bash
bash scripts/install-launchd.sh --uninstall
# or one component only:
bash scripts/install-launchd.sh --uninstall --component dashboard
```

### Running the tests

```bash
# Tests must run from the repo's venv (they import fastapi, uvicorn, etc.)
.venv/bin/python -m pytest              # pytest
.venv/bin/python -m unittest discover -s tests   # stdlib unittest
```

The tests import the dashboard module as a top-level name (`import dashboard`), so they need to be run with the venv's Python — using the system `python3` (which lacks `fastapi`/`uvicorn`) will fail at collection.

---

## Architecture

```
dashboard.py          FastAPI + MCP server (port 8765)
static/               Frontend (HTML + JS + CSS)
bridge/
  engine_client.py    DS4 telemetry client + KV/prefill parsing
  system_metrics.py   macOS GPU/CPU/temp/swap/pressure via sysctl/powermetrics
  config_manager.py   Auto-discover + read/write DS4 config + restart
benchmarks/           Coding + agentic benchmark suites + runner
mcp/                  MCP server (stdio + SSE) — 9 tools, 3 read-only resources
updater/              GitHub release downloader + verifier
```

---

## MCP Tools

| Tool            | Description                                      |
|-----------------|--------------------------------------------------|
| `get_status`    | DS4 uptime, model, port                          |
| `get_metrics`   | Live telemetry snapshot (tok_s, prefill, KV, etc.) |
| `set_config`    | Apply a config key=value                         |
| `get_config`    | Read current dashboard overrides                 |
| `run_benchmark` | Execute a named benchmark suite                  |
| `restart_ds4`   | Trigger launchd restart of DS4                   |
| `update_ds4`    | Download + verify + swap binary                  |
| `rollback_ds4`  | Roll back to previous binary                     |
| `get_schema`    | List all auto-discovered config options          |

---

## Configuration

The dashboard reads these environment variables (or uses sensible defaults):

| Variable            | Default          | Description                     |
|---------------------|------------------|---------------------------------|
| `DS4_HOME`          | `~/ds4`          | Directory containing ds4-server |
| `DS4_PRIMARY_PORT`  | `8001`           | DS4 inference port              |
| `DS4_TELEM_URL`     | `http://127.0.0.1:8001/health` | Telemetry endpoint (PR #374) |
| `DS4_LAUNCHD_LABEL` | `com.ds4.engine` | launchd service label          |

---

## Development

```bash
# Run tests (uses stdlib unittest)
make test

# Type check / lint
ruff check .
mypy .

# Frontend only (live reload)
python -m http.server 8080 -d static
```

---

## Contributing

1. Fork the repo
2. Create a feature branch (`git checkout -b feat/my-feature`)
3. Commit your changes
4. Push to the branch
5. Open a Pull Request

Please keep commits focused and include a clear description of the change.

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Acknowledgments

Built for the DS4 inference engine ecosystem. Designed to be a clean, professional, and agent-friendly control surface.

---

*Last updated: 2026-06-12*
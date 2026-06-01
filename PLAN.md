# DS4 Dashboard

## Vision
A cyberpunk-themed web dashboard for DS4 that feels like staring into a white dwarf star. Green-on-dark hacker aesthetic. Auto-discovers new config options from the DS4 binary. Built-in MCP server for agentic management. One-click coding benchmarks.

## Architecture

```
ds4-dashboard/
├── dashboard.py              ← FastAPI server (REST + MCP dual transport, port 8765)
├── static/                   ← Web GUI
│   ├── index.html            ← Main dashboard page
│   ├── dashboard.js          ← Live telemetry polling, chart rendering
│   └── style.css             ← Cyberpunk theme
├── bridge/                   ← Data collection layer
│   ├── engine_client.py      ← DS4 telemetry client (telem endpoint)
│   ├── system_metrics.py     ← macOS metrics (GPU/CPU/temps)
│   └── config_manager.py     ← Read/write DS4 config, auto-discover new options
├── benchmarks/               ← Benchmark suites
│   ├── coding.py             ← Coding/agentic LLM benchmarks
│   ├── runner.py             ← Benchmark runner (1-click from dashboard)
│   └── suites.py             ← Predefined benchmark suites
├── mcp/                      ← MCP server (stdio + SSE transport)
│   ├── server.py             ← MCP lifecycle + transport
│   ├── tools.py              ← Tools: status, config, benchmark, update, metrics
│   └── resources.py          ← Subscribable resources (telemetry stream)
├── updater/                  ← One-click GitHub release updater
│   └── updater.py            ← Download, verify hash, swap binary, rollback
└── tests/                    ← Test suite
    └── test_api.py
```

## Features

### 1. Cyberpunk Theme
- **White dwarf animated logo**: Pulsing core, gravitational lensing rings, accretion disk that rotates subtly
- **Color palette**: `#00ff41` (matrix green) on `#0a0a0a` (near-black) with `#00d4ff` (cyan) accents
- **Memory gauge**: Visual bar showing KV cache usage with accretion disk colors — green (safe) → yellow (caution) → red (critical)
- **Starfield background**: Subtle animated dots with gravitational lensing effect
- **Data panels**: Semi-transparent glass-morphism cards with green border glow

### 2. Auto-Discovering Config
- When new flags are added to DS4, the dashboard's `/api/config-schema` endpoint detects them
- New options appear in the config editor automatically — no manual schema updates
- `bridge/config_manager.py` parses DS4's `--help` output or telem schema to discover new options
- Config editor in the UI lets users set any discovered option and apply it

### 3. Live Monitoring
- **Tok/s**: Real-time tokens per second (from DS4 telem `/metrics`)
- **Prefill speed**: Prompt processing tokens/s
- **KV cache**: Location (path), current size, budget limit, fill %
- **GPU utilization**: % from macOS GPU metrics (sysctl/powermetrics)
- **CPU utilization**: % per core or aggregate
- **Temperature**: CPU/GPU die temps from macOS sensors
- **Memory pressure**: Total RAM, DS4 process RSS, available cushion, swap usage
- **All metrics update every 2 seconds** via dashboard.js polling

### 4. Memory Gauge Visualization
- Bar/dial showing total device memory usage
- DS4's portion highlighted separately
- Color transitions: green (<70%) → yellow (70-85%) → red (>85%)
- Animated accretion disk visual that responds to KV cache fill %
- Numerical labels: "XX GB / YY GB available", "ZZ% filled"

### 5. One-Click Benchmarks
- **Coding benchmarks**: HumanEval-style function completion, code generation, bug fix
- **Agentic benchmarks**: Multi-turn reasoning tasks, tool-calling scenarios
- **Predefined suites**: "Quick smoke test", "Full coding eval", "Agentic endurance"
- **1-click button**: Select suite → click "Run Benchmark" → results stream into dashboard
- **Results display**: Tok/s, latency p50/p95, pass rate, KV cache impact, cost estimate
- **Compare mode**: Run multiple configs and compare side-by-side

### 6. MCP Server
- Dual transport: stdio (for Claude Code / Codex / Cursor) + HTTP/SSE (for agents)
- **Tools**:
  - `get_status` → Current DS4 status, uptime, model, port
  - `get_metrics` → Live telemetry (tok/s, KV cache, GPU/CPU, temps)
  - `set_config` → Apply a config change (key=value)
  - `get_config` → Read current config
  - `run_benchmark` → Execute a benchmark suite, return results
  - `update_ds4` → Trigger one-click update from GitHub
  - `get_schema` → List all available config options (auto-discovered)
- **Resources**:
  - `telemetry://stream` → Subscribable SSE stream of live metrics
  - `config://current` → Current config snapshot
  - `benchmarks://results` → Last benchmark results

### 7. Updater (Optional)
- One-click update from GitHub releases
- Download release asset, verify SHA256, backup current binary, swap, restart
- Progress bar in dashboard, rollback on failure

## Implementation Plan

### Phase 1 — Core Dashboard + MCP
1. Enhance `dashboard.py` with MCP server, benchmark endpoints, updater skeleton
2. Enhance `static/style.css` with full cyberpunk theme (animations, memory gauge, glass cards)
3. Enhance `static/dashboard.js` with memory gauge, GPU/CPU/temp charts, benchmark UI
4. Enhance `static/index.html` with full layout (5 panels: status, config, monitoring, benchmarks, MCP)
5. Build `bridge/system_metrics.py` — macOS GPU/CPU/temp via sysctl, powermetrics, IOKit
6. Build `bridge/config_manager.py` — auto-discover new DS4 options
7. Build `benchmarks/` — coding + agentic benchmark suites
8. Build `mcp/` — MCP server with stdio + SSE transport
9. Build `updater/updater.py` — GitHub release checker

### Phase 2 — Polish
- Animated white dwarf SVG logo
- Benchmark compare mode
- Launchd integration (restart DS4 after config change)
- Docker/devcontainer support

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
- Tokens per second, prefill speed, KV cache usage
- GPU/CPU utilization, die temperatures
- Memory pressure and swap monitoring
- 2-second polling interval with smooth updates

### ⚙️ Auto-Discovering Configuration
- Parses DS4 binary help output and telemetry schema
- Dynamically renders config editor for any discovered option
- Apply changes with one click; launchd integration restarts DS4 automatically

### 🧪 One-Click Benchmarks
- Predefined suites: smoke test, full coding eval, agentic endurance
- Coding + multi-turn tool-calling scenarios
- Historical results chart with Chart.js
- Side-by-side compare mode

### 🔌 MCP Server (Dual Transport)
- stdio transport for Claude Code, Codex, Cursor
- HTTP/SSE transport for agents and web clients
- Tools: status, metrics, config, benchmark, update, schema
- Subscribable resources for live telemetry streams

### 🚀 Launchd Integration (macOS)
- Auto-start DS4 and dashboard at login
- Zero-downtime config reload via `launchctl kickstart`
- Structured logging to `/tmp`

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

```bash
# Edit the plists to point at your paths, then:
bash scripts/install-launchd.sh
```

Uninstall:

```bash
bash scripts/install-launchd.sh --uninstall
```

---

## Architecture

```
dashboard.py          FastAPI + MCP server (port 8765)
static/               Frontend (HTML + JS + CSS)
bridge/
  engine_client.py    DS4 telemetry client
  system_metrics.py   macOS GPU/CPU/temp via sysctl/powermetrics
  config_manager.py   Auto-discover + read/write DS4 config
benchmarks/           Coding + agentic benchmark suites
mcp/                  MCP server (stdio + SSE)
updater/              GitHub release downloader + verifier
```

---

## MCP Tools

| Tool            | Description                              |
|-----------------|------------------------------------------|
| `get_status`    | DS4 uptime, model, port                  |
| `get_metrics`   | Live telemetry snapshot                  |
| `set_config`    | Apply a config key=value                 |
| `get_config`    | Read current config                      |
| `run_benchmark` | Execute a named benchmark suite          |
| `update_ds4`    | Download + verify + swap binary          |
| `get_schema`    | List all auto-discovered config options  |

---

## Configuration

The dashboard reads these environment variables (or uses sensible defaults):

| Variable            | Default          | Description                     |
|---------------------|------------------|---------------------------------|
| `DS4_HOME`          | `~/ds4`          | Directory containing ds4-server |
| `DS4_PRIMARY_PORT`  | `8001`           | DS4 inference port              |
| `DS4_TELEM_URL`     | `http://127.0.0.1:8001/telem` | Telemetry endpoint     |
| `DS4_LAUNCHD_LABEL` | `com.ds4.engine` | launchd service label          |

---

## Development

```bash
# Run tests
pytest

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

*Last updated: 2026-06-01*
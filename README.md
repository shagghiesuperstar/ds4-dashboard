# DS4 Dwarfstar Dashboard — Agentic Control for Local Intelligence

> **Every DS4 user gets it. New config options appear magically. Your models tune themselves to your hardware.**

<p align="center">
  <img src="static/logo.svg" alt="DS4 Dwarfstar logo" width="140" />
</p>

---

## Thesis

**Local AI inference is the future, but it ships without a dashboard.**

You install DeepSeek V4 Flash. You run it. You get tokens. But you get nothing else. No visibility into what the engine is doing. No way to know if your config is optimal for your hardware. No way to benchmark across model variants. No way to programmatically tune, update, or manage the engine from your agent stack.

This is the **Dwarfstar Dashboard** — a self-serve, cyberpunk-themed web GUI, REST API, benchmark harness, and MCP server that transforms DS4 from a blind terminal process into a first-class citizen of your AI infrastructure. It gives you:

- **Visibility** — live metrics, KV cache fill, GPU/CPU/Memory pressure, model running averages
- **Control** — dynamic config editor that auto-discovers every DS4 option, one-click restart, model switching
- **Tuning** — benchmark suites that measure real-world agentic performance, not synthetic ML numbers, with A/B compare across config profiles
- **Agentic access** — an MCP server that lets Hermes agents, Codex, Claude Code, or any MCP client drive DS4 programmatically
- **Updates** — one-click GitHub release check, download, verify, swap, and rollback

---

## The Pain Point

### Running Blind

Every local LLM operator knows this feeling:

```
You: "Is the engine running?"
Terminal: silence.
You: "What's my token throughput?"
Terminal: silence.
You: "Is my KV cache about to OOM?"
Terminal: silence.
You: "Should I use the imatrix model or the Q4 variant?"
Terminal: silence.
```

DS4 is a masterpiece of inference engineering — Antirez has built something genuinely revolutionary in Metal. But it has no dashboard. No telemetry UI. No way to see what's happening unless you SSH in and grep logs.

This dashboard fixes that. Every metric is one click away. Every config option has a form field. Every benchmark result is charted. The engine finally speaks.

### Running Without a Compass

You have 12 GGUF files. Which one is right for your hardware? Your use case? Your memory budget?

Without benchmarks tied to your actual workload, you're guessing. The Q4 variant might give better quality but 20% slower generation. The imatrix variant might hallucinate less on structured tasks but cost more memory. Without a dashboard that runs real agentic benchmarks — tool call accuracy, multi-turn coherence, instruction following — you can't know.

This dashboard runs **coding** and **agentic** benchmark suites against YOUR engine, YOUR model, YOUR hardware. It scores them. It compares profiles side-by-side. It tracks history across DS4 versions. Now you have a compass.

### Running Without an API for Agents

Your agent stack (Hermes, Codex, Claude Code) can't talk to DS4. There's no MCP server. No tool surface. No resource endpoints. The engine is a black box that only accepts chat completions.

This dashboard adds a full MCP server over stdio, HTTP JSON-RPC, and SSE — 9 tools, 3 resources, zero extra ports needed. Your agents can check status, tweak config, run benchmarks, trigger updates, and restart the engine, all programmatically.

---

## The Opportunity — Agentic Tuning via MCP

### The Vision

The MCP server is not just a convenience feature. It's the **mechanism for a new kind of model tuning**.

Here's the insight: **benchmarking + MCP = automated hardware-specific calibration.**

Every user has different hardware: M4 Max 128GB, M5 Max 64GB, dual M3 Ultra, NVIDIA 4090, AMD MI300. Every user has a different use case: coding agent, chat, RAG pipeline, batch processing, tool-calling agent. Every DS4 variant (imatrix, Q4K, mixed Q2+Q4, MTP) performs differently on each combination.

The dashboard's MCP surface lets an **agentic tuning loop** exist:

1. Agent checks current status (`get_status`)
2. Agent reads available model variants (`get_schema` → model path field)
3. Agent runs a benchmark suite against the current config (`run_benchmark`)
4. Agent tweaks a config parameter (KV cache budget, context window, MTP draft count) (`set_config`)
5. Agent restarts the engine (`restart_ds4`)
6. Agent re-runs the benchmark and compares results
7. Agent converges on the optimal config for this hardware + workload
8. Agent saves the winning profile and reports back

**This is why we had to build this for the DS4 community.** Without the dashboard, this loop is manual — SSH, grep, guess, restart, repeat. With the dashboard, it's a 10-line MCP script that any Hermes agent can execute in seconds.

### Concrete Example

Here's what an agentic tuning session looks like with the Dwarfstar Dashboard MCP:

```python
# Agentic tuning loop — Hermes agent tunes DS4 for Shag's M5 Max 128GB
# Goal: maximize coding benchmark score while keeping memory cushion >30%

# Step 1: Check current state
status = ds4.get_status()
# → running, tok/s=24, kv_cache=32GB/51GB, memory_cushion=52%

# Step 2: Discover available config options
schema = ds4.get_schema()
# → ctx=131072, mtp_draft=2, kv_budget=51200, gpu_layers=80, ...

# Step 3: Run baseline coding benchmark
baseline = ds4.run_benchmark(suite="full_coding")
# → coding_score=72/100, tok/s=24.1, ttft=1.2s

# Step 4: Tune — increase MTP draft tokens for throughput
ds4.set_config({"mtp_draft": 4, "kv_disk_space_mb": 40960})
ds4.restart()

# Step 5: Run tuned benchmark
tuned = ds4.run_benchmark(suite="full_coding")
# → coding_score=78/100 (+6), tok/s=28.4 (+18%), ttft=0.9s (-25%)
# memory_cushion=48% (still >30% — safe)

# Step 6: Compare and save
ds4.compare(baseline, tuned)
# → "MTP draft=4 improves throughput 18%, reduces TTFT 25%, memory cushion OK.
#    Recommend: mtp_draft=4, kv_disk_space_mb=40960 for coding workloads."

# Step 7: Persist the winning config
ds4.set_config({"mtp_draft": 4, "kv_disk_space_mb": 40960})
ds4.restart()
# → DS4 now runs at tuned config. Benchmark history records the improvement.
```

Without the dashboard, this takes 15 minutes of SSH, grep, manual `kill -9`, manual benchmark timing with a stopwatch, and guesswork. With the dashboard, it takes 15 seconds and the agent does it unattended.

**This is the opportunity for Antirez and every DS4 user:** the dashboard makes DS4 not just a great engine, but a **self-tuning system** that adapts to its operator's hardware and workload. The MCP surface is the API for that adaptation loop. It's the difference between a static binary and an evolving intelligence.

---

## Dashboard Walkthrough — Every Visual, Data Point, and Control

### Top Status Bar

```
┌──────────────────────────────────────────────────────────────────┐
│  ⬡ DWARFSTAR DASHBOARD  v0.1.0  [🟢 LIVE]  ⚙️  ⟳ 2s           │
└──────────────────────────────────────────────────────────────────┘
```

| Element | Description |
|---|---|
| **⬡ Dwarfstar logo** | SVG white dwarf star — the dashboard's identity mark |
| **Version badge** | Dashboard version from `dashboard.py` `__version__` |
| **🟢 LIVE/🟡 BOOTING/🔴 OFFLINE dot** | Engine status — green when DS4 responds to `/v1/models`, amber during load, red when unreachable |
| **⚙️ Config indicator** | Flashes when overrides differ from defaults |
| **⟳ 2s** | Polling interval — the dashboard fetches `/api/status` every 2 seconds |

### Panel 1: Engine Core (Left Column)

```
┌─ ENGINE CORE ────────────────────────────────────────────────────┐
│  ● RUNNING          PID: 48212        Uptime: 4h 23m              │
│  Tok/s: 24.8        Prefill: 1.2s     Context: 131072             │
│  KV Cache: 32.1 GB / 51.2 GB  [████████████░░░░░░░]  63%          │
│  Model: DeepSeek-V4-Flash-IQ2XXS-... (86.7 GB)                    │
│  MTP Draft: 2       Metal Shaders: 19/19 loaded                   │
│  Running averages: tok/s 24.2 (n=47)  ttft 1.1s (n=47)           │
└───────────────────────────────────────────────────────────────────┘
```

| Data Point | Source | What It Tells You |
|---|---|---|
| **● RUNNING** | `GET /api/status` → `engine.running` | Process state — green dot means DS4 is serving |
| **PID** | `ps` / `engine_client.pid` | OS process ID for kill/trace |
| **Uptime** | `engine_client.uptime` | How long since last restart |
| **Tok/s** | DS4 telemetry `/telem` or `/metrics` | Current generation throughput — the speed you're actually getting |
| **Prefill** | DS4 telemetry | Time to first token for the last prompt — affects perceived latency |
| **Context** | `config.context_window` | How many tokens the model can see |
| **KV Cache bar** | Telemetry `kv_cache.used_mb` / `kv_cache.budget_mb` | Fill level of disk KV cache — near-full means you're bumping against the budget |
| **KV Cache %** | Calculated used/budget ratio | Color-coded: green <70%, amber 70-85%, red >85% |
| **Model name** | `config.model` or telemetry | Which GGUF is loaded, truncated to fit |
| **MTP Draft** | Config `mtp_draft` | Speculative decoding draft count — higher = faster but more memory |
| **Metal Shaders** | Telemetry or engine config | How many of the 19 Metal kernels are loaded — missing shaders = performance degradation |
| **Running averages** | `bridge/model_averages.py` | Smoothed tok/s and TTFT over the last N completions — more stable than instantaneous readings |

### Panel 2: System Monitoring (Middle Column)

```
┌─ SYSTEM ──────────────────────────────────────────────────────────┐
│  CPU: ████████░░░░  42%     GPU: ██████████░░░░  58%              │
│  CPU Temp: 68°C    GPU Temp: 72°C    (— unavailable w/o sudo)    │
│                                                                   │
│  ┌─ MEMORY CUSHION ──────────────────────────────────┐            │
│  │ [████████████████████████░░░░░░░░░░░░░░░░] 128 GB │            │
│  │  Used: 68 GB │ Free Cushion: 60 GB                │            │
│  │  DS4: ████████ 34 GB  │  System: ██████ 34 GB     │            │
│  │  CUSHION: 🟢 60 GB free (47%)                     │            │
│  └───────────────────────────────────────────────────┘            │
│                                                                   │
│  Swap: 1.2 GB    Wired: 18 GB    Active: 42 GB    Inactive: 8 GB │
└───────────────────────────────────────────────────────────────────┘
```

| Data Point | Source | What It Tells You |
|---|---|---|
| **CPU %** | `ps` / `top` aggregated | Total CPU utilization across all cores — DS4 is GPU-bound, so this is usually low |
| **GPU %** | `sysctl` or `powermetrics` | Metal GPU utilization — should be high during generation, low during idle |
| **CPU Temp** | `sysctl machdep.x86.thermal.temperature` or `powermetrics` | Thermal headroom — throttling starts at ~85°C+ |
| **GPU Temp** | `powermetrics` (requires sudo) | GPU junction temp — critical for sustained generation. Shows "—" if unavailable |
| **Memory Cushion bar** | `vm_stat` + custom calculation | **The crown jewel.** Total system memory breakdown showing used vs free, with DS4's RSS and system overhead separated |
| **Used GB** | `vm_stat active + wired + compressed` | How much RAM is actually in use |
| **Free Cushion** | `sysctl hw.memsize - used` | Headroom before swap pressure starts |
| **DS4 RSS** | `ps -o rss= <pid>` | DS4 process's resident set size — the engine's true memory footprint |
| **System overhead** | `used - DS4_RSS` | Everything else — kernel, browsers, other agents |
| **🟢🟡🔴 Cushion dot** | Color logic: green >30%, amber 15-30%, red <15% | Instant visual of memory safety — red means risk of OOM/swap death |
| **Swap** | `vm_stat` | How much has been paged to disk — should be near 0 on a tuned system |
| **Wired** | `vm_stat` | Memory pinned by kernel/hardware — high wired = lots of Metal allocations |
| **Active** | `vm_stat` | Memory actively in use by processes |
| **Inactive** | `vm_stat` | Available but not currently needed — good sign of headroom |

### Panel 3: Config Editor (Right Column)

```
┌─ CONFIG ──────────────────────────────────────────────────────────┐
│  [Dynamic schema — keys auto-discovered from DS4 --help + telemetry] │
│                                                                   │
│  ┌─ primary_port ──────────────────────────────────────────────┐  │
│  │  [8001]  (int)  Server listen port                            │  │
│  └──────────────────────────────────────────────────────────────┘  │
│  ┌─ context_window ────────────────────────────────────────────┐  │
│  │  [131072]  (int)  Context window size   ⚡overridden         │  │
│  └──────────────────────────────────────────────────────────────┘  │
│  ┌─ mtp_draft ─────────────────────────────────────────────────┐  │
│  │  [2]  (int)  MTP speculative draft tokens                    │  │
│  └──────────────────────────────────────────────────────────────┘  │
│  ┌─ kv_disk_space_mb ──────────────────────────────────────────┐  │
│  │  [51200]  (int)  KV cache budget in MB                       │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  [Apply] [Apply & Restart]  [Restart]  [Reset to Defaults]       │
└───────────────────────────────────────────────────────────────────┘
```

| Control | Description |
|---|---|
| **Schema-driven form** | Every config key is rendered from `GET /api/config-schema` — type maps to widget: `int` → number input, `string` → text input, `bool` → toggle, `enum` → dropdown |
| **Key name** | The actual DS4 config key — maps to CLI flag or config file option |
| **Current value input** | Editable — change the number/text and hit Apply |
| **Type tag** | `(int)`, `(string)`, `(bool)` — tells you what format the engine expects |
| **Description** | Human-readable explanation of what this setting does |
| **⚡overridden badge** | Appears when the dashboard's value differs from the DS4 engine's actual value — shows you have un-applied changes |
| **Apply button** | Writes the override to dashboard memory (doesn't restart) |
| **Apply & Restart** | Writes the override AND restarts DS4 — use for settings that need a reload (model, ctx, port) |
| **Restart button** | Restarts DS4 without changing config — useful after a crash |
| **Reset to Defaults** | Clears all dashboard overrides back to defaults |

### Panel 4: Models & GGUF Discovery (Below Config)

```
┌─ MODELS ──────────────────────────────────────────────────────────┐
│  Available GGUF files:  6 found  in  ~/ds4/gguf/                  │
│                                                                   │
│  ◉ ds4flash.gguf (symlink → DeepSeek-V4-Flash-IQ2XXS-...-imatrix) │
│  ○ DeepSeek-V4-Flash-Q4KExperts-OtherQ2K-...-imatrix.gguf  (91GB) │
│  ○ DeepSeek-V4-Flash-MTP-Q4K-Q8_0-F32.gguf                (3.8GB) │
│  ○ DeepSeek-V4-Flash-IQ2XXS-w2Q2K-...-chat-v2.gguf        (86GB)  │
│  ○ ...                                                             │
│                                                                   │
│  Running averages for current model:                               │
│  tok/s: 24.2  (n=47)  |  ttft: 1.1s  (n=47)  |  score: 74/100   │
│                                                                   │
│  [Switch Model]                                                   │
└───────────────────────────────────────────────────────────────────┘
```

| Data Point | Description |
|---|---|
| **Available GGUF count** | `bridge/model_discovery.py` scans `DS4_HOME/gguf/` for `*.gguf` files |
| **Model list** | Each GGUF file with size — the active symlink is highlighted |
| **◉ Active dot** | The currently loaded model (the `ds4flash.gguf` symlink target) |
| **Running averages** | `bridge/model_averages.py` — persistent tok/s and TTFT per model variant |
| **Switch Model button** | Opens a modal to select a new GGUF, updates the symlink, and restarts |

### Panel 5: Benchmark Suite (Below Models)

```
┌─ BENCHMARKS ──────────────────────────────────────────────────────┐
│  [Quick Smoke] [Coding Suite] [Agentic Suite] [A/B Compare]       │
│                                                                   │
│  Coding Score:  ████████████████░░░░░  82/100  🟢                 │
│  Agent Score:   ██████████████░░░░░░░  68/100  🟡                 │
│                                                                   │
│  Last run: 2026-05-29 14:32  |  Suite: full_coding                │
│  ──────────────────────────────────────────────────────           │
│  Code Gen:       45 tok/s   TTFT: 0.8s  ✅                        │
│  Code Review:    52 tok/s   TTFT: 1.2s  ✅                        │
│  Refactor:       41 tok/s   TTFT: 1.1s  ✅                        │
│  Agent Loop:     38 tok/s   TTFT: 2.1s  ⚠️ slow                  │
│  JSON Mode:      58 tok/s   TTFT: 0.6s  ✅                        │
│  Context Load:   240 tok/s  TTFT: 0.3s  ✅                        │
│                                                                   │
│  [History Chart] ───────────────────────────────────────           │
│  ╭╮╭╮╭╮╭╮╭╮╭╮╭╮╭╮╭╮╭╮╭╮╭╮╭╮╭╮╭╮╭╮╭╮╭╮╭╮╭╮                    │
│  ╰╯╰╯╰╯╰╯╰╯╰╯╰╯╰╯╰╯╰╯╰╯╰╯╰╯╰╯╰╯╰╯╰╯╰╯╰╯╰╯                    │
│  Score over last 19 runs  |  Best: 85  |  Avg: 74                 │
└───────────────────────────────────────────────────────────────────┘
```

| Control / Data Point | Description |
|---|---|
| **Quick Smoke button** | Runs the `quick_smoke` suite — 3 fast benchmarks (code gen, JSON mode, context load) ~30s total |
| **Coding Suite button** | Runs `full_coding` — 6 benchmarks measuring real dev workflow performance ~2min |
| **Agentic Suite button** | Runs `agentic_smoke` — tool call, instruction following, multi-turn, structured output ~3min |
| **A/B Compare button** | Opens the compare modal: runs two config profiles back to back, restores original, shows delta table |
| **Coding Score bar** | Normalized 0-100 aggregate across coding benchmarks — the single number that tells you "is DS4 fast today?" |
| **Agent Score bar** | Normalized 0-100 aggregate across agentic benchmarks — "is DS4 smart today?" |
| **Individual benchmark rows** | Per-benchmark tok/s, TTFT, and pass/fail/⚠️ status — shows which areas need tuning |
| **History Chart** | Chart.js line chart of benchmark scores over time — track improvements across DS4 engine updates, model swaps, and config changes |
| **Score stats** | Best, average, run count — trend indicators for the chart |

### Panel 6: Updater (Below Benchmarks)

```
┌─ UPDATER ──────────────────────────────────────────────────────────┐
│  Current: v0.4.2  │  Latest: v0.5.0  [Check for Update]           │
│                                                                   │
│  [████████████████░░░░░░░░░░]  43%  Downloading...                │
│  Verifying checksum... ✅                                          │
│  Swapping binary... ✅                                             │
│  Restarting DS4...                                                 │
│                                                                   │
│  🔄 Rollback to v0.4.2 (backup saved 2026-05-28)                  │
└───────────────────────────────────────────────────────────────────┘
```

| Control / Data Point | Description |
|---|---|
| **Current version** | Parsed from `~/.hermes/cron/output/antirez-version-scan/latest.md` or `DS4_HOME/version.txt` |
| **Latest version** | Fetched from `https://api.github.com/repos/antirez/ds4/releases/latest` |
| **Check for Update button** | Calls `GET /api/update/check` — fetches GitHub release data |
| **Download progress bar** | Streams download via chunked response — shows bytes received / total |
| **Verification check** | SHA256 comparison of downloaded binary vs GitHub release asset hash |
| **Swap status** | Backs up current binary to `DS4_HOME/rollback/`, swaps in new binary |
| **Restart indicator** | Calls `restart_ds4` via launchd or wrapper script |
| **Rollback button** | Restores the most recent backup — one-click safety net |

### Panel 7: MCP & Agent Access (Bottom Panel)

```
┌─ MCP & HERMES ────────────────────────────────────────────────────┐
│  MCP Server: 🟢 RUNNING  (stdio + HTTP + SSE)                     │
│  Tools: 9  |  Resources: 3  |  Active connections: 0              │
│                                                                   │
│  get_status        get_metrics     get_config      get_schema      │
│  set_config        restart_ds4     run_benchmark   update_ds4      │
│  rollback_ds4                                                     │
│                                                                   │
│  telemetry://stream  │  config://current  │  benchmarks://results  │
│                                                                   │
│  [Hermes Config Snippet] [Skill Docs]                             │
└───────────────────────────────────────────────────────────────────┘
```

| Control / Data Point | Description |
|---|---|
| **MCP status dot** | Green when the MCP stdio/HTTP/SSE handlers are registered |
| **Tool list** | All 9 MCP tools — clickable to show JSON-RPC signature |
| **Resource list** | All 3 MCP resources — clickable to show data shape |
| **Active connections** | Count of current MCP sessions |
| **Hermes Config Snippet button** | Shows the `config.yaml` entry needed to connect Hermes agents |
| **Skill Docs button** | Links to `optional-skills/ds4-manager/` |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Dwarfstar Dashboard                         │
│                                                                   │
│  FastAPI Server (port 8765)                                       │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ REST API                 │ MCP Server (stdio / HTTP / SSE) │  │
│  │ ┌───────────────────────┐│ ┌──────────────────────────────┐│  │
│  │ │ GET  /api/status      ││ │ get_status      (tool)       ││  │
│  │ │ GET  /api/metrics     ││ │ get_metrics     (tool)       ││  │
│  │ │ GET  /api/config      ││ │ get_config      (tool)       ││  │
│  │ │ GET  /api/config-schema││ │ get_schema      (tool)       ││  │
│  │ │ PATCH /api/config     ││ │ set_config      (tool)       ││  │
│  │ │ POST /api/config/apply││ │ restart_ds4     (tool)       ││  │
│  │ │ POST /api/restart     ││ │ run_benchmark   (tool)       ││  │
│  │ │ GET  /api/models      ││ │ update_ds4      (tool)       ││  │
│  │ │ POST /api/models/sw.. ││ │ rollback_ds4    (tool)       ││  │
│  │ │ GET  /api/benchmarks  ││ └──────────────────────────────┘│  │
│  │ │ POST /api/benchmarks/ ││ ┌──────────────────────────────┐│  │
│  │ │ GET  /api/update/check││ │ telemetry://stream (resource)││  │
│  │ │ POST /api/update      ││ │ config://current   (resource)││  │
│  │ │ POST /api/update/rollb││ │ benchmarks://results(resource)││  │
│  │ └───────────────────────┘│ └──────────────────────────────┘│  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  bridge/                  benchmarks/              mcp/           │
│  ┌────────────────────┐   ┌──────────────────┐   ┌────────────┐  │
│  │ engine_client.py   │   │ suites.py        │   │ server.py  │  │
│  │ config_manager.py  │   │ coding.py        │   │ tools.py   │  │
│  │ system_metrics.py  │   │ agent_suite.py   │   │ resources  │  │
│  │ model_discovery.py │   │ runner.py        │   └────────────┘  │
│  │ model_averages.py  │   │ history.json     │                    │
│  └────────────────────┘   └──────────────────┘                    │
│                                                                   │
│  static/                          updater/                        │
│  ┌────────────────────┐   ┌──────────────────────┐                │
│  │ index.html         │   │ updater.py            │               │
│  │ dashboard.js       │   │ backups.json          │               │
│  │ style.css          │   └──────────────────────┘                │
│  │ logo.svg           │                                           │
│  └────────────────────┘                                           │
│                                                                   │
│  ↑ human browser  ↑ Hermes/Codex/Claude Code  ↑ DS4 engine        │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
DS4 Engine (port 8001)
    │
    ├── /v1/models          →  engine_client.py  →  /api/status (running check)
    ├── /telem              →  engine_client.py  →  /api/status (tok/s, KV cache, shaders)
    ├── /metrics            →  engine_client.py  →  /api/metrics (prometheus-style)
    └── /v1/chat/completions →  benchmarks/       →  benchmark results
                                runner.py

macOS System
    │
    ├── vm_stat             →  system_metrics.py  →  /api/status (memory, swap, cushion)
    ├── ps                  →  system_metrics.py  →  /api/status (CPU, RSS)
    ├── powermetrics        →  system_metrics.py  →  /api/status (GPU, temps)
    └── sysctl              →  system_metrics.py  →  /api/status (hw info)

GitHub (antirez/ds4)
    │
    └── API releases        →  updater/updater.py  →  /api/update/check

Dashboard State
    │
    ├── config_manager.py   →  /api/config, /api/config-schema (in-memory overrides)
    ├── model_averages.py   →  /api/models (running tok/s, ttft per model)
    └── history.json        →  /api/benchmarks/history (persisted benchmark results)

Human Browser                Hermes/Codex/Claude Code Agent
    │                               │
    ├── index.html                  ├── mcp/tools.py (9 tools over stdio/HTTP/SSE)
    ├── dashboard.js                ├── mcp/resources.py (3 resources)
    └── style.css                   └── mcp/server.py (JSON-RPC dispatcher)
```

---

## Why We Had to Build This for the DS4 Community

DS4 is not just another inference engine. It's a **Metal-native masterpiece** — Antirez has written something that competes with llama.cpp on Apple Silicon using raw Metal performance. But it ships without a dashboard, without telemetry, without an agent interface, without a benchmark harness.

This means every DS4 user is flying blind. They don't know:

- Is my KV cache about to OOM?
- Is the MTP draft model helping or hurting?
- Which GGUF variant performs best for my hardware?
- Should I increase context window or keep it conservative?
- Is there a new DS4 release with bug fixes I need?

The Dwarfstar Dashboard solves all of this. It gives the community:

1. **Visibility** — stop guessing, start knowing
2. **Control** — every config option has a form, every action has a button
3. **Tuning** — benchmark your actual workload, not synthetic ML numbers
4. **Agentic access** — let your AI stack drive DS4 like a first-class citizen
5. **Updates** — one-click to stay current with Antirez's relentless improvements

**The PR to Antirez is ready.** One `--dashboard` flag, one telemetry endpoint, and every DS4 user gets the full Dwarfstar experience. The dashboard code is designed to merge cleanly into DS4's telem server — no extra ports, no extra dependencies, no breaking changes.

---

## Quick Start

```bash
git clone https://github.com/shagghiesuperstar/ds4-dashboard.git
cd ds4-dashboard
./install.sh
.venv/bin/python dashboard.py --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765` — the dashboard assumes DS4 is running on `127.0.0.1:8001`. If DS4 is offline, the UI still loads and reports the engine as offline.

### Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `DS4_HOME` | `~/ds4` | Root directory for DS4 engine, GGUF models, Metal shaders |
| `DS4_BINARY` | `~/ds4/ds4-server` | Path to the DS4 engine binary |
| `DS4_MODEL` | `~/ds4/ds4flash.gguf` | Path to the active model GGUF (or symlink) |
| `DS4_MTP` | `~/ds4/gguf/DeepSeek-V4-Flash-MTP-Q4K-Q8_0-F32.gguf` | MTP speculative model path |
| `DS4_METAL_DIR` | `~/ds4/metal` | Directory containing Metal shader `.metal` files |
| `DS4_KV_CACHE` | `/tmp/ds4-kv` | Disk KV cache directory |
| `DS4_PRIMARY_PORT` | `8001` | DS4 engine port |
| `DS4_TELEM_URL` | `http://127.0.0.1:8001/telem` | DS4 telemetry endpoint |
| `DS4_METRICS_URL` | `http://127.0.0.1:8001/metrics` | DS4 metrics endpoint |
| `DS4_COMPLETION_URL` | `http://127.0.0.1:8001/v1/chat/completions` | DS4 chat completions endpoint |
| `DS4_CONTEXT_WINDOW` | `131072` | Default context window size |
| `DS4_KV_CACHE_BUDGET_MIB` | `51200` | KV cache budget in MiB |
| `DS4_GITHUB_REPO` | `antirez/ds4` | GitHub repo for update checks |

---

## MCP Integration — Agentic DS4 Control

### For Hermes Agents

Add to `~/.hermes/config.yaml`:

```yaml
mcp:
  servers:
    ds4:
      transport: stdio
      command: /path/to/ds4-dashboard/.venv/bin/python
      args:
        - /path/to/ds4-dashboard/dashboard.py
        - --mcp-stdio
```

### MCP Tools

| Tool | Input | Output | Purpose |
|---|---|---|---|
| `get_status` | `{}` | Engine state, tok/s, KV cache, uptime, model, running averages | Quick health check |
| `get_metrics` | `{}` | CPU/GPU/temps/memory/swap/wired/active | System resource check |
| `get_config` | `{}` | Full current config snapshot | Read all settings |
| `get_schema` | `{}` | Schema with types, defaults, descriptions, overrides | Discover available options |
| `set_config` | `{"key":"...","value":...}` | Apply result + restart flag | Change a single setting |
| `restart_ds4` | `{}` | Restart status | Restart the engine |
| `run_benchmark` | `{"suite_id":"...","iterations":1}` | Per-task results + aggregate scores | Benchmark current config |
| `update_ds4` | `{"asset_url":"...","asset_hash":"..."}` | Download/verify/swap/restart status | One-click update |
| `rollback_ds4` | `{}` | Rollback status | Revert to last backup |

### MCP Resources

| Resource | Data | Use Case |
|---|---|---|
| `telemetry://stream` | Live tok/s, KV cache, shader count | Real-time monitoring |
| `config://current` | Current config snapshot | Read-only config access |
| `benchmarks://results` | Latest benchmark results | Programmatic result analysis |

### For Codex, Claude Code, or Any MCP Client

Connect via HTTP JSON-RPC:

```bash
curl -s http://127.0.0.1:8765/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"get_status","params":{},"id":1}'
```

Or via SSE:

```bash
curl -s http://127.0.0.1:8765/mcp/sse
```

---

## launchd Integration

```bash
# Install dashboard-only as a LaunchAgent
./install.sh --launchd-dashboard

# Install both dashboard + DS4 engine as LaunchAgents
./install.sh --launchd-all

# Unload both
./install.sh --uninstall-launchd
```

| Label | Purpose | Plist |
|---|---|---|
| `com.dwarfstar.ds4-dashboard` | Runs FastAPI dashboard on `127.0.0.1:8765` | `scripts/ds4-dashboard-launchd.plist` |
| `com.dwarfstar.ds4` | Runs DS4 engine on port `8001` | `scripts/ds4-launchd.plist` |

Logs:

```bash
tail -f /tmp/ds4-dashboard-stdout.log
tail -f /tmp/ds4-dashboard-stderr.log
tail -f /tmp/ds4-stdout.log
tail -f /tmp/ds4-stderr.log
```

---

## Hermes Skill — ds4-manager

The Hermes skill for agentic DS4 management lives in `optional-skills/ds4-manager/`. Copy this directory into the Hermes agent repo under `optional-skills/` to give any Hermes agent instant DS4 control:

```bash
cp -r optional-skills/ds4-manager/ ~/.hermes/skills/
```

Then any Hermes agent can load the skill and call the MCP tools directly.

---

## Development

```bash
./install.sh
.venv/bin/python -m pip install -r requirements-dev.txt
PYTHONPYCACHEPREFIX=/private/tmp/ds4-dashboard-pycache \
  .venv/bin/python -m unittest discover -s tests
.venv/bin/uvicorn dashboard:app --host 127.0.0.1 --port 8765 --reload
```

Docker is available for dashboard-only development:

```bash
docker compose up --build
```

---

## Notes

- Temperature metrics are nullable — `powermetrics` usually requires sudo on macOS
- If DS4 lacks `/telem` or `/metrics` endpoints, the dashboard suppresses noisy failures and shows reachable process/config data
- Benchmark history is capped at 200 entries
- The updater stores up to five backups in `updater/backups.json`
- The dashboard does NOT modify your DS4 config.yaml — it maintains its own in-memory override layer. Config is applied via the engine's own API or restart

---
name: ds4-manager
description: |
  Manage Dwarfstar DS4 engine via MCP — status, config, benchmarks, updates.
  Requires the DS4 Dashboard MCP server running locally.
trigger: When user asks about DS4 status, config, update, or benchmarks.
tags: [ds4, dwarfstar, inference, deepseek]
---

# DS4 Manager

This skill connects to the DS4 Dashboard's MCP server, giving the agent
direct programmatic access to the Dwarfstar DeepSeek V4 Flash engine.

## Prerequisites

- DS4 Dashboard running: `dashboard.py` (see shagghiesuperstar/ds4-dashboard)
- MCP server configured in `~/.hermes/config.yaml`:
  ```yaml
  mcp:
    servers:
      ds4:
        transport: stdio
        command: /path/to/dashboard.py
        args: ["--mcp-stdio"]
  ```

## Available Tools

| Tool | What it does |
|------|-------------|
| `ds4_status` | Check if DS4 is running, tok/s, KV cache, uptime |
| `ds4_get_config` | Read full config |
| `ds4_set_config` | Apply new config (optional restart) |
| `ds4_get_config_schema` | Discover all available config options |
| `ds4_run_benchmark` | Run coding or agentic benchmark suite |
| `ds4_check_update` | Check for new GitHub release |
| `ds4_trigger_update` | One-click update + restart |
| `ds4_get_metrics` | GPU/CPU/util/temp/memory |

## Common Use Cases

### "Is DS4 running?"
→ Call `ds4_status`. If not running, suggest starting it.

### "Update DS4 to the latest"
→ Call `ds4_check_update`. If available, call `ds4_trigger_update`.

### "Tune DS4 for my workload"
→ Call `ds4_get_config_schema` to see options, then `ds4_set_config`.

### "Benchmark DS4"
→ Call `ds4_run_benchmark` with suite="coding" or suite="agent".

### "Why is my MBP slowing down?"
→ Call `ds4_get_metrics`. Check memory pressure and GPU temp.
   If memory cushion < 20%, suggest reducing ctx or offloading more GPU layers.

## Quick Install

1. Start the dashboard: `python3 dashboard.py --port 8765`
2. Configure Hermes MCP (see prerequisites above)
3. Load this skill in your Hermes agent

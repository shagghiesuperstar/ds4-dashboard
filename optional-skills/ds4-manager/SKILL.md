---
name: ds4-manager
description: Manage a local DS4 Dwarfstar Dashboard through MCP for status, metrics, config, benchmarks, updates, rollback, and restarts.
trigger: Use when the user asks about DS4, Dwarfstar, DeepSeek V4 Flash, local inference health, DS4 config, DS4 benchmarks, DS4 updates, or MCP control of the dashboard.
tags: [ds4, dwarfstar, deepseek, inference, mcp, benchmarks]
---

# DS4 Manager

Use the DS4 Dwarfstar Dashboard MCP server as the source of truth for local
DeepSeek V4 Flash engine state. Prefer MCP tools over shell commands unless the
user explicitly asks for direct process inspection.

## MCP Connection

Hermes should connect to the dashboard over stdio:

```yaml
mcp:
  servers:
    ds4:
      transport: stdio
      command: /Users/m4mbp/ds4-dashboard/.venv/bin/python
      args:
        - /Users/m4mbp/ds4-dashboard/dashboard.py
        - --mcp-stdio
```

The same dashboard also exposes HTTP JSON-RPC at `POST http://127.0.0.1:8765/mcp`
and an SSE telemetry stream at `GET http://127.0.0.1:8765/mcp/sse`.

## Available Tools

| Tool | Use it for |
| --- | --- |
| `get_status` | Current DS4 running state, model, port, uptime, KV cache, and dashboard config. |
| `get_metrics` | Live telemetry plus CPU, GPU, temperature, memory, and KV disk pressure. |
| `get_config` | Current effective dashboard config snapshot. |
| `get_schema` | Discovered config keys with type, default, current value, and override status. |
| `set_config` | Set one dashboard config override by key/value. |
| `restart_ds4` | Restart DS4 through launchd or the dashboard restart wrapper. |
| `run_benchmark` | Run `quick_smoke`, `full_coding`, `agentic_smoke`, or `agentic_endurance`. |
| `update_ds4` | Check for or apply a DS4 binary update from GitHub releases. |
| `rollback_ds4` | Restore the most recent updater backup. |

## Operating Rules

1. For any health question, call `get_status` first. Call `get_metrics` when the
   user mentions speed, thermals, memory, GPU/CPU use, KV cache, or system load.
2. Before changing config, call `get_schema` and verify the key, type, current
   value, and whether a restart is required. Explain the change before calling
   `set_config` unless the user already gave a specific key/value instruction.
3. After a restart-affecting config change, call `restart_ds4`, wait briefly,
   then call `get_status` again. Recommend `quick_smoke` when the user wants
   confirmation that the engine still answers.
4. For benchmarks, default to `quick_smoke`. Use `agentic_smoke` for tool-use or
   agent behavior questions, and `full_coding` only when the user asks for a
   deeper coding evaluation.
5. For updates, call `update_ds4` with `apply=false` first. Only call
   `update_ds4` with `apply=true` after the user confirms the target release or
   asset. If the updated binary fails, use `rollback_ds4`.
6. Do not invent DS4 flags. If a requested option is missing from `get_schema`,
   say it is not currently discovered by the dashboard.

## Response Pattern

Keep responses operational:

- State the observed DS4 state and the one or two metrics that matter.
- Say what action was taken, including config keys or benchmark suite IDs.
- For failures, include the exact tool error and the next safe recovery step.

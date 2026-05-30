# DS4 Dashboard MCP Reference

The dashboard exposes MCP over stdio, HTTP JSON-RPC, and an HTTP SSE telemetry
stream. Tool names are intentionally short because the MCP server is already
scoped as `ds4`.

## Stdio Transport

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

## HTTP Transport

- Manifest: `GET http://127.0.0.1:8765/api/mcp/manifest`
- JSON-RPC: `POST http://127.0.0.1:8765/mcp`
- SSE telemetry: `GET http://127.0.0.1:8765/mcp/sse`

Example JSON-RPC tool call:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "get_status",
    "arguments": {}
  }
}
```

## Tools

### `get_status`

Input: `{}`

Output: DS4 running state, port, uptime, model/config snapshot, telemetry, KV
cache status, system metrics, and model running averages.

### `get_metrics`

Input: `{}`

Output: A lighter live telemetry payload with state, KV cache, CPU, GPU,
temperature, and memory metrics.

### `get_config`

Input: `{}`

Output: Current effective dashboard config.

### `get_schema`

Input: `{}`

Output: Discovered config options with `type`, `default`, `current`, `desc`,
`source`, and `overridden` where available.

### `set_config`

Input:

```json
{ "key": "context_window", "value": 131072 }
```

Output: The normalized update result and full effective config. If
`restart_needed` is true, call `restart_ds4` after user confirmation.

### `restart_ds4`

Input: `{}`

Output: launchd or restart-wrapper result with exit code, stdout, stderr, and
method.

### `run_benchmark`

Input:

```json
{ "suite_id": "quick_smoke", "iterations": 1, "compare_label": "baseline" }
```

Suites: `quick_smoke`, `full_coding`, `agentic_smoke`, `agentic_endurance`.

Output: Aggregate pass rate, latency percentiles, tok/s average, output token
count, and per-task scoring.

### `update_ds4`

Input:

```json
{ "apply": false }
```

Use `apply=false` to check releases. Use `apply=true` only after confirmation
and, when needed, with `asset_url` and `sha256`.

### `rollback_ds4`

Input: `{}`

Output: Most recent updater backup restore result.

## Resources

### `telemetry://stream`

Current telemetry snapshot. The HTTP SSE endpoint emits this shape every two
seconds.

### `config://current`

Current effective dashboard config snapshot.

### `benchmarks://results`

Most recent in-memory benchmark results.

# DS4 Dashboard MCP Endpoints

The dashboard exposes a JSON-RPC MCP server with 8 tools and 1 subscribable resource.

## Tools

### ds4_status
**Input:** none
**Output:** Full status payload (running, tok/s, KV cache, GPU/CPU/temp, uptime)

### ds4_get_config
**Input:** none
**Output:** Current DS4 config as JSON

### ds4_set_config
**Input:** `{ key: string, value: any, restart: boolean }`
**Output:** `{ ok: boolean, config: {...} }`
**Note:** If `restart=true` and the key requires a DS4 restart, it triggers launchctl kickstart.

### ds4_get_config_schema
**Input:** `{ refresh?: boolean }`
**Output:** All available config options with types, defaults, descriptions

### ds4_run_benchmark
**Input:** `{ suite_id: string, iterations?: number, compare_label?: string }`
**Output:** Benchmark results with per-task scores and aggregate metrics

### ds4_check_update
**Input:** none
**Output:** `{ current: string, latest: string, changelog: string, update_available: boolean }`

### ds4_trigger_update
**Input:** `{ apply?: boolean, asset_url?: string, sha256?: string }`
**Output:** Update result with progress

### ds4_get_metrics
**Input:** none
**Output:** Live telemetry snapshot (GPU/CPU/util/temp/memory)

## Resources

### telemetry://metrics
Subscribable SSE resource. Pushes a new metrics payload every 2s.
Subscribe via `resources/subscribe` with URI `telemetry://metrics`.

## Transport

- **JSON-RPC:** POST `/mcp` with `{ jsonrpc: "2.0", method: "...", params: {...}, id: 1 }`
- **SSE:** GET `/mcp/sse` for server-sent events
- **Manifest:** GET `/api/mcp/manifest` lists all tools + resources

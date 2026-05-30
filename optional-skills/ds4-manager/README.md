# ds4-manager

Hermes skill for operating a local DS4 Dwarfstar Dashboard over MCP.

## Install

Copy this directory into the Hermes optional skills directory:

```bash
cp -R optional-skills/ds4-manager /path/to/hermes-agent/optional-skills/
```

Then add the dashboard MCP server to `~/.hermes/config.yaml`:

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

Start the dashboard once with `./install.sh` and either run it manually or load
the LaunchAgent:

```bash
.venv/bin/python dashboard.py --host 127.0.0.1 --port 8765
./install.sh --launchd-dashboard
```

## Tools

The skill expects the dashboard MCP server to expose:

`get_status`, `get_metrics`, `get_config`, `get_schema`, `set_config`,
`restart_ds4`, `run_benchmark`, `update_ds4`, and `rollback_ds4`.

See [references/mcp-endpoints.md](references/mcp-endpoints.md) for transport and
payload details.

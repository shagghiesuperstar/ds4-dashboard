# ds4-manager — Hermes Skill for DS4 Dashboard

Manage your Dwarfstar DeepSeek V4 Flash engine directly from any Hermes agent.
Provides 8 MCP tools for status, config, benchmarks, and updates.

## Installation

1. **Start the DS4 Dashboard:**
   ```bash
   python3 dashboard.py --port 8765
   ```

2. **Add MCP server to Hermes config** (`~/.hermes/config.yaml`):
   ```yaml
   mcp:
     servers:
       ds4:
         transport: stdio
         command: /path/to/dashboard.py
         args: ["--mcp-stdio"]
   ```

3. **Load the skill** in your Hermes agent.

## Requirements

- Python 3.9+
- FastAPI + uvicorn (see requirements.txt)
- DS4 engine running locally (port 8001 by default)

## License

MIT — part of the Dwarfstar project by shagghiesuperstar.

# DS4 Dwarfstar Dashboard

Local FastAPI dashboard for the DS4 inference engine running on port `8001`.

## Run

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/uvicorn dashboard:app --host 127.0.0.1 --port 8765 --reload
```

Then open `http://127.0.0.1:8765`.

## Test

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
PYTHONPYCACHEPREFIX=/private/tmp/ds4-dashboard-pycache .venv/bin/python -m unittest discover -s tests
```

## Defaults

The dashboard is preconfigured for:

- DS4 binary: `~/ds4/ds4-server`
- Telemetry: `http://127.0.0.1:8001/telem`
- Model: `~/ds4/ds4flash.gguf`
- MTP: `~/ds4/gguf/DeepSeek-V4-Flash-MTP-Q4K-Q8_0-F32.gguf`
- KV disk cache: `/tmp/ds4-kv`
- KV budget: `51200` MiB
- Context window: `131072`

Override with `DS4_HOME`, `DS4_BINARY`, `DS4_MODEL`, `DS4_MTP`, `DS4_METAL_DIR`, `DS4_KV_CACHE`, `DS4_PRIMARY_PORT`, `DS4_TELEM_URL`, `DS4_CONTEXT_WINDOW`, or `DS4_KV_CACHE_BUDGET_MIB`.

System metrics use `vm_stat`, `sysctl`, and `top`. If `sysctl hw.memsize` is denied, memory totals fall back to a `vm_stat` estimate. Temperature metrics are left null because `powermetrics` generally requires sudo.

"""pytest discovery config for ds4-dashboard.

The dashboard's Python modules live at the repo root (dashboard.py,
engine_client.py, etc.) and tests import them as top-level names. We add
the repo root to sys.path so this works regardless of the caller's
working directory.

If the active interpreter can't import the dashboard's runtime
dependencies (e.g. a CI runner that resolves 'python3' to the system
interpreter without fastapi/uvicorn installed), pytest will still fail
to collect the tests with the same ModuleNotFoundError the user would
hit by running 'python3 dashboard.py' directly. The right fix is to
activate the repo's venv first -- see README.md "Running the tests".
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

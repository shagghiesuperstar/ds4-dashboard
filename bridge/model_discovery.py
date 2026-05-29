"""
Model discovery: scan known GGUF directories for available models.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, List


def discover_models(*, model_paths: List[Path]) -> List[Dict[str, Any]]:
    """Scan a list of directories/files for GGUF model candidates.

    Returns a sorted list of model entries with path, filename, size, and type.
    """
    discovered: List[Dict[str, Any]] = []
    seen = set()

    for path in model_paths:
        if not path.exists():
            continue
        if path.is_file() and path.suffix in (".gguf", ".ggufv2", ".ggufv3"):
            if str(path) not in seen:
                seen.add(str(path))
                discovered.append(_entry(path))
        elif path.is_dir():
            for entry in sorted(path.iterdir()):
                if entry.is_file() and entry.suffix in (".gguf", ".ggufv2", ".ggufv3"):
                    if str(entry) not in seen:
                        seen.add(str(entry))
                        discovered.append(_entry(entry))

    return discovered


def _entry(path: Path) -> Dict[str, Any]:
    size_bytes = path.stat().st_size if path.is_file() else 0
    return {
        "path": str(path),
        "filename": path.name,
        "size_bytes": size_bytes,
        "size_gb": round(size_bytes / (1024**3), 2),
        "parent_dir": str(path.parent),
    }

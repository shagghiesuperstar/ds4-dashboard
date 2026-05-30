"""
Model discovery: scan known GGUF directories for available models.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, Any, List


HF_API_BASE = "https://huggingface.co/api/models"
HF_MODEL_BASE = "https://huggingface.co"
DESCRIPTION_CACHE_TTL_SECONDS = 6 * 60 * 60

_DESCRIPTION_CACHE: Dict[str, tuple[float, str]] = {}


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
    data = {
        "path": str(path),
        "filename": path.name,
        "size_bytes": size_bytes,
        "size_gb": round(size_bytes / (1024**3), 2),
        "parent_dir": str(path.parent),
    }
    repo = infer_huggingface_repo(path)
    if not repo and path.is_symlink():
        try:
            repo = infer_huggingface_repo(path.resolve())
        except OSError:
            repo = None
    if repo:
        data["repo"] = repo
    return data


def infer_huggingface_repo(model_path: Path | str) -> str | None:
    """Best-effort mapping from a local model path to a Hugging Face repo id."""
    path = Path(model_path)

    # Hugging Face cache paths look like models--org--repo/snapshots/<sha>/file.
    for part in path.parts:
        if part.startswith("models--"):
            pieces = part.split("--")
            if len(pieces) >= 3 and pieces[1] and pieces[2]:
                return f"{pieces[1]}/{pieces[2]}"

    raw = str(model_path)
    match = re.search(r"(?:huggingface\.co|hf\.co)[/:]([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", raw)
    if match:
        return match.group(1)

    filename = path.name.lower()
    if "deepseek-v4-flash" in filename:
        return "antirez/deepseek-v4-gguf"

    return None


def fetch_model_card_description(repo: str, *, timeout_seconds: float = 2.5) -> str:
    """Fetch a short model-card description from Hugging Face."""
    repo = repo.strip()
    if not repo:
        return ""

    cached = _DESCRIPTION_CACHE.get(repo)
    now = time.monotonic()
    if cached and now - cached[0] < DESCRIPTION_CACHE_TTL_SECONDS:
        return cached[1]

    description = ""
    payload = _fetch_hf_model_payload(repo, timeout_seconds=timeout_seconds)
    if payload:
        description = _extract_payload_description(payload)
    if not description:
        description = _fetch_readme_description(repo, timeout_seconds=timeout_seconds)
    if not description and payload:
        description = _extract_payload_summary(payload)

    _DESCRIPTION_CACHE[repo] = (now, description)
    return description


def _fetch_hf_model_payload(repo: str, *, timeout_seconds: float) -> Dict[str, Any]:
    repo_path = urllib.parse.quote(repo, safe="/")
    request = urllib.request.Request(
        f"{HF_API_BASE}/{repo_path}",
        headers={"Accept": "application/json", "User-Agent": "ds4-dashboard/0.1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return {}

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _extract_payload_description(payload: Dict[str, Any]) -> str:
    for source in (payload, payload.get("cardData")):
        if not isinstance(source, dict):
            continue
        for key in ("description", "summary", "model_description"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return _clean_description(value)
    return ""


def _extract_payload_summary(payload: Dict[str, Any]) -> str:
    card_data = payload.get("cardData") if isinstance(payload.get("cardData"), dict) else {}
    parts = []
    base_model = card_data.get("base_model")
    if isinstance(base_model, str) and base_model:
        parts.append(f"Quantized from {base_model}")
    pipeline = payload.get("pipeline_tag") or card_data.get("pipeline_tag")
    if isinstance(pipeline, str) and pipeline:
        parts.append(pipeline.replace("-", " "))
    tags = [tag for tag in payload.get("tags", []) if isinstance(tag, str)]
    useful_tags = [
        tag
        for tag in tags
        if not tag.startswith(("license:", "base_model:", "region:")) and tag not in {"en", "text-generation"}
    ][:5]
    if useful_tags:
        parts.append(", ".join(useful_tags))
    return _clean_description("; ".join(parts))


def _fetch_readme_description(repo: str, *, timeout_seconds: float) -> str:
    repo_path = urllib.parse.quote(repo, safe="/")
    request = urllib.request.Request(
        f"{HF_MODEL_BASE}/{repo_path}/raw/main/README.md",
        headers={"Accept": "text/markdown,text/plain", "User-Agent": "ds4-dashboard/0.1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return ""
    return _extract_readme_description(body)


def _extract_readme_description(markdown: str) -> str:
    text = re.sub(r"\A---\s*\n.*?\n---\s*\n", "", markdown, flags=re.S)
    paragraphs: list[str] = []
    current: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        if line.startswith(("#", "|", "!", "<", "```")):
            continue
        if line.startswith(("-", "*", "+")):
            continue
        current.append(line)
        if len(" ".join(current)) >= 180:
            break
    if current:
        paragraphs.append(" ".join(current))
    return _clean_description(paragraphs[0] if paragraphs else "")


def _clean_description(value: str, *, max_chars: int = 240) -> str:
    cleaned = re.sub(r"`([^`]+)`", r"\1", value)
    cleaned = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"[*_>#]", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:\t\r\n")
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 1].rsplit(" ", 1)[0].rstrip(".,;:") + "..."

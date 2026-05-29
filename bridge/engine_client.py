from __future__ import annotations

import json
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class EngineClientConfig:
    host: str
    port: int
    telem_url: str
    binary_path: Path
    request_timeout_seconds: float = 0.75


class DS4EngineClient:
    def __init__(self, config: EngineClientConfig) -> None:
        self.config = config

    def get_status(self) -> Dict[str, Any]:
        checked_at = time.time()
        port_open = self._is_port_open()
        pid = self._pid_for_port() if port_open else None
        telemetry, telemetry_error = self._fetch_telem() if port_open else (None, None)

        running = port_open
        state = "running" if running else "stopped"
        message = "DS4 port is accepting connections."
        if not running:
            message = f"DS4 is not accepting connections on port {self.config.port}."
        elif telemetry_error:
            message = f"DS4 port is open; telemetry is idle or unavailable: {telemetry_error}"
        elif telemetry:
            message = "DS4 telemetry online."

        return {
            "engine": "ds4",
            "state": state,
            "running": running,
            "pid": pid,
            "uptime_seconds": self._uptime_seconds(pid) if pid else None,
            "port": self.config.port,
            "telem_url": self.config.telem_url,
            "checked_at": checked_at,
            "message": message,
            "telemetry": self._normalize_telemetry(telemetry or {}),
            "telemetry_raw": telemetry,
            "telemetry_error": telemetry_error,
            "binary_exists": self.config.binary_path.exists(),
            "binary": str(self.config.binary_path),
        }

    def _is_port_open(self) -> bool:
        try:
            with socket.create_connection(
                (self.config.host, self.config.port),
                timeout=self.config.request_timeout_seconds,
            ):
                return True
        except OSError:
            return False

    def _fetch_telem(self) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
        request = urllib.request.Request(self.config.telem_url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.config.request_timeout_seconds) as response:
                body = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            return None, f"HTTP {exc.code}"
        except urllib.error.URLError as exc:
            return None, str(exc.reason)
        except TimeoutError:
            return None, "request timed out"
        except OSError as exc:
            return None, str(exc)

        if not body.strip():
            return {}, None

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            return {"raw": body[:2000]}, None

        if isinstance(parsed, dict):
            return parsed, None
        return {"value": parsed}, None

    def _pid_for_port(self) -> Optional[int]:
        command = ["lsof", "-nP", f"-iTCP:{self.config.port}", "-sTCP:LISTEN", "-t"]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=1.0, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return None

        for line in result.stdout.splitlines():
            line = line.strip()
            if line.isdigit():
                return int(line)
        return None

    def _uptime_seconds(self, pid: int) -> Optional[int]:
        try:
            result = subprocess.run(
                ["ps", "-o", "etimes=", "-p", str(pid)],
                capture_output=True,
                text=True,
                timeout=1.0,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None

        value = result.stdout.strip()
        return int(value) if value.isdigit() else None

    def _normalize_telemetry(self, telemetry: Dict[str, Any]) -> Dict[str, Any]:
        tokens = self._first_number(
            telemetry,
            ("tok_s", "tokens_per_second", "tokens_sec", "tps", "token_s", "tokens_per_sec"),
        )
        prefill_ms = self._first_number(
            telemetry,
            ("prefill_ms", "prefill_latency_ms", "prompt_ms", "prompt_eval_ms"),
        )
        uptime = self._first_number(telemetry, ("uptime_seconds", "uptime_sec", "uptime"))
        kv_cache = self._normalize_kv_cache(telemetry)

        normalized = {
            "tok_s": tokens,
            "prefill_latency_ms": prefill_ms,
            "uptime_seconds": uptime,
            "kv_cache": kv_cache,
        }
        for key in ("model", "backend", "version", "build"):
            if key in telemetry:
                normalized[key] = telemetry[key]
        return normalized

    def _normalize_kv_cache(self, telemetry: Dict[str, Any]) -> Dict[str, Any]:
        kv = telemetry.get("kv_cache") or telemetry.get("kv") or {}
        if not isinstance(kv, dict):
            kv = {"raw": kv}

        used_bytes = self._first_number(kv, ("used_bytes", "bytes_used", "used"))
        total_bytes = self._first_number(kv, ("total_bytes", "bytes_total", "capacity"))
        fill_percent = self._first_number(kv, ("fill_percent", "used_percent", "percent"))
        if fill_percent is None and used_bytes is not None and total_bytes:
            fill_percent = used_bytes / total_bytes * 100

        return {
            **kv,
            "used_bytes": used_bytes,
            "total_bytes": total_bytes,
            "fill_percent": fill_percent,
        }

    def _first_number(self, source: Dict[str, Any], keys: tuple[str, ...]) -> Optional[float]:
        for key in keys:
            value = source.get(key)
            if isinstance(value, bool) or value is None:
                continue
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                try:
                    return float(value)
                except ValueError:
                    continue
        return None

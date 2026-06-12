from __future__ import annotations

import json
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional


@dataclass(frozen=True)
class EngineClientConfig:
    host: str
    port: int
    telem_url: str
    binary_path: Path
    metrics_url: Optional[str] = None
    completion_url: Optional[str] = None
    request_timeout_seconds: float = 0.75
    generation_timeout_seconds: float = 45.0


class DS4EngineClient:
    def __init__(self, config: EngineClientConfig) -> None:
        self.config = config
        self.completion_url = config.completion_url or f"http://{config.host}:{config.port}/v1/chat/completions"
        self._telemetry_supported: bool | None = None  # None = untested, True/False = cached
        self._model_averages_provider: Optional[Callable[[], Dict[str, Any]]] = None

    def set_model_averages_provider(self, provider: Optional[Callable[[], Dict[str, Any]]]) -> None:
        self._model_averages_provider = provider

    def get_status(self) -> Dict[str, Any]:
        checked_at = time.time()
        port_open = self._is_port_open()
        pid = self._pid_for_port() if port_open else None

        # Only probe telemetry once; cache the result to avoid 404 spam
        if port_open and self._telemetry_supported is None:
            telemetry, telemetry_error = self.get_raw_telemetry()
            if telemetry_error and "404" in telemetry_error:
                self._telemetry_supported = False
            elif telemetry_error:
                # transient error (connection refused, timeout) — retry next poll
                self._telemetry_supported = None
            else:
                self._telemetry_supported = True
        elif port_open and self._telemetry_supported is False:
            # Already confirmed unsupported — skip probing, show clean message
            telemetry = None
            telemetry_error = None
        elif port_open and self._telemetry_supported is True:
            telemetry, telemetry_error = self.get_raw_telemetry()
        else:
            telemetry = None
            telemetry_error = None

        running = port_open
        state = "running" if running else "stopped"
        message = "DS4 port is accepting connections."
        if not running:
            message = f"DS4 is not accepting connections on port {self.config.port}."
        elif telemetry_error and self._telemetry_supported is not False:
            message = f"DS4 port is open; telemetry is idle or unavailable: {telemetry_error}"
        elif self._telemetry_supported is False:
            message = "DS4 port is open; telemetry endpoints are not exposed by this engine."
            telemetry_error = None  # suppress raw 404 from API response
        elif telemetry:
            message = "DS4 telemetry online."
        else:
            message = "DS4 port is open; no telemetry data available."

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

    def get_metrics(self) -> Dict[str, Any]:
        telemetry, error = self.get_raw_telemetry()
        return {
            "telemetry": self._normalize_telemetry(telemetry or {}),
            "telemetry_raw": telemetry,
            "telemetry_error": error,
            "port_open": self._is_port_open(),
            "checked_at": time.time(),
        }

    def get_raw_telemetry(self) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
        # Single source: /health endpoint (PR #374). No metrics fallback needed.
        payload, error = self._fetch_json_url(self.config.telem_url)
        if error:
            return None, error
        if payload is None:
            return None, None
        return payload if isinstance(payload, dict) else {"value": payload}, None

    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int = 256,
        temperature: float = 0.0,
        timeout_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        if not self._is_port_open():
            return {
                "ok": False,
                "text": "",
                "error": f"DS4 is not accepting connections on port {self.config.port}.",
                "latency_seconds": 0.0,
                "output_tokens": 0,
                "tok_s": None,
            }

        endpoints = (
            (
                self.completion_url,
                {
                    "model": "ds4",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "stream": False,
                },
                "chat",
            ),
            (
                f"http://{self.config.host}:{self.config.port}/completion",
                {
                    "prompt": prompt,
                    "n_predict": max_tokens,
                    "temperature": temperature,
                    "stream": False,
                },
                "completion",
            ),
        )

        timeout = timeout_seconds or self.config.generation_timeout_seconds
        errors: list[str] = []
        for url, payload, style in endpoints:
            started_at = time.perf_counter()
            raw, error = self._post_json_url(url, payload, timeout_seconds=timeout)
            latency = time.perf_counter() - started_at
            if error:
                errors.append(f"{url}: {error}")
                continue

            text = self._extract_generation_text(raw, style)
            usage = raw.get("usage", {}) if isinstance(raw, dict) else {}
            completion_tokens = self._first_number(usage, ("completion_tokens", "output_tokens", "tokens"))
            output_tokens = int(completion_tokens) if completion_tokens is not None else self._estimate_tokens(text)
            tok_s = output_tokens / latency if latency > 0 and output_tokens else None
            return {
                "ok": True,
                "text": text,
                "error": None,
                "latency_seconds": latency,
                "output_tokens": output_tokens,
                "tok_s": tok_s,
                "raw": raw,
                "endpoint": url,
            }

        return {
            "ok": False,
            "text": "",
            "error": "; ".join(errors) if errors else "No completion endpoint responded.",
            "latency_seconds": 0.0,
            "output_tokens": 0,
            "tok_s": None,
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

    def _fetch_json_url(self, url: str) -> tuple[Optional[Any], Optional[str]]:
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
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

        return parsed, None

    def _post_json_url(
        self,
        url: str,
        payload: Dict[str, Any],
        *,
        timeout_seconds: float,
    ) -> tuple[Dict[str, Any], Optional[str]]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                raw_body = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            return {}, f"HTTP {exc.code} {detail}".strip()
        except urllib.error.URLError as exc:
            return {}, str(exc.reason)
        except TimeoutError:
            return {}, "request timed out"
        except OSError as exc:
            return {}, str(exc)

        if not raw_body.strip():
            return {}, None
        try:
            parsed = json.loads(raw_body)
        except json.JSONDecodeError:
            return {"text": raw_body}, None
        return parsed if isinstance(parsed, dict) else {"value": parsed}, None

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
        prefill_tps = self._first_number(
            telemetry,
            ("prefill_tok_s", "prefill_tokens_per_second", "prompt_tok_s", "prompt_tokens_per_second"),
        )
        prefill_ms = self._first_number(
            telemetry,
            ("prefill_ms", "prefill_latency_ms", "prompt_ms", "prompt_eval_ms"),
        )
        uptime = self._first_number(telemetry, ("uptime_seconds", "uptime_sec", "uptime"))
        kv_cache = self._normalize_kv_cache(telemetry)

        normalized = {
            "tok_s": tokens if tokens is not None else self._model_average_number("tok_s"),
            "prefill_tok_s": prefill_tps if prefill_tps is not None else self._model_average_number("prefill_tok_s"),
            "prefill_latency_ms": prefill_ms,
            "uptime_seconds": uptime,
            "kv_cache": kv_cache,
        }
        for key in ("model", "backend", "version", "build", "requests", "active_requests"):
            if key in telemetry:
                normalized[key] = telemetry[key]
        return normalized

    def _normalize_kv_cache(self, telemetry: Dict[str, Any]) -> Dict[str, Any]:
        kv = telemetry.get("kv_cache") or telemetry.get("kv") or {}
        if not isinstance(kv, dict):
            kv = {"raw": kv}

        used_bytes = self._first_number(kv, ("used_bytes", "bytes_used", "used"))
        total_bytes = self._first_number(kv, ("total_bytes", "bytes_total", "capacity"))
        budget_bytes = self._first_number(kv, ("budget_bytes", "bytes_budget", "budget"))
        fill_percent = self._first_number(kv, ("fill_percent", "used_percent", "percent"))
        denominator = total_bytes or budget_bytes
        if fill_percent is None and used_bytes is not None and denominator:
            fill_percent = used_bytes / denominator * 100

        return {
            **kv,
            "used_bytes": used_bytes,
            "total_bytes": total_bytes,
            "budget_bytes": budget_bytes,
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

    def _model_average_number(self, metric: str) -> Optional[float]:
        if self._model_averages_provider is None:
            return None
        try:
            averages = self._model_averages_provider()
        except Exception:
            return None
        if not isinstance(averages, dict):
            return None

        metric_stats = averages.get(metric)
        if isinstance(metric_stats, dict):
            for key in ("avg", "last", "value"):
                value = metric_stats.get(key)
                number = self._coerce_number(value)
                if number is not None:
                    return number
        return self._coerce_number(metric_stats)

    def _coerce_number(self, value: Any) -> Optional[float]:
        if isinstance(value, bool) or value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return None
        return None

    def _extract_generation_text(self, raw: Dict[str, Any], style: str) -> str:
        if not isinstance(raw, dict):
            return ""
        if style == "chat":
            choices = raw.get("choices")
            if isinstance(choices, list) and choices:
                first = choices[0]
                if isinstance(first, dict):
                    message = first.get("message")
                    if isinstance(message, dict) and isinstance(message.get("content"), str):
                        return message["content"]
                    if isinstance(first.get("text"), str):
                        return first["text"]
        for key in ("content", "text", "response", "completion", "value"):
            value = raw.get(key)
            if isinstance(value, str):
                return value
        return ""

    def _estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        return max(1, int(len(text.split()) * 1.35))

    # Removed: _derive_metrics_url — no longer needed since /health is self-contained

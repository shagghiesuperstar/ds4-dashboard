from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ConfigOption:
    key: str
    type: str
    default: Any = None
    desc: str = ""
    source: str = "dashboard"
    flag: Optional[str] = None
    choices: Optional[list[str]] = None

    def as_dict(self, current: Any = None) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "type": self.type,
            "default": self.default,
            "desc": self.desc,
            "source": self.source,
            "current": self.default if current is None else current,
        }
        if self.flag:
            data["flag"] = self.flag
        if self.choices:
            data["choices"] = self.choices
        return data


class DS4ConfigManager:
    def __init__(
        self,
        *,
        binary_path: Path,
        telem_url: str,
        defaults: Dict[str, Any],
        kv_cache_path: Path,
        metal_dir: Path,
        discovery_ttl_seconds: float = 30.0,
        launchd_label: str = "com.dwarfstar.ds4",
    ) -> None:
        self.binary_path = binary_path
        self.telem_url = telem_url
        self.defaults = dict(defaults)
        self.kv_cache_path = kv_cache_path
        self.metal_dir = metal_dir
        self.discovery_ttl_seconds = discovery_ttl_seconds
        self.launchd_label = launchd_label
        self._overrides: Dict[str, Any] = {}
        self._schema_cache: Optional[Dict[str, ConfigOption]] = None
        self._schema_cache_at = 0.0

    def get_config(self) -> Dict[str, Any]:
        values = self.effective_values()
        kv_cache_path = Path(str(values.get("kv_disk_cache", self.kv_cache_path))).expanduser()
        metal_dir = Path(str(values.get("metal_shader_dir", self.metal_dir))).expanduser()

        return {
            "engine": "ds4",
            "binary": self._path_info(Path(str(values.get("binary", self.binary_path))).expanduser()),
            "primary_host": values.get("primary_host"),
            "primary_port": values.get("primary_port"),
            "telem_url": values.get("telem_url"),
            "completion_url": values.get("completion_url"),
            "model": self._path_info(Path(str(values.get("model", ""))).expanduser()),
            "mtp": self._path_info(Path(str(values.get("mtp", ""))).expanduser()),
            "context_window": values.get("context_window"),
            "kv_disk_cache": {
                "path": str(kv_cache_path),
                "budget_mib": values.get("kv_cache_budget_mib"),
                "budget_bytes": self._mib_to_bytes(values.get("kv_cache_budget_mib")),
                "exists": kv_cache_path.exists(),
            },
            "metal": {
                "path": str(metal_dir),
                "shader_count": self._count_metal_shaders(metal_dir),
            },
            "poll_interval_ms": values.get("poll_interval_ms", 2000),
            "overrides": dict(self._overrides),
        }

    def get_schema(self, *, force_refresh: bool = False) -> Dict[str, Dict[str, Any]]:
        options = self._load_schema(force_refresh=force_refresh)
        values = self.effective_values()
        return {key: option.as_dict(values.get(key)) for key, option in sorted(options.items())}

    def effective_values(self) -> Dict[str, Any]:
        values = dict(self.defaults)
        options = self._load_schema(force_refresh=False)
        for key, value in self._overrides.items():
            option = options.get(key)
            values[key] = self._coerce_value(value, option.type if option else "string")
        return values

    def get_overrides(self) -> Dict[str, Any]:
        return dict(self._overrides)

    # Keys that require a full DS4 restart to take effect
    _RESTART_REQUIRED_KEYS: set = {
        "model",
        "mtp",
        "context_window",
        "binary",
        "primary_host",
        "primary_port",
        "kv_disk_cache",
        "kv_cache_budget_mib",
        "metal_shader_dir",
    }

    def set_override(self, key: str, value: Any) -> Dict[str, Any]:
        normalized_key = self._normalize_key(key)
        if not normalized_key:
            raise ValueError("Config key is required.")

        schema = self._load_schema(force_refresh=False)
        option = schema.get(normalized_key)
        coerced = self._coerce_value(value, option.type if option else "string")
        self._overrides[normalized_key] = coerced
        restart_needed = normalized_key in self._RESTART_REQUIRED_KEYS
        return {
            "key": normalized_key,
            "value": coerced,
            "schema_known": option is not None,
            "type": option.type if option else "string",
            "restart_needed": restart_needed,
        }

    def key_requires_restart(self, key: str) -> bool:
        normalized_key = self._normalize_key(key)
        return normalized_key in self._RESTART_REQUIRED_KEYS

    def apply_and_restart(self, key: str, value: Any, restart_script: str) -> Dict[str, Any]:
        """Set an override and restart DS4 if the key requires it.

        Prefer the installed launchd service. The restart_script is retained as
        a legacy fallback for older local setups.
        """
        normalized_key = self._normalize_key(key)
        if not normalized_key:
            raise ValueError("Config key is required.")

        schema = self._load_schema(force_refresh=False)
        option = schema.get(normalized_key)
        coerced = self._coerce_value(value, option.type if option else "string")
        self._overrides[normalized_key] = coerced
        restart_needed = normalized_key in self._RESTART_REQUIRED_KEYS

        restart_result: Dict[str, Any] = {"triggered": False, "exit_code": -1, "stdout": "", "stderr": ""}
        if restart_needed:
            restart_result = self.restart_ds4(restart_script=restart_script)

        return {
            "key": normalized_key,
            "value": coerced,
            "schema_known": option is not None,
            "type": option.type if option else "string",
            "restart_needed": restart_needed,
            "restart": restart_result,
        }

    def restart_ds4(self, restart_script: Optional[str] = None) -> Dict[str, Any]:
        """Restart DS4, preferring launchd when the LaunchAgent is loaded."""
        if self._launchd_loaded():
            return self._kickstart_launchd()

        if restart_script and Path(restart_script).exists():
            if platform.system() != "Darwin" or shutil.which("launchctl") is None:
                return {
                    "triggered": False,
                    "method": "legacy-script",
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": "",
                    "error": "launchd is unavailable; install scripts/ds4-launchd.plist first.",
                }
            try:
                proc = subprocess.run(
                    ["bash", restart_script],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                return {
                    "triggered": True,
                    "method": "legacy-script",
                    "exit_code": proc.returncode,
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "command": f"bash {restart_script}",
                }
            except (OSError, subprocess.TimeoutExpired) as exc:
                return {
                    "triggered": True,
                    "method": "legacy-script",
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": "",
                    "error": str(exc),
                }

        return {
            "triggered": False,
            "method": "launchd",
            "exit_code": -1,
            "stdout": "",
            "stderr": "",
            "error": f"launchd service {self.launchd_label} is not loaded.",
        }

    def clear_override(self, key: str) -> bool:
        normalized_key = self._normalize_key(key)
        return self._overrides.pop(normalized_key, None) is not None

    def _launchd_target(self) -> str:
        return f"gui/{os.getuid()}/{self.launchd_label}"

    def _launchd_loaded(self) -> bool:
        if platform.system() != "Darwin" or shutil.which("launchctl") is None:
            return False
        try:
            result = subprocess.run(
                ["launchctl", "print", self._launchd_target()],
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0

    def _kickstart_launchd(self) -> Dict[str, Any]:
        target = self._launchd_target()
        command = ["launchctl", "kickstart", "-k", target]
        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            return {
                "triggered": True,
                "method": "launchd",
                "label": self.launchd_label,
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "command": " ".join(command),
            }
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {
                "triggered": True,
                "method": "launchd",
                "label": self.launchd_label,
                "exit_code": -1,
                "stdout": "",
                "stderr": "",
                "command": " ".join(command),
                "error": str(exc),
            }

    def _load_schema(self, *, force_refresh: bool) -> Dict[str, ConfigOption]:
        now = time.monotonic()
        if (
            not force_refresh
            and self._schema_cache is not None
            and now - self._schema_cache_at < self.discovery_ttl_seconds
        ):
            return self._schema_cache

        schema = self._builtin_schema()
        schema.update(self._discover_help_options())
        schema.update(self._discover_telemetry_schema())
        self._schema_cache = schema
        self._schema_cache_at = now
        return schema

    def _builtin_schema(self) -> Dict[str, ConfigOption]:
        return {
            "binary": ConfigOption(
                "binary",
                "path",
                str(self.binary_path),
                "DS4 server binary path.",
                source="dashboard env",
            ),
            "primary_port": ConfigOption(
                "primary_port",
                "int",
                self.defaults.get("primary_port"),
                "DS4 primary server and telemetry port.",
                source="dashboard env",
                flag="--port",
            ),
            "primary_host": ConfigOption(
                "primary_host",
                "string",
                self.defaults.get("primary_host"),
                "DS4 primary server host used by dashboard API clients.",
                source="dashboard env",
                flag="--host",
            ),
            "telem_url": ConfigOption(
                "telem_url",
                "string",
                self.defaults.get("telem_url"),
                "DS4 telemetry endpoint polled by the dashboard.",
                source="dashboard env",
            ),
            "metrics_url": ConfigOption(
                "metrics_url",
                "string",
                self.defaults.get("metrics_url"),
                "DS4 metrics endpoint merged with telemetry when available.",
                source="dashboard env",
            ),
            "completion_url": ConfigOption(
                "completion_url",
                "string",
                self.defaults.get("completion_url"),
                "OpenAI-compatible chat completion endpoint used by benchmarks.",
                source="dashboard env",
            ),
            "model": ConfigOption(
                "model",
                "path",
                self.defaults.get("model"),
                "Main GGUF model path or symlink.",
                source="dashboard env",
                flag="--model",
            ),
            "mtp": ConfigOption(
                "mtp",
                "path",
                self.defaults.get("mtp"),
                "MTP draft model GGUF path.",
                source="dashboard env",
                flag="--mtp",
            ),
            "context_window": ConfigOption(
                "context_window",
                "int",
                self.defaults.get("context_window"),
                "Configured DS4 context window.",
                source="dashboard env",
                flag="--ctx",
            ),
            "kv_disk_cache": ConfigOption(
                "kv_disk_cache",
                "path",
                self.defaults.get("kv_disk_cache"),
                "KV disk cache directory.",
                source="dashboard env",
                flag="--kv-disk-cache",
            ),
            "kv_cache_budget_mib": ConfigOption(
                "kv_cache_budget_mib",
                "int",
                self.defaults.get("kv_cache_budget_mib"),
                "KV disk cache budget in MiB.",
                source="dashboard env",
            ),
            "metal_shader_dir": ConfigOption(
                "metal_shader_dir",
                "path",
                self.defaults.get("metal_shader_dir"),
                "Directory containing Metal shader sources.",
                source="dashboard env",
            ),
            "poll_interval_ms": ConfigOption(
                "poll_interval_ms",
                "int",
                self.defaults.get("poll_interval_ms", 2000),
                "Dashboard telemetry polling interval in milliseconds.",
                source="dashboard env",
            ),
        }

    def _discover_help_options(self) -> Dict[str, ConfigOption]:
        if not self.binary_path.exists():
            return {}

        text = ""
        for argument in ("--help", "-h"):
            try:
                result = subprocess.run(
                    [str(self.binary_path), argument],
                    capture_output=True,
                    text=True,
                    timeout=2.0,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            text = "\n".join(part for part in (result.stdout, result.stderr) if part)
            if text.strip():
                break
        if not text.strip():
            return {}

        options: Dict[str, ConfigOption] = {}
        for line in text.splitlines():
            parsed = self._parse_help_line(line)
            if parsed:
                options[parsed.key] = parsed
        return options

    def _discover_telemetry_schema(self) -> Dict[str, ConfigOption]:
        request = urllib.request.Request(self.telem_url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=0.45) as response:
                body = response.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError):
            return {}

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return {}
        if not isinstance(payload, dict):
            return {}

        raw_schema = payload.get("config_schema") or payload.get("schema")
        if not isinstance(raw_schema, dict):
            return {}

        discovered: Dict[str, ConfigOption] = {}
        for raw_key, meta in raw_schema.items():
            key = self._normalize_key(str(raw_key))
            if not key:
                continue
            if isinstance(meta, dict):
                option_type = str(meta.get("type") or self._infer_type(key, str(meta.get("desc", "")), None))
                default = meta.get("default")
                desc = str(meta.get("desc") or meta.get("description") or "Discovered from DS4 telemetry schema.")
                choices = meta.get("choices") if isinstance(meta.get("choices"), list) else None
            else:
                option_type = self._infer_type(key, "", meta)
                default = meta
                desc = "Discovered from DS4 telemetry schema."
                choices = None
            discovered[key] = ConfigOption(key, option_type, default, desc, source="telem schema", choices=choices)
        return discovered

    def _parse_help_line(self, line: str) -> Optional[ConfigOption]:
        if "--" not in line:
            return None
        match = re.search(r"(?P<flag>--[A-Za-z0-9][A-Za-z0-9_-]*)(?:[=\s]+(?P<arg><[^>]+>|\[[^\]]+\]|[A-Z][A-Z0-9_-]*|\w+))?", line)
        if not match:
            return None

        flag = match.group("flag")
        argument = match.group("arg")
        key = self._normalize_key(flag)
        if not key:
            return None

        desc = line[match.end() :].strip(" \t:-")
        if not desc:
            desc = f"Discovered from DS4 help output for {flag}."
        option_type = self._infer_type(key, desc, argument)
        default = self._extract_default(desc, option_type)
        return ConfigOption(key, option_type, default, desc, source="binary --help", flag=flag)

    def _normalize_key(self, key: str) -> str:
        normalized = key.strip().lstrip("-").replace("-", "_")
        normalized = re.sub(r"[^A-Za-z0-9_]+", "_", normalized).strip("_").lower()
        return normalized

    def _infer_type(self, key: str, desc: str, argument: Any) -> str:
        haystack = f"{key} {desc}".lower()
        if argument is None and any(word in haystack for word in ("enable", "disable", "verbose", "debug", "no_")):
            return "bool"
        if argument is None:
            return "bool"
        if isinstance(argument, bool):
            return "bool"
        if isinstance(argument, int):
            return "int"
        if isinstance(argument, float):
            return "float"
        if any(word in haystack for word in ("path", "file", "dir", "model", "cache", "binary", "gguf")):
            return "path"
        if any(word in haystack for word in ("port", "threads", "count", "size", "limit", "window", "ctx", "budget", "tokens")):
            return "int"
        if any(word in haystack for word in ("temp", "temperature", "top_p", "prob", "ratio", "scale")):
            return "float"
        return "string"

    def _extract_default(self, desc: str, option_type: str) -> Any:
        match = re.search(r"default(?:s)?(?:\s+to)?\s*[=:]?\s*([^\s,;\)]+)", desc, re.I)
        if not match:
            return None
        return self._coerce_value(match.group(1).strip("'\""), option_type)

    def _coerce_value(self, value: Any, option_type: str) -> Any:
        if value is None:
            return None
        if option_type == "bool":
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled", "enable"}
        if option_type == "int":
            if isinstance(value, int) and not isinstance(value, bool):
                return value
            return int(float(str(value).strip()))
        if option_type == "float":
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value)
            return float(str(value).strip())
        if option_type == "path":
            return str(Path(str(value)).expanduser())
        return str(value)

    def _path_info(self, path: Path) -> Dict[str, Any]:
        return {
            "path": str(path),
            "exists": path.exists(),
            "is_symlink": path.is_symlink(),
            "resolved": str(path.resolve()) if path.exists() else None,
        }

    def _count_metal_shaders(self, path: Path) -> int:
        if not path.is_dir():
            return 0
        return len([entry for entry in path.iterdir() if entry.is_file() and entry.suffix == ".metal"])

    def _mib_to_bytes(self, value: Any) -> Optional[int]:
        try:
            return int(value) * 1024 * 1024
        except (TypeError, ValueError):
            return None

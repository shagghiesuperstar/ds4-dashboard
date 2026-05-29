from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional


class MacSystemMetrics:
    def get_metrics(
        self,
        *,
        pid: Optional[int] = None,
        kv_cache_path: Optional[Path] = None,
        kv_budget_bytes: Optional[int] = None,
    ) -> Dict[str, Any]:
        return {
            "memory": self._memory_metrics(),
            "cpu": self._cpu_metrics(),
            "gpu": self._gpu_metrics(),
            "temperature": self._temperature_metrics(),
            "process": self._process_metrics(pid) if pid else None,
            "kv_disk_cache": self._kv_disk_cache_metrics(kv_cache_path, kv_budget_bytes),
        }

    def _memory_metrics(self) -> Dict[str, Any]:
        sysctl_total_bytes = self._sysctl_int("hw.memsize")
        total_bytes = sysctl_total_bytes
        page_size, pages = self._vm_stat()
        if total_bytes is None and page_size:
            total_pages = sum(
                pages.get(key, 0)
                for key in (
                    "pages_free",
                    "pages_active",
                    "pages_inactive",
                    "pages_speculative",
                    "pages_throttled",
                    "pages_wired_down",
                    "pages_occupied_by_compressor",
                    "pages_compressor",
                )
            )
            total_bytes = total_pages * page_size if total_pages else None

        free_pages = pages.get("pages_free", 0) + pages.get("pages_speculative", 0)
        free_bytes = free_pages * page_size if page_size and total_bytes else None
        used_bytes = total_bytes - free_bytes if total_bytes is not None and free_bytes is not None else None
        free_percent = free_bytes / total_bytes * 100 if total_bytes and free_bytes is not None else None
        used_percent = used_bytes / total_bytes * 100 if total_bytes and used_bytes is not None else None

        return {
            "source": "sysctl+vm_stat" if sysctl_total_bytes is not None else "vm_stat_estimate",
            "total_bytes": total_bytes,
            "free_bytes": free_bytes,
            "used_bytes": used_bytes,
            "free_percent": free_percent,
            "used_percent": used_percent,
            "pressure": self._pressure_label(free_percent),
            "swap": self._swap_metrics(),
            "page_size": page_size,
            "pages": pages,
        }

    def _cpu_metrics(self) -> Dict[str, Any]:
        usage_percent = self._top_cpu_usage()
        load_average = self._load_average()
        return {
            "source": "top+sysctl",
            "usage_percent": usage_percent,
            "load_average": load_average,
            "core_count": os.cpu_count(),
            "temperature_c": None,
            "temperature_source": "see top-level temperature metrics",
        }

    def _gpu_metrics(self) -> Dict[str, Any]:
        ioreg = self._run(["ioreg", "-r", "-n", "AGXAccelerator", "-d", "1"], timeout=1.0)
        utilization = self._first_percent(ioreg.stdout, ("Device Utilization", "GPU Busy", "Busy")) if ioreg else None
        source = "ioreg AGXAccelerator" if utilization is not None else "unavailable"

        if utilization is None:
            powermetrics = self._run(
                ["powermetrics", "--samplers", "gpu_power", "-n", "1", "-i", "250"],
                timeout=1.25,
            )
            if powermetrics:
                utilization = self._first_percent(powermetrics.stdout, ("GPU Active", "GPU Busy", "GPU"))
                source = "powermetrics gpu_power" if utilization is not None else source

        return {
            "source": source,
            "utilization_percent": utilization,
            "note": None if utilization is not None else "GPU utilization is best-effort on macOS without privileged samplers.",
        }

    def _temperature_metrics(self) -> Dict[str, Any]:
        osx_cpu_temp = self._run(["osx-cpu-temp"], timeout=0.75)
        if osx_cpu_temp and osx_cpu_temp.stdout.strip():
            value = self._first_number(osx_cpu_temp.stdout)
            return {
                "source": "osx-cpu-temp",
                "cpu_c": value,
                "gpu_c": None,
                "available": value is not None,
            }

        powermetrics = self._run(
            ["powermetrics", "--samplers", "smc", "-n", "1", "-i", "250"],
            timeout=1.25,
        )
        text = powermetrics.stdout if powermetrics else ""
        cpu_temp = self._temperature_after_label(text, ("CPU die temperature", "CPU temp", "CPU"))
        gpu_temp = self._temperature_after_label(text, ("GPU die temperature", "GPU temp", "GPU"))
        return {
            "source": "powermetrics smc" if cpu_temp is not None or gpu_temp is not None else "unavailable",
            "cpu_c": cpu_temp,
            "gpu_c": gpu_temp,
            "available": cpu_temp is not None or gpu_temp is not None,
            "note": None
            if cpu_temp is not None or gpu_temp is not None
            else "Temperature samplers often require sudo or a helper such as osx-cpu-temp.",
        }

    def _process_metrics(self, pid: int) -> Dict[str, Any]:
        result = self._run(["ps", "-o", "pid=,rss=,%cpu=,%mem=,command=", "-p", str(pid)], timeout=1.0)
        if not result or not result.stdout.strip():
            return {"pid": pid, "running": False}

        line = result.stdout.strip().splitlines()[0].strip()
        match = re.match(r"(\d+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s+(.*)", line)
        if not match:
            return {"pid": pid, "running": True, "raw": line}

        return {
            "pid": int(match.group(1)),
            "running": True,
            "rss_bytes": int(match.group(2)) * 1024,
            "cpu_percent": float(match.group(3)),
            "memory_percent": float(match.group(4)),
            "command": match.group(5),
        }

    def _kv_disk_cache_metrics(
        self,
        path: Optional[Path],
        budget_bytes: Optional[int],
    ) -> Optional[Dict[str, Any]]:
        if path is None:
            return None
        result: Dict[str, Any] = {
            "path": str(path),
            "exists": path.exists(),
            "budget_bytes": budget_bytes,
            "used_bytes": None,
            "fill_percent": None,
        }
        if not path.exists():
            return result

        used_bytes = self._du_bytes(path)
        result["used_bytes"] = used_bytes
        if used_bytes is not None and budget_bytes:
            result["fill_percent"] = used_bytes / budget_bytes * 100
        return result

    def _sysctl_int(self, name: str) -> Optional[int]:
        result = self._run(["sysctl", "-n", name], timeout=1.0)
        if not result:
            return None
        value = result.stdout.strip()
        return int(value) if value.isdigit() else None

    def _load_average(self) -> Optional[list[float]]:
        result = self._run(["sysctl", "-n", "vm.loadavg"], timeout=1.0)
        if result:
            matches = re.findall(r"\d+(?:\.\d+)?", result.stdout)
            if len(matches) >= 3:
                return [float(value) for value in matches[:3]]
        try:
            return [float(value) for value in os.getloadavg()]
        except OSError:
            return None

    def _swap_metrics(self) -> Dict[str, Any]:
        result = self._run(["sysctl", "-n", "vm.swapusage"], timeout=1.0)
        if not result:
            return {"source": "unavailable", "total_bytes": None, "used_bytes": None, "free_bytes": None}

        values: Dict[str, int] = {}
        for key, value, unit in re.findall(r"(total|used|free)\s+=\s+([\d.]+)([KMG]?)", result.stdout, re.I):
            multiplier = {"": 1, "K": 1024, "M": 1024**2, "G": 1024**3}[unit.upper()]
            values[f"{key.lower()}_bytes"] = int(float(value) * multiplier)
        return {"source": "sysctl vm.swapusage", **values}

    def _vm_stat(self) -> tuple[Optional[int], Dict[str, int]]:
        result = self._run(["vm_stat"], timeout=1.0)
        if not result:
            return None, {}

        page_size = None
        pages: Dict[str, int] = {}
        for line in result.stdout.splitlines():
            if page_size is None:
                match = re.search(r"page size of (\d+) bytes", line)
                if match:
                    page_size = int(match.group(1))
                    continue

            match = re.match(r"([^:]+):\s+([0-9]+)\.", line.strip())
            if not match:
                continue
            key = re.sub(r"[^a-z0-9]+", "_", match.group(1).strip().lower()).strip("_")
            if key.startswith("pages_"):
                key = key.removeprefix("pages_")
            key = f"pages_{key}"
            pages[key] = int(match.group(2))

        if page_size is None:
            page_size = self._sysctl_int("hw.pagesize")
        return page_size, pages

    def _top_cpu_usage(self) -> Optional[float]:
        result = self._run(["top", "-l", "1", "-n", "0", "-stats", "cpu"], timeout=2.0)
        if not result:
            return None

        match = re.search(r"CPU usage:\s+([\d.]+)% user,\s+([\d.]+)% sys", result.stdout)
        if not match:
            return None
        return float(match.group(1)) + float(match.group(2))

    def _du_bytes(self, path: Path) -> Optional[int]:
        result = self._run(["du", "-sk", str(path)], timeout=2.0)
        if not result:
            return None
        first = result.stdout.strip().split(maxsplit=1)[0] if result.stdout.strip() else ""
        return int(first) * 1024 if first.isdigit() else None

    def _run(self, command: list[str], *, timeout: float) -> Optional[subprocess.CompletedProcess[str]]:
        try:
            return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return None

    def _pressure_label(self, free_percent: Optional[float]) -> str:
        if free_percent is None:
            return "unknown"
        if free_percent > 30:
            return "green"
        if free_percent >= 15:
            return "amber"
        return "red"

    def _first_percent(self, text: str, labels: tuple[str, ...]) -> Optional[float]:
        for label in labels:
            match = re.search(rf"{re.escape(label)}[^0-9]*(\d+(?:\.\d+)?)\s*%", text, re.I)
            if match:
                return float(match.group(1))
        return None

    def _temperature_after_label(self, text: str, labels: tuple[str, ...]) -> Optional[float]:
        for label in labels:
            match = re.search(rf"{re.escape(label)}[^0-9]*(\d+(?:\.\d+)?)\s*(?:C|c|degC)", text)
            if match:
                return float(match.group(1))
        return None

    def _first_number(self, text: str) -> Optional[float]:
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        return float(match.group(0)) if match else None

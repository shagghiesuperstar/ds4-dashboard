from __future__ import annotations

import os
import re
import subprocess
from typing import Any, Dict, Optional


class MacSystemMetrics:
    def get_metrics(self) -> Dict[str, Any]:
        return {
            "memory": self._memory_metrics(),
            "cpu": self._cpu_metrics(),
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
            "temperature_c": None,
            "temperature_source": "powermetrics requires sudo and is not used by the MVP.",
        }

    def _sysctl_int(self, name: str) -> Optional[int]:
        try:
            result = subprocess.run(
                ["sysctl", "-n", name],
                capture_output=True,
                text=True,
                timeout=1.0,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None

        value = result.stdout.strip()
        return int(value) if value.isdigit() else None

    def _load_average(self) -> Optional[list[float]]:
        try:
            result = subprocess.run(
                ["sysctl", "-n", "vm.loadavg"],
                capture_output=True,
                text=True,
                timeout=1.0,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None

        matches = re.findall(r"\d+(?:\.\d+)?", result.stdout)
        if len(matches) < 3:
            try:
                return [float(value) for value in os.getloadavg()]
            except OSError:
                return None
        return [float(value) for value in matches[:3]]

    def _vm_stat(self) -> tuple[Optional[int], Dict[str, int]]:
        try:
            result = subprocess.run(
                ["vm_stat"],
                capture_output=True,
                text=True,
                timeout=1.0,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
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
        try:
            result = subprocess.run(
                ["top", "-l", "1", "-n", "0", "-stats", "cpu"],
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None

        match = re.search(r"CPU usage:\s+([\d.]+)% user,\s+([\d.]+)% sys", result.stdout)
        if not match:
            return None
        return float(match.group(1)) + float(match.group(2))

    def _pressure_label(self, free_percent: Optional[float]) -> str:
        if free_percent is None:
            return "unknown"
        if free_percent > 30:
            return "green"
        if free_percent >= 15:
            return "amber"
        return "red"

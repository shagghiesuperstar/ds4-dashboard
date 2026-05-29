from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional


class DS4Updater:
    def __init__(
        self,
        *,
        repo: str,
        binary_path: Path,
        backups_path: Optional[Path] = None,
        backup_limit: int = 5,
    ) -> None:
        self.repo = repo
        self.binary_path = binary_path
        self.backups_path = backups_path or Path(__file__).resolve().parent / "backups.json"
        self.backup_limit = max(1, int(backup_limit))

    def check_latest_release(self) -> Dict[str, Any]:
        url = f"https://api.github.com/repos/{self.repo}/releases/latest"
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "ds4-dashboard",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=5.0) as response:
                payload = json.loads(response.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as exc:
            return {"ok": False, "repo": self.repo, "error": f"GitHub returned HTTP {exc.code}"}
        except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError) as exc:
            return {"ok": False, "repo": self.repo, "error": str(exc)}

        assets = []
        for asset in payload.get("assets", []):
            if not isinstance(asset, dict):
                continue
            assets.append(
                {
                    "name": asset.get("name"),
                    "size": asset.get("size"),
                    "browser_download_url": asset.get("browser_download_url"),
                    "content_type": asset.get("content_type"),
                }
            )

        return {
            "ok": True,
            "repo": self.repo,
            "tag_name": payload.get("tag_name"),
            "name": payload.get("name"),
            "published_at": payload.get("published_at"),
            "html_url": payload.get("html_url"),
            "assets": assets,
            "binary_path": str(self.binary_path),
            "binary_exists": self.binary_path.exists(),
            "backups": self._load_backups(),
        }

    def update(
        self,
        *,
        asset_url: Optional[str] = None,
        sha256: Optional[str] = None,
        apply: bool = False,
    ) -> Dict[str, Any]:
        release = self.check_latest_release()
        if not release.get("ok"):
            return release
        if not apply:
            return {
                "ok": True,
                "dry_run": True,
                "message": "Release check completed. Pass apply=true and an asset URL to install.",
                "release": release,
            }

        download_url = asset_url or self._first_binary_asset_url(release)
        if not download_url:
            return {"ok": False, "error": "No release asset URL was provided or discovered.", "release": release}

        downloaded = self._download_asset(download_url)
        if not downloaded.get("ok"):
            return {**downloaded, "release": release}

        tmp_path = Path(str(downloaded["path"]))
        actual_sha256 = self._sha256(tmp_path)
        if sha256 and actual_sha256.lower() != sha256.lower():
            tmp_path.unlink(missing_ok=True)
            return {
                "ok": False,
                "error": "SHA256 verification failed.",
                "expected_sha256": sha256,
                "actual_sha256": actual_sha256,
                "release": release,
            }

        backup_path = self._backup_path()
        backup_entry = None
        try:
            self.binary_path.parent.mkdir(parents=True, exist_ok=True)
            if self.binary_path.exists():
                shutil.copy2(self.binary_path, backup_path)
                backup_entry = self._record_backup(backup_path)
            shutil.move(str(tmp_path), str(self.binary_path))
            mode = self.binary_path.stat().st_mode
            self.binary_path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except OSError as exc:
            if backup_path.exists():
                shutil.copy2(backup_path, self.binary_path)
            return {"ok": False, "error": str(exc), "backup_path": str(backup_path), "release": release}

        return {
            "ok": True,
            "dry_run": False,
            "message": "DS4 binary updated. Restart DS4 to use the new binary.",
            "binary_path": str(self.binary_path),
            "backup_path": str(backup_path) if backup_path.exists() else None,
            "backup": backup_entry,
            "backups": self._load_backups(),
            "sha256": actual_sha256,
            "release": release,
        }

    def rollback(self) -> Dict[str, Any]:
        backups = self._load_backups()
        backup = self._latest_existing_backup(backups)
        if not backup:
            return {
                "ok": False,
                "error": "No rollback backup is available.",
                "binary_path": str(self.binary_path),
                "backups": backups,
            }

        backup_path = Path(str(backup["path"])).expanduser()
        tmp_path = self.binary_path.with_name(f".{self.binary_path.name}.rollback.{self._timestamp()}.tmp")
        swapped_current = False
        try:
            self.binary_path.parent.mkdir(parents=True, exist_ok=True)
            if self.binary_path.exists():
                shutil.copy2(self.binary_path, tmp_path)
                swapped_current = True
            shutil.copy2(backup_path, self.binary_path)
            mode = self.binary_path.stat().st_mode
            self.binary_path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            if swapped_current:
                shutil.copy2(tmp_path, backup_path)
                self._refresh_backup_entry(backups, backup_path)
        except OSError as exc:
            return {
                "ok": False,
                "error": str(exc),
                "binary_path": str(self.binary_path),
                "backup": backup,
                "backups": self._load_backups(),
            }
        finally:
            tmp_path.unlink(missing_ok=True)

        return {
            "ok": True,
            "message": "DS4 binary rolled back. Restart DS4 to use the restored binary.",
            "binary_path": str(self.binary_path),
            "backup_path": str(backup_path),
            "swapped_current": swapped_current,
            "backup": backup,
            "backups": self._load_backups(),
        }

    def _first_binary_asset_url(self, release: Dict[str, Any]) -> Optional[str]:
        for asset in release.get("assets", []):
            name = str(asset.get("name") or "").lower()
            if "ds4" in name and not name.endswith((".sha256", ".txt")):
                return asset.get("browser_download_url")
        return None

    def _download_asset(self, url: str) -> Dict[str, Any]:
        request = urllib.request.Request(url, headers={"User-Agent": "ds4-dashboard"})
        try:
            with urllib.request.urlopen(request, timeout=60.0) as response:
                fd, tmp_name = tempfile.mkstemp(prefix="ds4-update-", dir="/private/tmp" if os.path.isdir("/private/tmp") else None)
                with os.fdopen(fd, "wb") as handle:
                    shutil.copyfileobj(response, handle)
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "path": tmp_name}

    def _backup_path(self) -> Path:
        return self.binary_path.with_name(f"{self.binary_path.name}.bak.{self._timestamp()}")

    def _timestamp(self) -> str:
        return time.strftime("%Y%m%d-%H%M%S")

    def _backup_entry(self, backup_path: Path) -> Dict[str, Any]:
        entry = {
            "timestamp": self._timestamp(),
            "path": str(backup_path),
            "binary_path": str(self.binary_path),
        }
        try:
            entry["size"] = backup_path.stat().st_size
        except OSError:
            entry["size"] = None
        return entry

    def _record_backup(self, backup_path: Path) -> Dict[str, Any]:
        entry = self._backup_entry(backup_path)
        backups = [item for item in self._load_backups() if item.get("path") != str(backup_path)]
        backups.append(entry)
        backups = backups[-self.backup_limit:]
        self._write_backups(backups)
        return entry

    def _refresh_backup_entry(self, backups: List[Dict[str, Any]], backup_path: Path) -> None:
        refreshed = self._backup_entry(backup_path)
        refreshed["timestamp"] = next(
            (item.get("timestamp") for item in backups if item.get("path") == str(backup_path)),
            refreshed["timestamp"],
        )
        updated = []
        for item in backups:
            updated.append(refreshed if item.get("path") == str(backup_path) else item)
        self._write_backups(updated[-self.backup_limit:])

    def _latest_existing_backup(self, backups: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        for backup in reversed(backups):
            raw_path = backup.get("path")
            if not raw_path:
                continue
            path = Path(str(raw_path)).expanduser()
            if path.is_file():
                return backup
        return None

    def _load_backups(self) -> List[Dict[str, Any]]:
        if not self.backups_path.exists():
            return []
        try:
            payload = json.loads(self.backups_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)][-self.backup_limit:]

    def _write_backups(self, backups: List[Dict[str, Any]]) -> None:
        try:
            self.backups_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self.backups_path.with_suffix(f"{self.backups_path.suffix}.tmp")
            tmp_path.write_text(json.dumps(backups[-self.backup_limit:], indent=2), encoding="utf-8")
            tmp_path.replace(self.backups_path)
        except OSError:
            return

    def _sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

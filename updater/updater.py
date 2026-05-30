from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import stat
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional


SHA256_RE = re.compile(r"\b[a-fA-F0-9]{64}\b")


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
                    "digest": asset.get("digest"),
                    "id": asset.get("id"),
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

        selected_asset = self._selected_release_asset(release, asset_url)
        if not selected_asset:
            return {"ok": False, "error": "No release binary asset was provided or discovered.", "release": release}

        download_url = str(selected_asset.get("browser_download_url") or "")
        if not download_url:
            return {"ok": False, "error": "Selected release asset has no download URL.", "release": release}

        checksum = self._resolve_expected_sha256(release, selected_asset, explicit_sha256=sha256)
        if not checksum.get("ok"):
            return {**checksum, "release": release, "asset": self._public_asset(selected_asset)}

        downloaded = self._download_asset(download_url, destination_dir=self.binary_path.parent)
        if not downloaded.get("ok"):
            return {**downloaded, "release": release, "asset": self._public_asset(selected_asset)}

        tmp_path = Path(str(downloaded["path"]))
        try:
            downloaded_size = tmp_path.stat().st_size
            actual_sha256 = self._sha256(tmp_path)
        except OSError as exc:
            tmp_path.unlink(missing_ok=True)
            return {"ok": False, "error": str(exc), "release": release, "asset": self._public_asset(selected_asset)}

        if downloaded_size <= 0:
            tmp_path.unlink(missing_ok=True)
            return {"ok": False, "error": "Downloaded release asset is empty.", "release": release, "asset": self._public_asset(selected_asset)}

        expected_sha256 = str(checksum["sha256"])
        if actual_sha256.lower() != expected_sha256.lower():
            tmp_path.unlink(missing_ok=True)
            return {
                "ok": False,
                "error": "SHA256 verification failed.",
                "expected_sha256": expected_sha256,
                "actual_sha256": actual_sha256,
                "checksum_source": checksum.get("source"),
                "release": release,
                "asset": self._public_asset(selected_asset),
            }

        installed = self._install_binary(tmp_path)
        if not installed.get("ok"):
            return {
                **installed,
                "sha256": actual_sha256,
                "checksum_source": checksum.get("source"),
                "release": release,
                "asset": self._public_asset(selected_asset),
            }

        return {
            "ok": True,
            "dry_run": False,
            "message": "DS4 binary updated. Restart DS4 to use the new binary.",
            "binary_path": str(self.binary_path),
            "asset": self._public_asset(selected_asset),
            "downloaded_bytes": downloaded_size,
            "backup_path": installed.get("backup_path"),
            "backup": installed.get("backup"),
            "backups": self._load_backups(),
            "sha256": actual_sha256,
            "checksum_source": checksum.get("source"),
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
        current_tmp = self.binary_path.with_name(f".{self.binary_path.name}.rollback-current.{self._timestamp()}.tmp")
        restore_tmp = self.binary_path.with_name(f".{self.binary_path.name}.rollback-restore.{self._timestamp()}.tmp")
        swapped_current = False
        try:
            self.binary_path.parent.mkdir(parents=True, exist_ok=True)
            if self.binary_path.exists():
                shutil.copy2(self.binary_path, current_tmp)
                swapped_current = True
            shutil.copy2(backup_path, restore_tmp)
            restore_tmp.chmod(self._executable_mode(backup_path))
            os.replace(restore_tmp, self.binary_path)
            if swapped_current:
                shutil.copy2(current_tmp, backup_path)
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
            current_tmp.unlink(missing_ok=True)
            restore_tmp.unlink(missing_ok=True)

        return {
            "ok": True,
            "message": "DS4 binary rolled back. Restart DS4 to use the restored binary.",
            "binary_path": str(self.binary_path),
            "backup_path": str(backup_path),
            "swapped_current": swapped_current,
            "backup": backup,
            "backups": self._load_backups(),
        }

    def _selected_release_asset(self, release: Dict[str, Any], asset_url: Optional[str]) -> Optional[Dict[str, Any]]:
        assets = [asset for asset in release.get("assets", []) if isinstance(asset, dict)]
        if asset_url:
            for asset in assets:
                if asset.get("browser_download_url") == asset_url or asset.get("name") == asset_url:
                    return dict(asset)
            return {
                "name": self._asset_name_from_url(asset_url),
                "browser_download_url": asset_url,
                "size": None,
                "content_type": None,
                "digest": None,
            }

        return self._first_binary_asset(release)

    def _first_binary_asset_url(self, release: Dict[str, Any]) -> Optional[str]:
        asset = self._first_binary_asset(release)
        return asset.get("browser_download_url") if asset else None

    def _first_binary_asset(self, release: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        candidates = []
        for asset in release.get("assets", []):
            if not isinstance(asset, dict):
                continue
            if not asset.get("browser_download_url") or self._is_checksum_asset(asset):
                continue
            score = self._binary_asset_score(asset)
            if score > 0:
                candidates.append((score, asset))

        if not candidates:
            non_checksum_assets = [
                asset
                for asset in release.get("assets", [])
                if isinstance(asset, dict)
                and asset.get("browser_download_url")
                and not self._is_checksum_asset(asset)
            ]
            if len(non_checksum_assets) == 1:
                return dict(non_checksum_assets[0])
            return None

        candidates.sort(key=lambda item: item[0], reverse=True)
        return dict(candidates[0][1])

    def _binary_asset_score(self, asset: Dict[str, Any]) -> int:
        name = str(asset.get("name") or "").lower()
        if not name or self._is_checksum_name(name):
            return 0

        score = 0
        if "ds4" in name:
            score += 50
        if "server" in name or "binary" in name:
            score += 12

        current_platform = sys.platform.lower()
        if current_platform == "darwin" and any(token in name for token in ("darwin", "macos", "osx", "apple")):
            score += 25
        elif current_platform.startswith("linux") and "linux" in name:
            score += 25

        machine = platform.machine().lower()
        machine_aliases = {
            "arm64": ("arm64", "aarch64"),
            "aarch64": ("arm64", "aarch64"),
            "x86_64": ("x86_64", "amd64"),
            "amd64": ("x86_64", "amd64"),
        }.get(machine, (machine,))
        if any(alias and alias in name for alias in machine_aliases):
            score += 15

        if any(name.endswith(ext) for ext in (".zip", ".tar.gz", ".tgz", ".gz")):
            score += 2
        return score

    def _resolve_expected_sha256(
        self,
        release: Dict[str, Any],
        asset: Dict[str, Any],
        *,
        explicit_sha256: Optional[str],
    ) -> Dict[str, Any]:
        if explicit_sha256:
            normalized = self._normalize_sha256(explicit_sha256)
            if not normalized:
                return {"ok": False, "error": "Invalid SHA256 checksum."}
            return {"ok": True, "sha256": normalized, "source": "request"}

        digest = str(asset.get("digest") or "")
        if digest.lower().startswith("sha256:"):
            normalized = self._normalize_sha256(digest.split(":", 1)[1])
            if normalized:
                return {"ok": True, "sha256": normalized, "source": "github_asset_digest"}

        checksum_asset = self._checksum_asset_for(release, asset)
        if not checksum_asset:
            return {"ok": False, "error": "No SHA256 checksum was provided or found in release assets."}

        checksum_url = str(checksum_asset.get("browser_download_url") or "")
        downloaded = self._download_text_asset(checksum_url)
        if not downloaded.get("ok"):
            return {**downloaded, "checksum_asset": self._public_asset(checksum_asset)}

        asset_name = str(asset.get("name") or self._asset_name_from_url(str(asset.get("browser_download_url") or "")))
        parsed = self._parse_sha256_text(str(downloaded.get("text") or ""), asset_name)
        if not parsed:
            return {
                "ok": False,
                "error": "Could not parse SHA256 checksum asset.",
                "checksum_asset": self._public_asset(checksum_asset),
            }

        return {
            "ok": True,
            "sha256": parsed,
            "source": f"release_asset:{checksum_asset.get('name')}",
            "checksum_asset": self._public_asset(checksum_asset),
        }

    def _checksum_asset_for(self, release: Dict[str, Any], asset: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        asset_name = str(asset.get("name") or self._asset_name_from_url(str(asset.get("browser_download_url") or ""))).lower()
        checksum_assets = [
            item
            for item in release.get("assets", [])
            if isinstance(item, dict) and item.get("browser_download_url") and self._is_checksum_asset(item)
        ]
        if not checksum_assets:
            return None

        scored = []
        for candidate in checksum_assets:
            name = str(candidate.get("name") or "").lower()
            score = 1
            if asset_name and asset_name in name:
                score += 20
            if asset_name and name.startswith(asset_name):
                score += 10
            if name in {f"{asset_name}.sha256", f"{asset_name}.sha256sum", f"{asset_name}.sha256.txt"}:
                score += 30
            if name in {"sha256sums", "sha256sums.txt", "checksums.txt"}:
                score += 5
            scored.append((score, candidate))

        if len(scored) == 1:
            return dict(scored[0][1])
        scored.sort(key=lambda item: item[0], reverse=True)
        return dict(scored[0][1]) if scored and scored[0][0] > 1 else None

    def _is_checksum_asset(self, asset: Dict[str, Any]) -> bool:
        return self._is_checksum_name(str(asset.get("name") or ""))

    def _is_checksum_name(self, name: str) -> bool:
        lowered = name.lower()
        return (
            lowered.endswith((".sha256", ".sha256sum", ".sha256.txt"))
            or lowered in {"sha256sums", "sha256sums.txt", "checksums.txt"}
            or "checksum" in lowered
        )

    def _normalize_sha256(self, value: str) -> Optional[str]:
        cleaned = str(value).strip().lower()
        if cleaned.startswith("sha256:"):
            cleaned = cleaned.split(":", 1)[1].strip()
        match = SHA256_RE.fullmatch(cleaned)
        return match.group(0).lower() if match else None

    def _parse_sha256_text(self, text: str, asset_name: str) -> Optional[str]:
        target = asset_name.lower()
        all_digests: List[str] = []
        target_digests: List[str] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            digests = [digest.lower() for digest in SHA256_RE.findall(line)]
            if not digests:
                continue
            all_digests.extend(digests)
            if not target or target in line.lower():
                target_digests.extend(digests)

        if target_digests:
            return target_digests[0]

        unique_digests = sorted(set(all_digests))
        if len(unique_digests) == 1:
            return unique_digests[0]
        return None

    def _download_asset(self, url: str, *, destination_dir: Optional[Path] = None) -> Dict[str, Any]:
        destination = destination_dir or Path(tempfile.gettempdir())
        request = urllib.request.Request(url, headers={"User-Agent": "ds4-dashboard"})
        try:
            destination.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(request, timeout=60.0) as response:
                fd, tmp_name = tempfile.mkstemp(prefix=f".{self.binary_path.name}.download.", dir=str(destination))
                with os.fdopen(fd, "wb") as handle:
                    shutil.copyfileobj(response, handle)
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "path": tmp_name}

    def _download_text_asset(self, url: str, *, max_bytes: int = 1024 * 1024) -> Dict[str, Any]:
        if not url:
            return {"ok": False, "error": "Checksum asset has no download URL."}
        request = urllib.request.Request(url, headers={"User-Agent": "ds4-dashboard"})
        try:
            with urllib.request.urlopen(request, timeout=15.0) as response:
                payload = response.read(max_bytes + 1)
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            return {"ok": False, "error": str(exc)}
        if len(payload) > max_bytes:
            return {"ok": False, "error": "Checksum asset is too large."}
        return {"ok": True, "text": payload.decode("utf-8", errors="replace")}

    def _install_binary(self, tmp_path: Path) -> Dict[str, Any]:
        backup_path = self._backup_path()
        backup_created = False
        rollback_error = None
        try:
            self.binary_path.parent.mkdir(parents=True, exist_ok=True)
            if self.binary_path.exists():
                shutil.copy2(self.binary_path, backup_path)
                backup_created = True
                install_mode = self._executable_mode(self.binary_path)
            else:
                install_mode = 0o755
            tmp_path.chmod(install_mode)
            os.replace(tmp_path, self.binary_path)
        except OSError as exc:
            if backup_created and backup_path.exists():
                try:
                    shutil.copy2(backup_path, self.binary_path)
                    self.binary_path.chmod(self._executable_mode(backup_path))
                except OSError as restore_exc:
                    rollback_error = str(restore_exc)
            tmp_path.unlink(missing_ok=True)
            return {
                "ok": False,
                "error": f"Binary swap failed: {exc}",
                "binary_path": str(self.binary_path),
                "backup_path": str(backup_path) if backup_created else None,
                "rollback_performed": backup_created and rollback_error is None,
                "rollback_error": rollback_error,
            }

        backup_entry = self._record_backup(backup_path) if backup_created else None
        return {
            "ok": True,
            "binary_path": str(self.binary_path),
            "backup_path": str(backup_path) if backup_created else None,
            "backup": backup_entry,
            "rollback_performed": False,
        }

    def _asset_name_from_url(self, url: str) -> str:
        parsed = urllib.parse.urlparse(url)
        name = Path(urllib.parse.unquote(parsed.path)).name
        return name or "release-asset"

    def _public_asset(self, asset: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "name": asset.get("name"),
            "size": asset.get("size"),
            "browser_download_url": asset.get("browser_download_url"),
            "content_type": asset.get("content_type"),
            "digest": asset.get("digest"),
        }

    def _executable_mode(self, path: Path) -> int:
        try:
            mode = stat.S_IMODE(path.stat().st_mode)
        except OSError:
            mode = 0o755
        return mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH

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

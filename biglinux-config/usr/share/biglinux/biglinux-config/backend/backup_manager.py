"""Backup and restore dotfiles via .tar.gz archives.

Handles:
- Exporting selected app configs to a compressed archive
- Importing configs from a previously exported archive
- Optional full-directory copy mode (includes all contents recursively)
- Manifest with metadata for safe restore
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tarfile
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from data.app_registry import AppEntry

logger = logging.getLogger("biglinux-config")

MANIFEST_NAME = "biglinux-backup-manifest.json"
BACKUP_VERSION = 1


@dataclass
class BackupResult:
    success: bool
    message: str
    archive_path: str
    app_count: int
    total_size: int


@dataclass
class RestoreFromBackupResult:
    success: bool
    message: str
    restored_apps: list[str]
    skipped_apps: list[str]


def _safe_path(member_name: str, dest: str) -> str | None:
    """Validate tar member path to prevent path traversal attacks."""
    target = os.path.realpath(os.path.join(dest, member_name))
    if not target.startswith(os.path.realpath(dest) + os.sep) and target != os.path.realpath(dest):
        return None
    return target


class _ExportCancelled(Exception):
    """Raised when the user cancels an export operation."""


def export_backup(
    entries: list[AppEntry],
    archive_path: str,
    full_directory: bool = False,
    progress_callback: Callable[[int, int, str]] | None = None,
    cancel_event: threading.Event | None = None,
) -> BackupResult:
    """Create a .tar.gz archive containing dotfiles for selected apps.

    Args:
        entries: List of AppEntry objects to back up.
        archive_path: Destination path for the .tar.gz file.
        full_directory: If True, include entire directories recursively.
                       If False, include only direct config files/folders listed.
        progress_callback: Optional callable(current, total, app_name) for progress updates.
        cancel_event: Optional threading.Event; if set, the export is cancelled.
    """
    home = os.path.expanduser("~")
    manifest = {
        "version": BACKUP_VERSION,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "hostname": os.uname().nodename,
        "full_directory": full_directory,
        "apps": [],
    }
    total_size = 0
    app_count = 0

    total_entries = len(entries)

    try:
        with tarfile.open(archive_path, "w:gz") as tar:
            for idx, entry in enumerate(entries):
                if cancel_event and cancel_event.is_set():
                    raise _ExportCancelled()

                if progress_callback:
                    progress_callback(idx, total_entries, entry.name)

                app_paths_added: list[str] = []

                for raw_path in entry.config_paths:
                    expanded = os.path.expanduser(raw_path)

                    if not os.path.exists(expanded):
                        continue

                    real = os.path.realpath(expanded)
                    if not real.startswith(home + os.sep) and real != home:
                        logger.warning("Skipping path outside HOME: %s", expanded)
                        continue

                    # Compute archive-internal path relative to HOME
                    rel_path = os.path.relpath(expanded, home)

                    if os.path.isdir(expanded):
                        if full_directory:
                            # Walk entire directory tree
                            for dirpath, dirnames, filenames in os.walk(expanded):
                                dir_rel = os.path.relpath(dirpath, home)
                                tar.add(dirpath, arcname=dir_rel, recursive=False)
                                for fname in filenames:
                                    fpath = os.path.join(dirpath, fname)
                                    f_rel = os.path.relpath(fpath, home)
                                    try:
                                        fsize = os.path.getsize(fpath)
                                        total_size += fsize
                                    except OSError:
                                        pass
                                    tar.add(fpath, arcname=f_rel)
                        else:
                            tar.add(expanded, arcname=rel_path)
                            for dirpath, _, filenames in os.walk(expanded):
                                for fname in filenames:
                                    try:
                                        total_size += os.path.getsize(
                                            os.path.join(dirpath, fname)
                                        )
                                    except OSError:
                                        pass

                    elif os.path.isfile(expanded):
                        try:
                            total_size += os.path.getsize(expanded)
                        except OSError:
                            pass
                        tar.add(expanded, arcname=rel_path)

                    app_paths_added.append(rel_path)

                if app_paths_added:
                    app_count += 1
                    manifest["apps"].append({
                        "app_id": entry.app_id,
                        "name": entry.name,
                        "paths": app_paths_added,
                    })

            # Write manifest as the last entry
            manifest_json = json.dumps(manifest, indent=2).encode("utf-8")
            import io
            info = tarfile.TarInfo(name=MANIFEST_NAME)
            info.size = len(manifest_json)
            info.mtime = int(time.time())
            tar.addfile(info, io.BytesIO(manifest_json))

        logger.info(
            "Backup created: %s (%d apps, %d bytes)",
            archive_path, app_count, total_size,
        )
        return BackupResult(
            success=True,
            message="",
            archive_path=archive_path,
            app_count=app_count,
            total_size=total_size,
        )

    except _ExportCancelled:
        logger.info("Export cancelled by user")
        try:
            os.unlink(archive_path)
        except OSError:
            pass
        return BackupResult(
            success=False,
            message="cancelled",
            archive_path=archive_path,
            app_count=0,
            total_size=0,
        )

    except Exception as exc:
        logger.error("Backup failed: %s", exc)
        # Clean up partial file
        try:
            os.unlink(archive_path)
        except OSError:
            pass
        return BackupResult(
            success=False,
            message=str(exc),
            archive_path=archive_path,
            app_count=0,
            total_size=0,
        )


def read_backup_manifest(archive_path: str) -> dict | None:
    """Read and return the manifest from a backup archive, or None on error."""
    try:
        with tarfile.open(archive_path, "r:gz") as tar:
            try:
                member = tar.getmember(MANIFEST_NAME)
            except KeyError:
                return None
            f = tar.extractfile(member)
            if f is None:
                return None
            return json.loads(f.read().decode("utf-8"))
    except (tarfile.TarError, json.JSONDecodeError, OSError):
        return None


def import_backup(
    archive_path: str,
    selected_app_ids: set[str] | None = None,
    progress_callback: Callable[[int, int, str]] | None = None,
    cancel_event: threading.Event | None = None,
) -> RestoreFromBackupResult:
    """Import dotfiles from a backup archive into $HOME.

    Uses streaming iteration (tar.next()) instead of tar.getmembers()
    for much better performance with large archives.  Progress is
    reported based on the compressed byte offset vs total file size.

    Args:
        archive_path: Path to the .tar.gz backup file.
        selected_app_ids: If set, only restore these app_ids.
                         If None, restore everything in the archive.
        progress_callback: Optional callable(current, total, app_name) for progress updates.
        cancel_event: Optional threading.Event; if set, the import is cancelled.
    """
    home = os.path.expanduser("~")
    restored: list[str] = []
    skipped: list[str] = []

    try:
        manifest = read_backup_manifest(archive_path)
        if manifest is None:
            return RestoreFromBackupResult(
                success=False,
                message="Invalid backup: no manifest found.",
                restored_apps=[],
                skipped_apps=[],
            )

        # Build set of paths to restore based on selected apps
        allowed_paths: set[str] | None = None
        apps_to_restore: list[dict] = []
        if selected_app_ids is not None:
            allowed_paths = set()
            for app_info in manifest.get("apps", []):
                if app_info["app_id"] in selected_app_ids:
                    apps_to_restore.append(app_info)
                    for p in app_info["paths"]:
                        allowed_paths.add(p)
                else:
                    skipped.append(app_info["name"])
        else:
            apps_to_restore = manifest.get("apps", [])

        # Build a mapping: path prefix → app name for progress tracking
        path_to_app: dict[str, str] = {}
        for app_info in apps_to_restore:
            for p in app_info["paths"]:
                path_to_app[p] = app_info["name"]

        total_bytes = os.path.getsize(archive_path)
        current_app_name = ""
        member_count = 0

        with tarfile.open(archive_path, "r:gz") as tar:
            member = tar.next()
            while member is not None:
                if cancel_event and cancel_event.is_set():
                    return RestoreFromBackupResult(
                        success=False,
                        message="cancelled",
                        restored_apps=restored,
                        skipped_apps=skipped,
                    )

                if member.name == MANIFEST_NAME:
                    member = tar.next()
                    continue

                # Determine which app this member belongs to
                for prefix, app_name in path_to_app.items():
                    if member.name == prefix or member.name.startswith(prefix + "/"):
                        if app_name != current_app_name:
                            current_app_name = app_name
                        break

                # Report progress based on compressed offset
                member_count += 1
                if progress_callback and member_count % 20 == 0:
                    offset = tar.fileobj.tell() if hasattr(tar.fileobj, "tell") else 0
                    progress_callback(offset, total_bytes, current_app_name)

                # Validate path safety
                target = _safe_path(member.name, home)
                if target is None:
                    logger.warning("Skipping unsafe path: %s", member.name)
                    member = tar.next()
                    continue

                # Check if this path is in allowed set
                if allowed_paths is not None:
                    belongs = any(
                        member.name == ap or member.name.startswith(ap + "/")
                        for ap in allowed_paths
                    )
                    if not belongs:
                        member = tar.next()
                        continue

                # Remove existing before extracting
                if os.path.exists(target):
                    if os.path.isdir(target) and not os.path.islink(target):
                        if member.isdir():
                            shutil.rmtree(target, ignore_errors=True)
                    elif os.path.isfile(target) or os.path.islink(target):
                        os.unlink(target)

                # Extract safely
                if member.isdir():
                    os.makedirs(target, exist_ok=True)
                elif member.isfile():
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with tar.extractfile(member) as src:
                        if src is not None:
                            with open(target, "wb") as dst:
                                shutil.copyfileobj(src, dst)
                    mode = member.mode & 0o0777
                    os.chmod(target, mode)

                member = tar.next()

        # Final progress at 100%
        if progress_callback:
            progress_callback(total_bytes, total_bytes, current_app_name)

        # Build restored app list
        for app_info in apps_to_restore:
            restored.append(app_info["name"])

        logger.info(
            "Backup imported: %s (restored=%s, skipped=%s)",
            archive_path, restored, skipped,
        )
        return RestoreFromBackupResult(
            success=True,
            message="",
            restored_apps=restored,
            skipped_apps=skipped,
        )

    except Exception as exc:
        logger.error("Import failed: %s", exc)
        return RestoreFromBackupResult(
            success=False,
            message=str(exc),
            restored_apps=restored,
            skipped_apps=skipped,
        )


def get_default_backup_name() -> str:
    """Generate a default backup filename with timestamp."""
    ts = time.strftime("%Y%m%d_%H%M%S")
    return f"big-restore-dotfiles-{ts}.tar.gz"

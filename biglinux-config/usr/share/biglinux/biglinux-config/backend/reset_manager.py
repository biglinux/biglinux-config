"""Manage application configuration reset operations.

Handles:
- Checking if an app is running
- Killing a running app (with user consent)
- Removing configuration directories
- Restoring from /etc/skel/ (BigLinux defaults)
- Logging operations
"""

from __future__ import annotations

import glob
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

from data.app_registry import AppEntry

logger = logging.getLogger("biglinux-config")

STATE_DIR = os.path.expanduser("~/.local/state/biglinux-config")
LOG_FILE = os.path.join(STATE_DIR, "operations.log")


class ResetMode(Enum):
    PROGRAM_DEFAULT = auto()  # remove dotfiles (app recreates defaults)
    BIGLINUX_DEFAULT = auto()  # remove + copy from /etc/skel/


@dataclass
class ResetResult:
    success: bool
    message: str
    app_id: str
    mode: ResetMode
    removed_paths: list[str]
    restored_paths: list[str]


def _ensure_log_dir() -> None:
    os.makedirs(STATE_DIR, exist_ok=True)


def _setup_logger() -> None:
    _ensure_log_dir()
    handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    if not logger.handlers:
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)


_setup_logger()


def get_running_pids(entry: AppEntry) -> list[int]:
    """Return PIDs of processes matching the app, or empty list."""
    name = entry.process_name or os.path.basename(entry.binary)
    try:
        result = subprocess.run(
            ["pgrep", "-f", name],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return [int(p) for p in result.stdout.strip().split() if p.isdigit()]
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass
    return []


def kill_app(entry: AppEntry) -> bool:
    """Terminate all instances of the app. Returns True on success."""
    pids = get_running_pids(entry)
    if not pids:
        return True
    try:
        for pid in pids:
            subprocess.run(["kill", str(pid)], timeout=5)
        # Give it a moment, then force-kill survivors
        subprocess.run(["sleep", "1"], timeout=3)
        remaining = get_running_pids(entry)
        for pid in remaining:
            subprocess.run(["kill", "-9", str(pid)], timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def reset_app(entry: AppEntry, mode: ResetMode) -> ResetResult:
    """Execute a full config reset for the given app.

    This function is meant to be called from a worker thread
    (never from the UI thread).
    """
    removed: list[str] = []
    restored: list[str] = []
    home = os.path.expanduser("~")

    try:
        # Remove config paths
        for raw_path in entry.config_paths:
            expanded = os.path.expanduser(raw_path)

            # Support glob patterns (e.g., ~/.config/krita*)
            targets = glob.glob(expanded) if ("*" in expanded or "?" in expanded) else [expanded]

            for target in targets:
                real = os.path.realpath(target)

                # Security: refuse to remove anything outside $HOME
                if not real.startswith(home + os.sep) and real != home:
                    logger.warning("Skipping path outside HOME: %s", target)
                    continue

                # Don't follow symlinks to outside HOME
                if os.path.islink(target):
                    link_target = os.path.realpath(target)
                    if not link_target.startswith(home + os.sep):
                        logger.warning("Skipping symlink pointing outside HOME: %s -> %s", target, link_target)
                        os.unlink(target)
                        removed.append(target)
                        continue

                if os.path.isdir(target):
                    shutil.rmtree(target, ignore_errors=True)
                    removed.append(target)
                elif os.path.isfile(target):
                    os.remove(target)
                    removed.append(target)

        # Restore from skel if requested
        if mode == ResetMode.BIGLINUX_DEFAULT and entry.skel_paths:
            for skel_path in entry.skel_paths:
                if not os.path.exists(skel_path):
                    continue

                # Compute destination: /etc/skel/.config/foo -> ~/.config/foo
                rel = os.path.relpath(skel_path, "/etc/skel")
                dest = os.path.join(home, rel)

                dest_parent = os.path.dirname(dest)
                os.makedirs(dest_parent, exist_ok=True)

                if os.path.isdir(skel_path):
                    if os.path.exists(dest):
                        shutil.rmtree(dest, ignore_errors=True)
                    shutil.copytree(skel_path, dest, symlinks=True)
                else:
                    shutil.copy2(skel_path, dest)

                restored.append(dest)

        logger.info(
            "Reset %s (%s): removed=%s restored=%s",
            entry.app_id,
            mode.name,
            removed,
            restored,
        )

        return ResetResult(
            success=True,
            message="",
            app_id=entry.app_id,
            mode=mode,
            removed_paths=removed,
            restored_paths=restored,
        )

    except Exception as exc:
        logger.error("Reset failed for %s: %s", entry.app_id, exc)
        return ResetResult(
            success=False,
            message=str(exc),
            app_id=entry.app_id,
            mode=mode,
            removed_paths=removed,
            restored_paths=restored,
        )


def get_config_size(entry: AppEntry) -> int:
    """Return total size in bytes of existing config paths."""
    total = 0
    for raw_path in entry.config_paths:
        expanded = os.path.expanduser(raw_path)
        targets = glob.glob(expanded) if ("*" in expanded or "?" in expanded) else [expanded]
        for target in targets:
            if os.path.isdir(target):
                for dirpath, _dirnames, filenames in os.walk(target):
                    for f in filenames:
                        try:
                            total += os.path.getsize(os.path.join(dirpath, f))
                        except OSError:
                            pass
            elif os.path.isfile(target):
                try:
                    total += os.path.getsize(target)
                except OSError:
                    pass
    return total


def has_skel(entry: AppEntry) -> bool:
    """Check if any skel paths actually exist on disk."""
    return any(os.path.exists(p) for p in entry.skel_paths)


def has_config(entry: AppEntry) -> bool:
    """Check if any config paths actually exist on disk."""
    for raw_path in entry.config_paths:
        expanded = os.path.expanduser(raw_path)
        targets = glob.glob(expanded) if ("*" in expanded or "?" in expanded) else [expanded]
        for target in targets:
            if os.path.exists(target):
                return True
    return False


def format_size(size_bytes: int) -> str:
    """Human-readable file size."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

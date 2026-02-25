"""Detect which registered applications are actually installed."""

from __future__ import annotations

import os
import shutil

from data.app_registry import APP_REGISTRY, FAVORITE_IDS, AppEntry


def get_installed_apps() -> list[AppEntry]:
    """Return only the AppEntry items whose binary exists on disk."""
    installed: list[AppEntry] = []
    for entry in APP_REGISTRY:
        if _binary_exists(entry.binary):
            installed.append(entry)
    return installed


def get_favorites(installed: list[AppEntry]) -> list[AppEntry]:
    """Filter installed apps to only those in the favorites set."""
    return [e for e in installed if e.app_id in FAVORITE_IDS]


def is_installed(entry: AppEntry) -> bool:
    return _binary_exists(entry.binary)


def _binary_exists(binary: str) -> bool:
    """Check if a binary is available (absolute path or in PATH)."""
    if os.path.isabs(binary):
        return os.path.isfile(binary) and os.access(binary, os.X_OK)
    return shutil.which(binary) is not None

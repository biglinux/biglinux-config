"""Detect which registered applications are actually installed."""

from __future__ import annotations

import os
import subprocess
import shutil

import gi
gi.require_version("Gio", "2.0")
from gi.repository import Gio

from data.app_registry import (
    APP_REGISTRY,
    FAVORITE_MIME_SLOTS,
    STATIC_FAVORITE_IDS,
    AppEntry,
)

# Cache for localized names looked up from .desktop files
_name_cache: dict[str, str] = {}
_desktop_map: dict[str, Gio.DesktopAppInfo] | None = None


def _build_desktop_map() -> dict[str, Gio.DesktopAppInfo]:
    """Build a map from desktop ID components and binary basenames.

    Two-pass to ensure desktop ID components take priority over executable basenames.
    """
    all_infos = [
        ai for ai in Gio.AppInfo.get_all()
        if isinstance(ai, Gio.DesktopAppInfo)
    ]
    result: dict[str, Gio.DesktopAppInfo] = {}

    # Pass 1: index by desktop ID stem and last component (higher priority)
    for app_info in all_infos:
        desktop_id = app_info.get_id() or ""
        stem = desktop_id.removesuffix(".desktop") if desktop_id else ""
        if stem:
            key = stem.lower()
            result[key] = app_info
            last_part = key.rsplit(".", 1)[-1]
            if last_part not in result:
                result[last_part] = app_info

    # Pass 2: index by executable basename (only if not already mapped)
    for app_info in all_infos:
        executable = app_info.get_executable()
        if executable:
            basename = os.path.basename(executable).lower()
            if basename not in result:
                result[basename] = app_info

    return result


def get_localized_name(entry: AppEntry) -> str:
    """Return the localized display name from the .desktop file, falling back to entry.name."""
    if entry.app_id in _name_cache:
        return _name_cache[entry.app_id]

    global _desktop_map
    if _desktop_map is None:
        _desktop_map = _build_desktop_map()

    info = None

    # Handle Flatpak apps: app_id is "flatpak-org.example.App"
    real_id = entry.app_id
    if real_id.startswith("flatpak-"):
        real_id = real_id[len("flatpak-"):]

    # Try direct desktop ID
    for candidate in (f"{real_id}.desktop", f"{real_id}-startcenter.desktop"):
        try:
            info = Gio.DesktopAppInfo.new(candidate)
            if info:
                break
        except TypeError:
            continue

    # Try lookup by real_id in the map
    if not info:
        info = _desktop_map.get(real_id.lower())

    # Try lookup by binary basename (skip generic binaries like "flatpak")
    if not info and entry.binary not in ("flatpak",):
        binary_name = os.path.basename(entry.binary).lower()
        info = _desktop_map.get(binary_name)

    if info:
        name = info.get_display_name() or info.get_name()
        if name:
            # Keep "(Flatpak)" suffix for Flatpak apps
            if entry.app_id.startswith("flatpak-"):
                name = f"{name} (Flatpak)"
            _name_cache[entry.app_id] = name
            return name

    _name_cache[entry.app_id] = entry.name
    return entry.name


def get_installed_apps() -> list[AppEntry]:
    """Return only the AppEntry items whose binary exists on disk."""
    installed: list[AppEntry] = []
    for entry in APP_REGISTRY:
        if _binary_exists(entry.binary):
            installed.append(entry)
    return installed


def _get_default_desktop_id(mime_type: str) -> str | None:
    """Return the .desktop filename for the system default handler of *mime_type*."""
    try:
        result = subprocess.run(
            ["xdg-mime", "query", "default", mime_type],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def _desktop_id_to_app_id(desktop_id: str) -> str:
    """Convert a .desktop filename to a comparable app_id.

    'org.kde.kate.desktop' → 'org.kde.kate'
    'firefox.desktop'      → 'firefox'
    """
    return desktop_id.removesuffix(".desktop")


def _find_app_by_desktop_id(desktop_id: str, installed: list[AppEntry]) -> AppEntry | None:
    """Find an installed app matching *desktop_id*.

    Matches against:
      - exact app_id (native entries)
      - flatpak-<desktop_stem> (flatpak entries)
      - last component of desktop_stem vs app_id (case-insensitive)
    """
    stem = _desktop_id_to_app_id(desktop_id)
    stem_lower = stem.lower()

    for e in installed:
        # Native match: firefox == firefox, or okularApplication_pdf == okularApplication_pdf
        if e.app_id.lower() == stem_lower:
            return e
        # Flatpak match: flatpak-org.gimp.GIMP vs org.gimp.GIMP
        if e.app_id.startswith("flatpak-"):
            flatpak_stem = e.app_id.removeprefix("flatpak-").lower()
            if flatpak_stem == stem_lower:
                return e

    # Fallback: match last component (e.g. 'kate' from 'org.kde.kate')
    last = stem_lower.rsplit(".", 1)[-1]
    for e in installed:
        eid = e.app_id.lower()
        if eid == last:
            return e
        if eid.startswith("flatpak-"):
            fp_last = eid.removeprefix("flatpak-").rsplit(".", 1)[-1]
            if fp_last == last:
                return e

    # Fallback: stem starts with app_id (e.g. 'okularapplication_pdf' starts with 'okular')
    for e in installed:
        eid = e.app_id.lower()
        if last.startswith(eid) or stem_lower.startswith(eid):
            return e

    return None


def get_favorites(installed: list[AppEntry]) -> list[AppEntry]:
    """Build the favorites list using system defaults + static favorites.

    For each MIME slot (browser, PDF viewer, etc.), detect the system default
    app and include it if it's in the installed list.
    Static favorites (GIMP, Lutris, Steam, Dolphin, Spectacle) are always
    included if installed.
    """
    result: list[AppEntry] = []
    seen: set[str] = set()

    # 1. System default apps for each MIME slot
    for mime_type, _slot_name in FAVORITE_MIME_SLOTS:
        desktop_id = _get_default_desktop_id(mime_type)
        if not desktop_id:
            continue
        entry = _find_app_by_desktop_id(desktop_id, installed)
        if entry and entry.app_id not in seen:
            result.append(entry)
            seen.add(entry.app_id)

    # 2. Static favorites
    for e in installed:
        if e.app_id in STATIC_FAVORITE_IDS and e.app_id not in seen:
            result.append(e)
            seen.add(e.app_id)
        elif e.app_id.startswith("flatpak-"):
            last = e.app_id.removeprefix("flatpak-").rsplit(".", 1)[-1].lower()
            if last in STATIC_FAVORITE_IDS and e.app_id not in seen:
                result.append(e)
                seen.add(e.app_id)

    return result


def is_installed(entry: AppEntry) -> bool:
    return _binary_exists(entry.binary)


def _binary_exists(binary: str) -> bool:
    """Check if a binary is available (absolute path or in PATH)."""
    if os.path.isabs(binary):
        return os.path.isfile(binary) and os.access(binary, os.X_OK)
    return shutil.which(binary) is not None

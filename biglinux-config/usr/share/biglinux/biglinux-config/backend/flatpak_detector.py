"""Detect Flatpak applications installed on the system."""

from __future__ import annotations

import os
import subprocess

from data.app_registry import AppEntry


def get_installed_flatpaks() -> list[AppEntry]:
    """Return AppEntry instances for every Flatpak whose config dir exists."""
    try:
        result = subprocess.run(
            [
                "flatpak", "list", "--app",
                "--columns=application,name,origin",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    if result.returncode != 0:
        return []

    apps: list[AppEntry] = []
    seen: set[str] = set()

    for line in result.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        app_id, name = parts[0].strip(), parts[1].strip()
        if not app_id or app_id in seen:
            continue
        seen.add(app_id)

        config_path = os.path.expanduser(f"~/.var/app/{app_id}")
        if not os.path.isdir(config_path):
            continue

        icon = _resolve_flatpak_icon(app_id)

        apps.append(AppEntry(
            app_id=f"flatpak-{app_id}",
            name=f"{name} (Flatpak)",
            icon=icon,
            binary="flatpak",
            category="flatpak",
            config_paths=[config_path],
            process_name=app_id,
        ))

    return apps


def _resolve_flatpak_icon(app_id: str) -> str:
    """Try to find an icon for a Flatpak app from its exports."""
    for base in (
        "/var/lib/flatpak/exports/share/icons",
        os.path.expanduser("~/.local/share/flatpak/exports/share/icons"),
    ):
        for theme in ("hicolor",):
            for size in ("scalable", "256x256", "128x128", "64x64", "48x48"):
                category = "apps"
                for ext in (".svg", ".png"):
                    path = os.path.join(base, theme, size, category, app_id + ext)
                    if os.path.isfile(path):
                        return path

    # Fallback: use the app_id as icon-name — GTK icon theme may resolve it
    return app_id

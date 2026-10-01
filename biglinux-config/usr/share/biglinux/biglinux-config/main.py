#!/usr/bin/env python3
"""BigLinux Config — launch as the desktop user with supported API versions."""
from __future__ import annotations

import os
import sys
from pathlib import Path

MIN_PYTHON = (3, 12)
MIN_GTK = (4, 12, 0)
MIN_ADWAITA = (1, 6, 0)


def _version(module) -> tuple[int, int, int]:
    return (module.get_major_version(), module.get_minor_version(),
            module.get_micro_version())


def main() -> int:
    if sys.version_info < MIN_PYTHON:
        print("BigLinux Config requires Python 3.12 or newer.", file=sys.stderr)
        return 1
    if os.geteuid() == 0:
        print("Run BigLinux Config as your desktop user, not with sudo/root.", file=sys.stderr)
        return 1
    try:
        import gi
        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw, Gtk
    except (ImportError, ValueError) as exc:
        print(f"Install PyGObject, GTK4 and libadwaita: {exc}", file=sys.stderr)
        return 1
    if _version(Gtk) < MIN_GTK or _version(Adw) < MIN_ADWAITA:
        print("BigLinux Config requires GTK >= 4.12 and libadwaita >= 1.6.", file=sys.stderr)
        return 1
    # The installed launcher uses -I: add only this trusted application tree,
    # not the caller's cwd, PYTHONPATH or user-site packages.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from ui.application import BigConfigApp
    return BigConfigApp(application_id="com.biglinux.config").run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())

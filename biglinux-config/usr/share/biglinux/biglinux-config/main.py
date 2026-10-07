#!/usr/bin/env python3
"""BigLinux Config — launch as the desktop user with supported API versions."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# The installed launcher uses -I: add only this trusted application tree,
# not the caller's cwd, PYTHONPATH or user-site packages.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from i18n import _  # noqa: E402
from ui.metadata import APP_NAME, APP_VERSION  # noqa: E402

MIN_PYTHON = (3, 12)
MIN_GTK = (4, 12, 0)
MIN_ADWAITA = (1, 6, 0)
APPLICATION_ID = "com.biglinux.config"


def _version(module) -> tuple[int, int, int]:
    return (module.get_major_version(), module.get_minor_version(),
            module.get_micro_version())


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    if "--version" in argv[1:]:
        print(f"{APP_NAME} {APP_VERSION}")
        return 0
    if sys.version_info < MIN_PYTHON:
        print(_("Restore Settings requires Python 3.12 or newer."), file=sys.stderr)
        return 1
    if os.geteuid() == 0:
        print(_("Run Restore Settings as your desktop user, not with sudo or as root."),
              file=sys.stderr)
        return 1
    try:
        import gi
        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw, Gtk
    except (ImportError, ValueError) as exc:
        print(_("Install PyGObject, GTK 4 and libadwaita: %s") % exc, file=sys.stderr)
        return 1
    if _version(Gtk) < MIN_GTK or _version(Adw) < MIN_ADWAITA:
        print(_("Restore Settings requires GTK 4.12 and libadwaita 1.6 or newer."),
              file=sys.stderr)
        return 1
    from ui.application import BigConfigApp
    return BigConfigApp(application_id=APPLICATION_ID).run(argv)


if __name__ == "__main__":
    sys.exit(main())

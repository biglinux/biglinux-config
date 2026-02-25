#!/usr/bin/env python3
"""BigLinux Config — Restore application settings to defaults."""

import sys
import os
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

# Ensure module imports resolve from the app directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui.application import BigConfigApp


def main() -> int:
    app = BigConfigApp(application_id="com.biglinux.config")
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())

"""About dialog for Restore Settings."""

from __future__ import annotations

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk

from utils import _

APP_NAME = "Restore Settings"
APP_VERSION = "1.0.0"
APP_ICON = "restore-settings"
APP_DEVELOPER = "BigLinux Team"
APP_WEBSITE = "https://github.com/ruscher/biglinux-config"
APP_ISSUE_URL = f"{APP_WEBSITE}/issues"
APP_SUPPORT_URL = f"{APP_WEBSITE}#troubleshooting"

APP_AUTHORS = (
    "Bruno Gonçalves <bigbruno@gmail.com>",
    "Rafael Ruscher <rruscher@gmail.com>",
)


def create_about_dialog() -> Adw.AboutDialog:
    """Create the standard Adwaita about dialog."""
    dialog = Adw.AboutDialog.new()
    dialog.set_application_name(_(APP_NAME))
    dialog.set_version(APP_VERSION)
    dialog.set_application_icon(APP_ICON)
    dialog.set_developer_name(APP_DEVELOPER)
    dialog.set_website(APP_WEBSITE)
    dialog.set_issue_url(APP_ISSUE_URL)
    dialog.set_support_url(APP_SUPPORT_URL)
    dialog.set_license_type(Gtk.License.GPL_3_0)
    dialog.set_developers(list(APP_AUTHORS))
    dialog.set_comments(
        _(
            "Restore, back up, and manage application settings on BigLinux.\n\n"
            "Restore Settings detects supported native and Flatpak applications, "
            "restores either BigLinux defaults or the application's own defaults, "
            "and exports or imports selected settings using compressed backups "
            "with integrity checks and rollback protection."
        )
    )
    return dialog


def show_about_dialog(parent: Gtk.Window) -> None:
    """Present the standard Adwaita about dialog."""
    create_about_dialog().present(parent)

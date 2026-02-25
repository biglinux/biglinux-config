"""About dialog for Restore Settings."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from utils import _

APP_NAME = "Restore Settings"
APP_VERSION = "1.0.0"
APP_DEVELOPER = "BigLinux Team"
APP_WEBSITE = "https://github.com/biglinux/biglinux-config"
APP_ISSUE_URL = f"{APP_WEBSITE}/issues"


def show_about_dialog(parent: Adw.ApplicationWindow) -> None:
    about = Adw.AboutDialog.new()
    about.set_application_name(_(APP_NAME))
    about.set_version(APP_VERSION)
    about.set_developer_name(APP_DEVELOPER)
    about.set_license_type(Gtk.License.GPL_3_0)
    about.set_website(APP_WEBSITE)
    about.set_issue_url(APP_ISSUE_URL)
    about.set_application_icon("restore-settings")

    about.add_credit_section(
        _("Legal"),
        [
            _(
                "The GPL-3.0 license applies to this configuration interface."
            )
        ],
    )

    about.add_credit_section(
        _("Technologies used"),
        [
            "GTK4 / Libadwaita",
            "Python / PyGObject",
            "BigLinux Project",
        ],
    )

    about.present(parent)

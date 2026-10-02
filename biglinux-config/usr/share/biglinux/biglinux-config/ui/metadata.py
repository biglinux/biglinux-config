"""Declarative product metadata; safe to import without GTK."""
from i18n import _

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


WELCOME_FEATURES = (
    (
        "restore-default-symbolic",
        _("Restore BigLinux Defaults"),
        _(
            "Restore the settings provided by BigLinux\n"
            "without changing unrelated files"
        ),
    ),
    (
        "edit-undo-symbolic",
        _("Restore Program Defaults"),
        _("Remove custom settings so the app\ncan recreate its original defaults"),
    ),
    (
        "document-save-symbolic",
        _("Export Settings"),
        _("Back up selected applications\nto a compressed .tar.gz archive"),
    ),
    (
        "document-open-symbolic",
        _("Import Settings"),
        _("Restore selected applications from\na previously exported backup"),
    ),
    (
        "folder-symbolic",
        _("Full Directory Backup"),
        _("Optionally include cache files\ninside registered application folders"),
    ),
    (
        "folder-flatpak-symbolic",
        _("Native & Flatpak Apps"),
        _("Manage settings for installed native\nand Flatpak applications together"),
    ),
    (
        "system-search-symbolic",
        _("Search & Favorites"),
        _("Find supported applications quickly\nand keep a personal favorites list"),
    ),
    (
        "preferences-system-symbolic",
        _("Desktop Settings"),
        _(
            "Handle registered GSettings/dconf data\n"
            "without touching unrelated preferences"
        ),
    ),
)

"""Internationalization utilities."""

import gettext
import locale
import os

DOMAIN = "biglinux-config"
LOCALE_DIR = "/usr/share/locale"

# Prefer the compiled catalogs shipped in the checkout during development.
# In the installed layout the same relative path resolves to /usr/share/locale.
_dev_locale = os.path.join(
    os.path.dirname(__file__),
    "..",
    "..",
    "..",
    "..",
    "..",
    "usr",
    "share",
    "locale",
)
if os.path.isdir(_dev_locale):
    LOCALE_DIR = os.path.abspath(_dev_locale)

try:
    locale.setlocale(locale.LC_ALL, "")
except locale.Error:
    pass

_translations = gettext.translation(DOMAIN, localedir=LOCALE_DIR, fallback=True)
_ = _translations.gettext
ngettext = _translations.ngettext


def set_label(widget, label: str) -> None:
    """Set GTK4 accessible label via Gtk.AccessibleProperty.LABEL."""
    from gi.repository import Gtk

    widget.update_property(
        [Gtk.AccessibleProperty.LABEL],
        [label],
    )

"""Welcome dialog for Restore Settings — shows features on first launch."""

from __future__ import annotations

import json
import os
import pathlib

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from utils import _

_CONFIG_DIR = pathlib.Path(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
) / "restore-settings"

_CONFIG_FILE = _CONFIG_DIR / "settings.json"


def _load_settings() -> dict:
    if _CONFIG_FILE.is_file():
        try:
            return json.loads(_CONFIG_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_settings(data: dict) -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _CONFIG_FILE.write_text(json.dumps(data, indent=2))


def should_show_welcome() -> bool:
    return _load_settings().get("show-welcome", True)


class WelcomeDialog:
    """Welcome dialog explaining Restore Settings features."""

    def __init__(self, parent: Adw.ApplicationWindow) -> None:
        self._parent = parent
        self._show_switch: Gtk.Switch | None = None
        self._dialog = self._build()

    def present(self) -> None:
        self._dialog.present(self._parent)

    # ── Build UI ─────────────────────────────────────────────────

    def _build(self) -> Adw.Dialog:
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_start(20)
        content.set_margin_end(20)
        content.set_margin_top(20)

        # ── Header ───────────────────────────────────────────────
        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        header.set_halign(Gtk.Align.CENTER)

        icon = Gtk.Image.new_from_icon_name("restore-settings")
        icon.set_pixel_size(64)
        header.append(icon)

        title = Gtk.Label()
        title.set_markup(
            "<span size='xx-large' weight='bold'>"
            + _("Welcome to Restore Settings")
            + "</span>"
        )
        header.append(title)

        subtitle = Gtk.Label(
            label=_(
                "Easily restore, backup, and manage application settings on BigLinux."
            )
        )
        subtitle.add_css_class("dim-label")
        subtitle.set_wrap(True)
        subtitle.set_justify(Gtk.Justification.CENTER)
        header.append(subtitle)

        content.append(header)

        # ── Features (two columns) ──────────────────────────────
        columns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        columns.set_margin_top(18)
        columns.set_halign(Gtk.Align.CENTER)
        columns.set_hexpand(True)

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        left.set_hexpand(True)

        left_features = [
            (
                "🔄 " + _("Restore BigLinux Defaults"),
                _(
                    "Reset any application to the BigLinux default\n"
                    "settings with a single click using /etc/skel."
                ),
            ),
            (
                "📦 " + _("Export Settings"),
                _(
                    "Back up dotfiles for multiple applications\n"
                    "into a single compressed .tar.gz archive."
                ),
            ),
            (
                "🔍 " + _("Search Across All Apps"),
                _(
                    "Quickly find any installed application\n"
                    "using the integrated search in the header bar."
                ),
            ),
        ]
        for t, d in left_features:
            left.append(self._feature_box(t, d))
        columns.append(left)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        right.set_hexpand(True)

        right_features = [
            (
                "📂 " + _("Import Settings"),
                _(
                    "Restore previously exported settings from\n"
                    "a .tar.gz backup with per-application selection."
                ),
            ),
            (
                "🖥️ " + _("Flatpak Support"),
                _(
                    "View and manage Flatpak application\n"
                    "settings alongside native packages."
                ),
            ),            (
                "📋 " + _("Organized by Category"),
                _(
                    "Browse applications grouped by category:\n"
                    "browsers, multimedia, office, system, and more."
                ),
            ),        ]
        for t, d in right_features:
            right.append(self._feature_box(t, d))
        columns.append(right)

        content.append(columns)

        # ── Separator + show-on-startup switch ──────────────────
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep.set_margin_top(12)
        content.append(sep)

        switch_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        switch_row.set_margin_top(12)

        switch_label = Gtk.Label(label=_("Show this dialog on startup"))
        switch_label.set_xalign(0)
        switch_label.set_hexpand(True)
        switch_row.append(switch_label)

        self._show_switch = Gtk.Switch()
        self._show_switch.set_valign(Gtk.Align.CENTER)
        self._show_switch.set_active(should_show_welcome())
        switch_row.append(self._show_switch)

        content.append(switch_row)

        # ── Close button ────────────────────────────────────────
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        btn_box.set_margin_top(18)
        btn_box.set_halign(Gtk.Align.CENTER)

        close_btn = Gtk.Button(label=_("Let's Start"))
        close_btn.add_css_class("suggested-action")
        close_btn.add_css_class("pill")
        close_btn.set_size_request(150, -1)
        close_btn.connect("clicked", self._on_close)
        btn_box.append(close_btn)

        content.append(btn_box)

        scrolled.set_child(content)

        dialog = Adw.Dialog()
        dialog.set_content_width(900)
        dialog.set_content_height(650)
        dialog.set_child(scrolled)
        return dialog

    # ── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _feature_box(title: str, description: str) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        t = Gtk.Label(label=title)
        t.add_css_class("heading")
        t.set_halign(Gtk.Align.START)
        t.set_wrap(True)
        box.append(t)

        d = Gtk.Label(label=description)
        d.set_halign(Gtk.Align.START)
        d.set_wrap(True)
        d.set_xalign(0)
        d.add_css_class("dim-label")
        d.set_max_width_chars(40)
        box.append(d)

        return box

    def _on_close(self, _btn: Gtk.Button) -> None:
        if self._show_switch:
            settings = _load_settings()
            settings["show-welcome"] = self._show_switch.get_active()
            _save_settings(settings)
        self._dialog.close()

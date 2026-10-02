"""Welcome dialog for Restore Settings."""

from __future__ import annotations


import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from i18n import _
from ui import set_label

from backend import user_prefs
from ui.metadata import WELCOME_FEATURES


def should_show_welcome() -> bool:
    return user_prefs.get_show_welcome()


class WelcomeDialog:
    """Welcome dialog explaining the main Restore Settings features."""

    def __init__(self, parent: Adw.ApplicationWindow) -> None:
        self._parent = parent
        self._dialog: Adw.Dialog | None = None
        self._show_switch: Gtk.Switch | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_start(20)
        content.set_margin_end(20)
        content.set_margin_top(20)
        content.set_margin_bottom(12)

        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        header.set_halign(Gtk.Align.CENTER)

        icon = Gtk.Image.new_from_icon_name("restore-settings")
        icon.set_pixel_size(64)
        header.append(icon)

        title = Gtk.Label()
        title.set_wrap(True)
        title.set_justify(Gtk.Justification.CENTER)
        title.set_markup(
            "<span size='xx-large' weight='bold'>"
            + GLib.markup_escape_text(_("Welcome to Restore Settings"))
            + "</span>"
        )
        header.append(title)

        subtitle = Gtk.Label()
        subtitle.set_wrap(True)
        subtitle.set_justify(Gtk.Justification.CENTER)
        subtitle.set_markup(
            "<span size='large'>"
            + GLib.markup_escape_text(
                _("Restore, back up, and manage application settings on BigLinux")
            )
            + "</span>"
        )
        subtitle.add_css_class("dim-label")
        header.append(subtitle)

        content.append(header)

        features = Gtk.FlowBox()
        features.set_selection_mode(Gtk.SelectionMode.NONE)
        features.set_homogeneous(True)
        features.set_min_children_per_line(1)
        features.set_max_children_per_line(2)
        features.set_row_spacing(2)
        features.set_column_spacing(24)
        features.set_margin_top(18)
        features.set_halign(Gtk.Align.CENTER)
        features.set_hexpand(True)

        for feature in WELCOME_FEATURES:
            features.insert(self._create_feature_box(*feature), -1)

        content.append(features)

        tip = Gtk.Label()
        tip.set_wrap(True)
        tip.set_justify(Gtk.Justification.CENTER)
        tip.set_markup(
            "<span size='small'>"
            + GLib.markup_escape_text(
                _(
                    "Tip: Start typing to search; right-click an application "
                    "to manage favorites"
                )
            )
            + "</span>"
        )
        tip.add_css_class("dim-label")
        tip.set_margin_top(12)
        content.append(tip)

        scrolled.set_child(content)

        bottom_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        bottom_bar.set_margin_start(20)
        bottom_bar.set_margin_end(20)
        bottom_bar.set_margin_top(12)
        bottom_bar.set_margin_bottom(16)

        self._show_switch = Gtk.Switch()
        self._show_switch.set_valign(Gtk.Align.CENTER)
        self._show_switch.set_active(should_show_welcome())
        self._show_switch.connect("notify::active", lambda *_: self._persist_welcome_choice())

        switch_label = Gtk.Label(label=_("Show dialog on startup"))
        switch_label.set_xalign(0)
        set_label(self._show_switch, switch_label.get_label())

        switch_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        switch_box.append(self._show_switch)
        switch_box.append(switch_label)
        switch_box.set_hexpand(True)
        bottom_bar.append(switch_box)

        start_button = Gtk.Button(label=_("Let's Start"))
        start_button.add_css_class("suggested-action")
        start_button.add_css_class("pill")
        start_button.set_size_request(150, -1)
        start_button.connect("clicked", self._on_close)
        bottom_bar.append(start_button)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.append(scrolled)
        outer.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        outer.append(bottom_bar)

        handle = Gtk.WindowHandle()
        handle.set_child(outer)

        self._dialog = Adw.Dialog()
        self._dialog.set_content_width(900)
        self._dialog.set_content_height(650)
        self._dialog.set_child(handle)

    def present(self) -> None:
        if self._dialog and self._parent:
            self._dialog.present(self._parent)

    @staticmethod
    def _create_feature_box(icon_name: str, title: str, description: str) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_pixel_size(32)
        icon.set_valign(Gtk.Align.START)
        icon.add_css_class("dim-label")
        row.append(icon)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        title_label = Gtk.Label()
        title_label.set_markup(f"<b>{GLib.markup_escape_text(title)}</b>")
        title_label.set_halign(Gtk.Align.START)
        title_label.set_wrap(True)
        text_box.append(title_label)

        description_label = Gtk.Label(label=description)
        description_label.set_halign(Gtk.Align.START)
        description_label.set_wrap(True)
        description_label.set_xalign(0)
        description_label.add_css_class("dim-label")
        description_label.set_max_width_chars(40)
        text_box.append(description_label)

        row.append(text_box)
        return row

    def _on_close(self, _button: Gtk.Button) -> None:
        if self._show_switch:
            self._persist_welcome_choice()
        if self._dialog:
            self._dialog.close()

    def _persist_welcome_choice(self) -> None:
        try:
            user_prefs.set_show_welcome(self._show_switch.get_active())
        except OSError as exc:
            alert = Adw.AlertDialog.new(_("Could not save preferences"), str(exc))
            alert.add_response("close", _("Close"))
            alert.present(self._parent)

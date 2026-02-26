"""FlowBox grid of application cards — BigControlCenter style."""

from __future__ import annotations

import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gtk, Pango

from utils import _, set_label
from data.app_registry import AppEntry
from backend.app_detector import get_localized_name
from backend.reset_manager import has_config


class AppGrid(Gtk.Box):
    """Displays application cards in a responsive FlowBox — BigControlCenter style."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)

        self._on_app_activated: callable | None = None
        self._on_app_hover: callable | None = None

        # CSS for program-button style (same as BigControlCenter)
        css = Gtk.CssProvider()
        css.load_from_data(b"""
            .program-button {
                background: none;
                padding: 8px;
                font-weight: inherit;
                min-width: 150px;
            }
            .program-button:hover {
                background: alpha(currentColor, 0.08);
            }
            .program-button:active {
                transform: scale(0.94);
                transition: transform 0.15s ease;
                background-color: alpha(currentColor, 0.15);
            }
        """)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        # Empty state
        self._status_page = Adw.StatusPage()
        self._status_page.set_icon_name("edit-find-symbolic")
        self._status_page.set_title(_("No applications found"))
        self._status_page.set_description(
            _("Try another category or search term")
        )
        self._status_page.set_visible(False)
        self._status_page.set_vexpand(True)
        self.append(self._status_page)

        # Scrolled container
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self._flowbox = Gtk.FlowBox()
        self._flowbox.set_valign(Gtk.Align.START)
        self._flowbox.set_max_children_per_line(20)
        self._flowbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._flowbox.set_homogeneous(False)
        self._flowbox.set_column_spacing(12)
        self._flowbox.set_row_spacing(18)
        self._flowbox.set_margin_start(16)
        self._flowbox.set_margin_end(16)
        self._flowbox.set_margin_top(16)
        self._flowbox.set_margin_bottom(16)

        scrolled.set_child(self._flowbox)
        self._scrolled = scrolled
        self.append(scrolled)

        self._cards: list[tuple[Gtk.FlowBoxChild, AppEntry]] = []

    def set_on_app_activated(self, callback: callable) -> None:
        self._on_app_activated = callback

    def set_on_app_hover(self, callback: callable) -> None:
        self._on_app_hover = callback

    def populate(self, apps: list[AppEntry]) -> None:
        """Replace all cards with the given app list."""
        child = self._flowbox.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self._flowbox.remove(child)
            child = next_child
        self._cards.clear()

        for entry in apps:
            btn = self._create_program_button(entry)
            self._flowbox.append(btn)
            # FlowBox wraps in FlowBoxChild automatically
            fb_child = btn.get_parent()
            self._cards.append((fb_child, entry))

        self._update_empty_state()

    def filter_by_text(self, text: str) -> None:
        """Show/hide cards based on search text."""
        query = text.lower().strip()
        visible_count = 0
        for fb_child, entry in self._cards:
            display_name = get_localized_name(entry)
            match = (
                not query
                or query in display_name.lower()
                or query in entry.name.lower()
                or query in entry.app_id.lower()
            )
            fb_child.set_visible(match)
            if match:
                visible_count += 1
        self._update_empty_state(visible_count)

    def _update_empty_state(self, visible_count: int | None = None) -> None:
        if visible_count is None:
            visible_count = sum(1 for c, _ in self._cards if c.get_visible())
        empty = visible_count == 0
        self._status_page.set_visible(empty)
        self._scrolled.set_visible(not empty)

    def _create_program_button(self, entry: AppEntry) -> Gtk.Button:
        """Create a program button matching BigControlCenter style."""
        button = Gtk.Button()
        button.add_css_class("program-button")
        button.set_focusable(True)
        button.set_focus_on_click(True)
        button.connect("clicked", self._on_card_clicked, entry)

        # Hover → show description in status bar
        motion = Gtk.EventControllerMotion.new()
        motion.connect("enter", self._on_card_enter, entry)
        motion.connect("leave", self._on_card_leave)
        button.add_controller(motion)

        # Content: icon + name (vertical)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        content.set_halign(Gtk.Align.CENTER)
        content.set_valign(Gtk.Align.START)
        button.set_child(content)

        # Icon — 64px
        icon = self._create_icon(entry.icon)
        content.append(icon)

        # Name label — ellipsize, wrap, centered
        name_label = Gtk.Label(label=get_localized_name(entry))
        name_label.set_ellipsize(Pango.EllipsizeMode.END)
        name_label.set_max_width_chars(20)
        name_label.set_width_chars(10)
        name_label.set_wrap(True)
        name_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        name_label.set_lines(3)
        name_label.set_justify(Gtk.Justification.CENTER)
        content.append(name_label)

        return button

    def _create_icon(self, icon_ref: str) -> Gtk.Image:
        """Create a 64px icon from path or icon name."""
        if icon_ref.startswith("/") and os.path.isfile(icon_ref):
            icon = Gtk.Image.new_from_file(icon_ref)
        elif icon_ref:
            icon = Gtk.Image.new_from_icon_name(icon_ref)
        else:
            icon = Gtk.Image.new_from_icon_name("application-x-executable")
        icon.set_pixel_size(64)
        return icon

    def _on_card_clicked(self, _button: Gtk.Button, entry: AppEntry) -> None:
        if self._on_app_activated:
            self._on_app_activated(entry)

    def _on_card_enter(
        self,
        _ctrl: Gtk.EventControllerMotion,
        _x: float,
        _y: float,
        entry: AppEntry,
    ) -> None:
        if self._on_app_hover:
            paths = ", ".join(entry.config_paths[:3])
            self._on_app_hover(paths)

    def _on_card_leave(self, _ctrl: Gtk.EventControllerMotion) -> None:
        if self._on_app_hover:
            self._on_app_hover("")

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
from backend.reset_manager import has_skel


def _is_flatpak(entry: AppEntry) -> bool:
    return entry.app_id.startswith("flatpak-") or entry.category == "flatpak"


class AppGrid(Gtk.Box):
    """Displays application cards in a responsive FlowBox — BigControlCenter style."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)

        self._on_app_activated: callable | None = None
        self._on_app_hover: callable | None = None
        self._favorite_provider: callable | None = None
        self._on_toggle_favorite: callable | None = None

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
            .card-badge {
                background-color: @window_bg_color;
                border-radius: 999px;
                padding: 2px;
                box-shadow: 0 0 0 1px alpha(@window_fg_color, 0.15);
            }
            .card-badge-biglinux {
                color: @accent_color;
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

    def set_favorite_provider(self, provider: callable) -> None:
        """provider(entry) -> bool : whether the app is currently a favorite."""
        self._favorite_provider = provider

    def set_on_toggle_favorite(self, callback: callable) -> None:
        """callback(entry) : toggle the app's favorite state."""
        self._on_toggle_favorite = callback

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

        is_flatpak = _is_flatpak(entry)
        skel_available = has_skel(entry)

        # Rich tooltip (source + BigLinux-default hint).
        kind = _("Flatpak application") if is_flatpak else _("Native application")
        tip = f"{get_localized_name(entry)}\n{kind}"
        if skel_available:
            tip += "\n" + _("BigLinux default available")
        button.set_tooltip_text(tip)

        # Hover → show description in status bar
        motion = Gtk.EventControllerMotion.new()
        motion.connect("enter", self._on_card_enter, entry)
        motion.connect("leave", self._on_card_leave)
        button.add_controller(motion)

        # Right-click → favorites context menu
        secondary = Gtk.GestureClick.new()
        secondary.set_button(Gdk.BUTTON_SECONDARY)
        secondary.connect("pressed", self._on_card_secondary, button, entry)
        button.add_controller(secondary)

        # Long-press (touch) → same context menu
        long_press = Gtk.GestureLongPress.new()
        long_press.set_touch_only(True)
        long_press.connect(
            "pressed",
            lambda _g, x, y: self._show_favorite_menu(button, entry, x, y),
        )
        button.add_controller(long_press)

        # Keyboard: Menu key or Shift+F10 → same context menu on the focused card
        key = Gtk.EventControllerKey.new()
        key.connect("key-pressed", self._on_card_key, button, entry)
        button.add_controller(key)

        # Content: icon + name (vertical)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        content.set_halign(Gtk.Align.CENTER)
        content.set_valign(Gtk.Align.START)
        button.set_child(content)

        # Icon — 64px, with corner badges (source + BigLinux default).
        icon = self._create_icon(entry.icon)
        icon_holder = Gtk.Overlay()
        icon_holder.set_halign(Gtk.Align.CENTER)
        icon_holder.set_child(icon)

        if is_flatpak:
            fp_badge = Gtk.Image.new_from_icon_name("folder-flatpak")
            fp_badge.set_pixel_size(18)
            fp_badge.add_css_class("card-badge")
            fp_badge.set_halign(Gtk.Align.END)
            fp_badge.set_valign(Gtk.Align.END)
            set_label(fp_badge, _("Flatpak application"))
            icon_holder.add_overlay(fp_badge)

        if skel_available:
            bl_badge = Gtk.Image.new_from_icon_name("biglinux-symbolic")
            bl_badge.set_pixel_size(16)
            bl_badge.add_css_class("card-badge")
            bl_badge.add_css_class("card-badge-biglinux")
            bl_badge.set_halign(Gtk.Align.END)
            bl_badge.set_valign(Gtk.Align.START)
            set_label(bl_badge, _("BigLinux default available"))
            icon_holder.add_overlay(bl_badge)

        content.append(icon_holder)

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

    def _on_card_secondary(
        self,
        gesture: Gtk.GestureClick,
        _n_press: int,
        x: float,
        y: float,
        button: Gtk.Button,
        entry: AppEntry,
    ) -> None:
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        self._show_favorite_menu(button, entry, x, y)

    def _on_card_key(
        self,
        _controller: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        state: Gdk.ModifierType,
        button: Gtk.Button,
        entry: AppEntry,
    ) -> bool:
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
        if keyval == Gdk.KEY_Menu or (shift and keyval == Gdk.KEY_F10):
            self._show_favorite_menu(
                button, entry, button.get_width() / 2, button.get_height() / 2)
            return True
        return False

    def _show_favorite_menu(
        self, button: Gtk.Button, entry: AppEntry, x: float, y: float
    ) -> None:
        """Show a small popover to add/remove the app from favorites."""
        if self._on_toggle_favorite is None:
            return
        is_fav = bool(self._favorite_provider and self._favorite_provider(entry))

        popover = Gtk.Popover()
        popover.set_parent(button)
        popover.set_has_arrow(True)
        popover.set_pointing_to(Gdk.Rectangle(int(x), int(y), 1, 1))
        popover.set_autohide(True)

        item = Gtk.Button()
        item.add_css_class("flat")
        item.set_halign(Gtk.Align.FILL)
        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        # Filled star = currently a favorite (click to remove); outline = add.
        icon_name = "starred-symbolic" if is_fav else "non-starred-symbolic"
        content.append(Gtk.Image.new_from_icon_name(icon_name))
        label = _("Remove from favorites") if is_fav else _("Add to favorites")
        content.append(Gtk.Label(label=label))
        item.set_child(content)

        def _activate(_b: Gtk.Button) -> None:
            popover.popdown()
            if self._on_toggle_favorite:
                self._on_toggle_favorite(entry)

        item.connect("clicked", _activate)
        popover.set_child(item)
        popover.connect("closed", lambda p: p.unparent())
        popover.popup()

    def _on_card_enter(
        self,
        _ctrl: Gtk.EventControllerMotion,
        _x: float,
        _y: float,
        entry: AppEntry,
    ) -> None:
        if self._on_app_hover:
            kind = _("Flatpak") if _is_flatpak(entry) else _("Native")
            parts = [get_localized_name(entry), kind]
            if has_skel(entry):
                parts.append(_("BigLinux default available"))
            self._on_app_hover(" · ".join(parts))

    def _on_card_leave(self, _ctrl: Gtk.EventControllerMotion) -> None:
        if self._on_app_hover:
            self._on_app_hover("")

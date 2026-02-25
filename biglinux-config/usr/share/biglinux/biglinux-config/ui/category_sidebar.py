"""Category sidebar widget — matches BigControlCenter layout."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gdk, Gtk, Pango

from utils import _
from data.app_registry import CATEGORIES


class CategoryRow(Gtk.ListBoxRow):
    """Custom row storing a category ID."""

    def __init__(self, category_id: str) -> None:
        super().__init__()
        self.category_id = category_id
        self.set_selectable(False)
        self.set_activatable(True)


class CategorySidebar(Gtk.Box):
    """Vertical list of categories with symbolic icons — BigControlCenter style."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)

        self.set_hexpand(False)
        self.set_vexpand(True)
        self.set_size_request(220, -1)

        # CSS for active-category highlight
        css = Gtk.CssProvider()
        css.load_from_data(b"""
            .active-category {
                background-color: alpha(currentColor, 0.1);
                border-radius: 6px;
            }
        """)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        self.append(scrolled)

        self._listbox = Gtk.ListBox()
        self._listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self._listbox.add_css_class("navigation-sidebar")
        self._listbox.connect("row-activated", self._on_row_activated)
        scrolled.set_child(self._listbox)

        # Categories including Flatpak pseudo-category
        self._all_categories = list(CATEGORIES) + [
            {"id": "flatpak", "label": "Flatpak", "icon": "folder-flatpak"},
        ]

        self._rows: dict[str, CategoryRow] = {}
        self._active_id: str | None = None
        self._on_category_changed: callable | None = None

        self._build_rows()

    def set_on_category_changed(self, callback: callable) -> None:
        self._on_category_changed = callback

    def _build_rows(self) -> None:
        for cat in self._all_categories:
            row = CategoryRow(cat["id"])
            content = self._create_row_content(cat)
            row.set_child(content)
            self._rows[cat["id"]] = row
            self._listbox.append(row)
            row.set_visible(False)

    def _create_row_content(self, cat: dict) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_top(8)
        box.set_margin_bottom(8)

        icon = Gtk.Image.new_from_icon_name(cat["icon"])
        icon.add_css_class("symbolic")
        icon.set_pixel_size(22)
        icon.set_margin_end(8)
        box.append(icon)

        label = Gtk.Label(label=_(cat["label"]))
        label.set_halign(Gtk.Align.START)
        label.set_hexpand(True)
        label.set_wrap(True)
        label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        label.set_xalign(0.0)
        label.set_max_width_chars(20)
        box.append(label)

        return box

    def _on_row_activated(self, _listbox: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
        if not isinstance(row, CategoryRow):
            return
        self._select(row.category_id)

    def _select(self, category_id: str) -> None:
        for cid, row in self._rows.items():
            if cid == category_id:
                row.add_css_class("active-category")
            else:
                row.remove_css_class("active-category")

        self._active_id = category_id
        if self._on_category_changed:
            self._on_category_changed(category_id)

    @property
    def listbox(self) -> Gtk.ListBox:
        return self._listbox

    def set_category_visible(self, category_id: str, visible: bool) -> None:
        row = self._rows.get(category_id)
        if row:
            row.set_visible(visible)

    def select_category(self, category_id: str) -> None:
        self._select(category_id)

    def get_selected_category(self) -> str | None:
        return self._active_id

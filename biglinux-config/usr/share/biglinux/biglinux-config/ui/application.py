"""Main GTK4/Adwaita application — BigControlCenter visual style."""

from __future__ import annotations

import pathlib
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gio, Gtk

from utils import _, set_label
from data.app_registry import AppEntry, CATEGORIES
from backend.app_detector import get_installed_apps, get_favorites
from backend.flatpak_detector import get_installed_flatpaks
from ui.category_sidebar import CategorySidebar
from ui.app_grid import AppGrid
from ui.restore_dialog import show_restore_dialog
from ui.about_dialog import show_about_dialog
from ui.backup_dialog import show_export_dialog, show_import_dialog
from ui.welcome_dialog import WelcomeDialog, should_show_welcome


class BigConfigApp(Adw.Application):
    """Single-instance Adw.Application for BigLinux Config."""

    def __init__(self, application_id: str, **kwargs) -> None:
        super().__init__(
            application_id=application_id,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
            **kwargs,
        )
        GLib.set_prgname(application_id)

        # Register custom icon directories so app icons are found
        icon_theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        app_dir = pathlib.Path(__file__).resolve().parents[1]
        icon_theme.add_search_path(str(app_dir / "img"))
        # pixmaps lives under .../usr/share/pixmaps (2 levels up from app_dir)
        share_dir = app_dir.parents[1]  # .../usr/share/
        icon_theme.add_search_path(str(share_dir / "pixmaps"))

        self._installed_apps: list[AppEntry] = []
        self._flatpak_apps: list[AppEntry] = []
        self._apps_by_category: dict[str, list[AppEntry]] = {}
        self._current_category: str = "favorites"

    def do_activate(self) -> None:
        win = self.props.active_window
        if win:
            win.present()
            return

        win = BigConfigWindow(application=self)
        self._setup_actions(win)
        win.present()

        self._load_apps_async(win)

        # Show welcome dialog on first launch
        if should_show_welcome():
            GLib.idle_add(self._show_welcome, win)

    def _setup_actions(self, win: BigConfigWindow) -> None:
        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", lambda _a, _p: show_about_dialog(win))
        self.add_action(about_action)

        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda _a, _p: self.quit())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<Control>q"])

        export_action = Gio.SimpleAction.new("export-backup", None)
        export_action.connect(
            "activate",
            lambda _a, _p: show_export_dialog(
                win, self._installed_apps + self._flatpak_apps
            ),
        )
        self.add_action(export_action)

        import_action = Gio.SimpleAction.new("import-backup", None)
        import_action.connect(
            "activate", lambda _a, _p: show_import_dialog(win)
        )
        self.add_action(import_action)

        welcome_action = Gio.SimpleAction.new("welcome", None)
        welcome_action.connect(
            "activate", lambda _a, _p: self._show_welcome(win)
        )
        self.add_action(welcome_action)

    def _show_welcome(self, win: BigConfigWindow) -> bool:
        WelcomeDialog(win).present()
        return GLib.SOURCE_REMOVE

    def _load_apps_async(self, win: BigConfigWindow) -> None:
        def _worker() -> None:
            installed = get_installed_apps()
            flatpaks = get_installed_flatpaks()
            GLib.idle_add(self._on_apps_loaded, win, installed, flatpaks)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_apps_loaded(
        self,
        win: BigConfigWindow,
        installed: list[AppEntry],
        flatpaks: list[AppEntry],
    ) -> bool:
        self._installed_apps = installed
        self._flatpak_apps = flatpaks
        all_apps = installed + flatpaks

        self._apps_by_category = {}
        for entry in all_apps:
            self._apps_by_category.setdefault(entry.category, []).append(entry)

        favorites = get_favorites(installed)
        if flatpaks:
            favorites.extend(flatpaks[:3])
        self._apps_by_category["favorites"] = favorites

        for cat_info in CATEGORIES:
            cid = cat_info["id"]
            win.sidebar.set_category_visible(
                cid, bool(self._apps_by_category.get(cid))
            )

        win.sidebar.set_category_visible("flatpak", len(self._flatpak_apps) > 0)

        win.sidebar.select_category("favorites")
        self._current_category = "favorites"
        self._update_grid(win)
        win.set_loading(False)

        return GLib.SOURCE_REMOVE

    def on_category_changed(self, win: BigConfigWindow, category_id: str) -> None:
        self._current_category = category_id
        win.search_entry.set_text("")
        self._update_grid(win)

    def on_search_changed(self, win: BigConfigWindow, text: str) -> None:
        if text.strip():
            all_apps = self._installed_apps + self._flatpak_apps
            win.grid.populate(all_apps)
            win.grid.filter_by_text(text)
        else:
            self._update_grid(win)

    def _update_grid(self, win: BigConfigWindow) -> None:
        apps = self._apps_by_category.get(self._current_category, [])
        win.grid.populate(apps)

    def on_app_activated(self, win: BigConfigWindow, entry: AppEntry) -> None:
        show_restore_dialog(win, entry, on_complete=lambda _r: self._update_grid(win))


class BigConfigWindow(Adw.ApplicationWindow):
    """Main window — BigControlCenter visual layout."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.set_title(_("Restore Settings"))
        self.set_default_size(1100, 620)
        self.set_size_request(360, 400)

        self._css_provider = Gtk.CssProvider()
        self._load_css()

        app: BigConfigApp = self.get_application()
        self._build_ui(app)

    def _load_css(self) -> None:
        self._css_provider.load_from_data(b"""
            .status-bar {
                border-top: 1px solid @borders;
                padding: 6px 10px;
            }
            .background-as-view-bg-color {
                background-color: var(--view-bg-color);
            }
        """)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            self._css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _build_ui(self, app: BigConfigApp) -> None:
        # Toast overlay as root (background color)
        toast_overlay = Adw.ToastOverlay()
        toast_overlay.add_css_class("background-as-view-bg-color")
        self.set_content(toast_overlay)

        # NavigationSplitView
        self._split_view = Adw.NavigationSplitView()
        toast_overlay.set_child(self._split_view)

        # ── Sidebar ──────────────────────────────────────────────
        sidebar_toolbar = Adw.ToolbarView()
        sidebar_header = Adw.HeaderBar()

        # App icon button (left side) — opens About dialog
        app_icon_btn = Gtk.Button()
        app_icon_btn.set_tooltip_text(_("About Restore Settings"))
        app_icon = Gtk.Image.new_from_icon_name("restore-settings")
        app_icon.set_pixel_size(25)
        app_icon_btn.set_child(app_icon)
        app_icon_btn.add_css_class("flat")
        app_icon_btn.connect("clicked", lambda _b: app.activate_action("about", None))
        sidebar_header.pack_start(app_icon_btn)

        sidebar_header.set_title_widget(
            Adw.WindowTitle.new(_("Restore Settings"), "")
        )
        sidebar_toolbar.add_top_bar(sidebar_header)

        self.sidebar = CategorySidebar()
        self.sidebar.set_on_category_changed(
            lambda cid: self._on_category_selected(cid)
        )
        sidebar_toolbar.set_content(self.sidebar)

        sidebar_page = Adw.NavigationPage.new(sidebar_toolbar, _("Categories"))
        self._split_view.set_sidebar(sidebar_page)

        # ── Content ──────────────────────────────────────────────
        content_toolbar = Adw.ToolbarView()
        content_header = Adw.HeaderBar()

        # Search entry always visible in headerbar center
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text(_("Search..."))
        self.search_entry.set_hexpand(False)
        self.search_entry.set_width_chars(20)
        self.search_entry.connect("search-changed", self._on_search_changed)

        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        search_box.append(self.search_entry)
        content_header.set_title_widget(search_box)

        # Menu button (right side)
        menu = Gio.Menu()
        backup_section = Gio.Menu()
        backup_section.append(_("Export settings…"), "app.export-backup")
        backup_section.append(_("Import settings…"), "app.import-backup")
        menu.append_section(None, backup_section)

        misc_section = Gio.Menu()
        misc_section.append(_("Welcome"), "app.welcome")
        misc_section.append(_("About"), "app.about")
        menu.append_section(None, misc_section)

        menu_button = Gtk.MenuButton()
        menu_button.set_icon_name("open-menu-symbolic")
        menu_button.set_menu_model(menu)
        menu_button.set_tooltip_text(_("Menu"))
        content_header.pack_end(menu_button)

        content_toolbar.add_top_bar(content_header)

        # Status bar (bottom) — revealer with crossfade
        self._status_revealer = Gtk.Revealer()
        self._status_revealer.set_transition_type(Gtk.RevealerTransitionType.CROSSFADE)
        self._status_revealer.set_transition_duration(150)
        self._status_label = Gtk.Label()
        self._status_label.set_wrap(True)
        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        status_box.append(self._status_label)
        status_box.add_css_class("status-bar")
        self._status_revealer.set_child(status_box)
        self._status_revealer.set_reveal_child(False)
        self._status_revealer.set_visible(False)
        content_toolbar.add_bottom_bar(self._status_revealer)

        # Content stack (loading / grid)
        self._content_stack = Gtk.Stack()
        self._content_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._content_stack.set_transition_duration(200)

        # Loading state
        loading_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=16
        )
        loading_box.set_valign(Gtk.Align.CENTER)
        loading_box.set_halign(Gtk.Align.CENTER)
        spinner = Adw.Spinner()
        spinner.set_size_request(48, 48)
        loading_box.append(spinner)
        loading_label = Gtk.Label(label=_("Loading applications…"))
        loading_label.add_css_class("title-4")
        loading_label.add_css_class("dim-label")
        loading_box.append(loading_label)
        self._content_stack.add_named(loading_box, "loading")

        # Grid
        self.grid = AppGrid()
        self.grid.set_on_app_activated(
            lambda entry: app.on_app_activated(self, entry)
        )
        self.grid.set_on_app_hover(self._on_hover_info)
        self._content_stack.add_named(self.grid, "grid")
        self._content_stack.set_visible_child_name("loading")

        content_toolbar.set_content(self._content_stack)

        content_page = Adw.NavigationPage.new(content_toolbar, _("Applications"))
        self._split_view.set_content(content_page)

        # Key controller — redirect typing to search
        key_ctrl = Gtk.EventControllerKey.new()
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_ctrl)

    # ── Public API ───────────────────────────────────────────────

    def set_loading(self, loading: bool) -> None:
        self._content_stack.set_visible_child_name(
            "loading" if loading else "grid"
        )

    def toggle_search(self) -> None:
        self.search_entry.grab_focus()

    def set_status_message(self, message: str) -> None:
        self._status_label.set_text(message)
        has_text = bool(message)
        self._status_revealer.set_reveal_child(has_text)
        self._status_revealer.set_visible(has_text)

    # ── Private handlers ─────────────────────────────────────────

    def _on_category_selected(self, category_id: str) -> None:
        app: BigConfigApp = self.get_application()
        app.on_category_changed(self, category_id)
        if self._split_view.get_collapsed():
            self._split_view.set_show_content(True)

    def _on_search_changed(self, entry: Gtk.SearchEntry) -> None:
        app: BigConfigApp = self.get_application()
        app.on_search_changed(self, entry.get_text())

    def _on_hover_info(self, description: str) -> None:
        self.set_status_message(description)

    def _on_key_pressed(
        self,
        _ctrl: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        state: Gdk.ModifierType,
    ) -> bool:
        # Backspace → remove char from search
        if keyval == Gdk.KEY_BackSpace:
            text = self.search_entry.get_text()
            if text:
                self.search_entry.grab_focus()
                self.search_entry.set_text(text[:-1])
                self.search_entry.set_position(-1)
                return True

        # Escape → clear search
        if keyval == Gdk.KEY_Escape:
            if self.search_entry.get_text():
                self.search_entry.set_text("")
                return True

        # Navigation keys — let GTK handle
        if keyval in (
            Gdk.KEY_Up, Gdk.KEY_Down, Gdk.KEY_Left, Gdk.KEY_Right,
            Gdk.KEY_Return, Gdk.KEY_Tab, Gdk.KEY_space,
        ):
            return False

        # Skip if search already focused or modifiers pressed
        if self.search_entry.has_focus():
            return False
        if state & (
            Gdk.ModifierType.CONTROL_MASK
            | Gdk.ModifierType.ALT_MASK
        ):
            return False

        # Printable char → redirect to search
        ch = chr(Gdk.keyval_to_unicode(keyval))
        if ch.isprintable():
            self.search_entry.grab_focus()
            self.search_entry.set_text(self.search_entry.get_text() + ch)
            self.search_entry.set_position(-1)
            return True

        return False

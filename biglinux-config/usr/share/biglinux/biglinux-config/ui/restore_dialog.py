"""Restore dialog — modal for choosing reset mode and confirming."""

from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gio, Gtk

from utils import _, ngettext
from data.app_registry import AppEntry
from backend.app_detector import get_localized_name
from backend.reset_manager import (
    ResetMode,
    ResetResult,
    format_size,
    get_running_pids,
    has_config,
    has_skel,
    kill_app,
    reset_app,
)

# ---------------------------------------------------------------------------
# Custom CSS for the restore dialog
# ---------------------------------------------------------------------------
_RESTORE_CSS = """
.restore-path-row {
    min-height: 42px;
}
.restore-desc-card {
    padding: 14px;
    border-radius: 12px;
}
.restore-size-badge {
    padding: 3px 10px;
    border-radius: 99px;
    font-size: 12px;
    font-weight: 600;
}
.restore-empty-icon {
    opacity: 0.4;
}
"""

_css_loaded = False


def _ensure_css() -> None:
    """Load custom CSS once."""
    global _css_loaded
    if _css_loaded:
        return
    _css_loaded = True
    provider = Gtk.CssProvider()
    provider.load_from_string(_RESTORE_CSS)
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(),
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )


def _get_mimetype_icon(path: str) -> str:
    """Return the best symbolic icon name for a path based on its mimetype."""
    import os

    expanded = os.path.expanduser(path)

    if os.path.isdir(expanded):
        basename = os.path.basename(expanded.rstrip("/"))
        folder_icons = {
            ".config": "folder-templates-symbolic",
            ".local": "folder-templates-symbolic",
            ".cache": "folder-templates-symbolic",
            ".mozilla": "folder-remote-symbolic",
        }
        return folder_icons.get(basename, "folder-symbolic")

    if os.path.isfile(expanded):
        content_type, _ = Gio.content_type_guess(expanded, None)
        if content_type:
            icon = Gio.content_type_get_symbolic_icon(content_type)
            if icon:
                names = icon.get_names()
                if names:
                    return names[0]

    # Heuristic based on extension/name
    lower = path.lower()
    if lower.endswith((".conf", ".cfg", ".ini", ".toml", ".yaml", ".yml")):
        return "text-x-generic-symbolic"
    if lower.endswith((".json",)):
        return "text-x-script-symbolic"
    if lower.endswith((".xml",)):
        return "text-xml-symbolic"
    if lower.endswith((".db", ".sqlite")):
        return "drive-harddisk-symbolic"
    if "/." in path or path.startswith("~/."):
        return "folder-templates-symbolic"

    return "text-x-generic-symbolic"


def _open_path_in_filemanager(path: str) -> None:
    """Open a path in the default file manager, selecting the file if possible."""
    import os
    import subprocess

    expanded = os.path.expanduser(path)

    if os.path.isfile(expanded):
        uri = Gio.File.new_for_path(expanded).get_uri()
        try:
            subprocess.Popen(
                ["dbus-send", "--session", "--dest=org.freedesktop.FileManager1",
                 "--type=method_call",
                 "/org/freedesktop/FileManager1",
                 "org.freedesktop.FileManager1.ShowItems",
                 f"array:string:{uri}", "string:"],
            )
            return
        except FileNotFoundError:
            pass
        expanded = os.path.dirname(expanded)

    if os.path.isdir(expanded):
        target = expanded
    else:
        parent_dir = os.path.dirname(expanded)
        if os.path.isdir(parent_dir):
            target = parent_dir
        else:
            return

    uri = Gio.File.new_for_path(target).get_uri()
    Gtk.show_uri(None, uri, Gdk.CURRENT_TIME)


def show_restore_dialog(
    parent: Adw.ApplicationWindow,
    entry: AppEntry,
    on_complete: callable | None = None,
) -> None:
    """Present the restore options dialog for an application."""
    import os
    import glob

    _ensure_css()

    config_exists = has_config(entry)
    skel_exists = has_skel(entry)

    dialog = Adw.Window()
    dialog.set_default_size(500, 420)
    dialog.set_modal(True)
    dialog.set_transient_for(parent)

    # ToolbarView with HeaderBar for close button (no title)
    toolbar_view = Adw.ToolbarView()
    toolbar_view.set_top_bar_style(Adw.ToolbarStyle.FLAT)
    toolbar_view.set_extend_content_to_top_edge(True)
    header = Adw.HeaderBar()
    header.set_show_title(False)
    toolbar_view.add_top_bar(header)

    # Main scrollable area
    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroll.set_vexpand(True)

    content_box = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL,
        spacing=12,
    )
    content_box.set_margin_top(40)
    content_box.set_margin_bottom(24)
    content_box.set_margin_start(24)
    content_box.set_margin_end(24)

    # ── App icon ──
    app_icon = Gtk.Image()
    app_icon.set_pixel_size(48)
    if entry.icon.startswith("/"):
        if os.path.isfile(entry.icon):
            app_icon.set_from_file(entry.icon)
        else:
            app_icon.set_from_icon_name("application-x-executable")
    else:
        app_icon.set_from_icon_name(entry.icon)
    app_icon.set_halign(Gtk.Align.CENTER)
    content_box.append(app_icon)

    # ── App name ──
    app_name_label = Gtk.Label(label=get_localized_name(entry))
    app_name_label.add_css_class("title-2")
    app_name_label.set_halign(Gtk.Align.CENTER)
    content_box.append(app_name_label)

    # ── Subtitle explanation ──
    subtitle_label = Gtk.Label(
        label=_("Choose how to restore the settings for this application.")
    )
    subtitle_label.add_css_class("dim-label")
    subtitle_label.set_wrap(True)
    subtitle_label.set_halign(Gtk.Align.CENTER)
    subtitle_label.set_justify(Gtk.Justification.CENTER)
    content_box.append(subtitle_label)

    # ── Paths section with individual sizes ──
    if entry.config_paths:
        # Calculate individual sizes and total
        def _path_size(raw_path: str) -> int:
            expanded = os.path.expanduser(raw_path)
            targets = glob.glob(expanded) if ("*" in expanded or "?" in expanded) else [expanded]
            total = 0
            for target in targets:
                if os.path.isdir(target):
                    for dirpath, _dirnames, filenames in os.walk(target):
                        for f in filenames:
                            try:
                                total += os.path.getsize(os.path.join(dirpath, f))
                            except OSError:
                                pass
                elif os.path.isfile(target):
                    try:
                        total += os.path.getsize(target)
                    except OSError:
                        pass
            return total

        path_sizes = {p: _path_size(p) for p in entry.config_paths}
        total_size = sum(path_sizes.values())

        paths_group = Adw.PreferencesGroup()
        paths_group.set_margin_top(4)

        # Expander row with path count and total size in subtitle
        expander = Adw.ExpanderRow()
        expander.set_title(_("Paths that will be replaced"))
        n = len(entry.config_paths)
        count_base = ngettext("%d path", "%d paths", n)
        # Handle broken translations that might have "form1,form2" in a single msgstr
        if "," in count_base and count_base.count("%d") > 1:
            parts = count_base.split(",")
            count_base = parts[0] if n == 1 else parts[-1]
        
        count_text = count_base % n
        expander.set_subtitle(f"{count_text} — {format_size(total_size)}")

        # Use add_prefix for consistent icon sizing with mode cards
        expander_icon = Gtk.Image.new_from_icon_name("folder-symbolic")
        expander_icon.set_pixel_size(24)
        expander.add_prefix(expander_icon)

        for cfg_path in entry.config_paths:
            expanded = os.path.expanduser(cfg_path)
            row = Adw.ActionRow()
            row.add_css_class("restore-path-row")
            row.set_title(cfg_path)
            row.set_title_lines(1)

            # Show individual size as subtitle
            psize = path_sizes.get(cfg_path, 0)
            row.set_subtitle(format_size(psize))
            row.set_subtitle_lines(1)

            # Mimetype-aware icon
            icon_name = _get_mimetype_icon(cfg_path)
            prefix_icon = Gtk.Image.new_from_icon_name(icon_name)
            prefix_icon.set_pixel_size(18)
            row.add_prefix(prefix_icon)

            # Open in file manager button
            open_btn = Gtk.Button()
            open_btn.set_icon_name("folder-open-symbolic")
            open_btn.set_valign(Gtk.Align.CENTER)
            open_btn.add_css_class("flat")
            open_btn.add_css_class("circular")
            open_btn.set_tooltip_text(_("Open in file manager"))
            open_btn.connect("clicked", lambda _b, p=cfg_path: _open_path_in_filemanager(p))
            row.add_suffix(open_btn)

            expander.add_row(row)

        paths_group.add(expander)
        content_box.append(paths_group)

    # ── No config found ──
    if not config_exists and not skel_exists:
        empty_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
        )
        empty_box.set_valign(Gtk.Align.CENTER)
        empty_box.set_halign(Gtk.Align.CENTER)
        empty_box.set_margin_top(16)
        empty_box.set_margin_bottom(16)

        empty_icon = Gtk.Image.new_from_icon_name("folder-symbolic")
        empty_icon.set_pixel_size(48)
        empty_icon.add_css_class("restore-empty-icon")
        empty_box.append(empty_icon)

        empty_label = Gtk.Label(
            label=_("No settings found for this application.")
        )
        empty_label.add_css_class("dim-label")
        empty_label.set_wrap(True)
        empty_label.set_halign(Gtk.Align.CENTER)
        empty_box.append(empty_label)

        content_box.append(empty_box)

        close_btn = Gtk.Button(label=_("Close"))
        close_btn.set_halign(Gtk.Align.CENTER)
        close_btn.add_css_class("pill")
        close_btn.connect("clicked", lambda _b: dialog.close())
        content_box.append(close_btn)

        scroll.set_child(content_box)
        toolbar_view.set_content(scroll)
        dialog.set_content(toolbar_view)
        dialog.present()
        return

    # ── Mode cards with action buttons integrated ──
    modes_box = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL,
        spacing=8,
    )
    modes_box.set_margin_top(4)

    if skel_exists:
        biglinux_card = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=12,
        )
        biglinux_card.add_css_class("card")
        biglinux_card.add_css_class("restore-desc-card")

        bl_icon = Gtk.Image.new_from_icon_name("biglinux-symbolic")
        bl_icon.set_pixel_size(24)
        bl_icon.set_valign(Gtk.Align.CENTER)
        biglinux_card.append(bl_icon)

        bl_text_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=2,
        )
        bl_text_box.set_hexpand(True)
        bl_text_box.set_valign(Gtk.Align.CENTER)
        bl_title = Gtk.Label(label=_("BigLinux defaults"))
        bl_title.add_css_class("heading")
        bl_title.set_xalign(0)
        bl_text_box.append(bl_title)

        biglinux_card.append(bl_text_box)

        biglinux_btn = Gtk.Button(label=_("Restore"))
        biglinux_btn.add_css_class("suggested-action")
        biglinux_btn.add_css_class("pill")
        biglinux_btn.set_valign(Gtk.Align.CENTER)
        biglinux_btn.connect(
            "clicked",
            lambda _b: _confirm_reset(parent, dialog, entry, ResetMode.BIGLINUX_DEFAULT, on_complete),
        )
        biglinux_card.append(biglinux_btn)

        modes_box.append(biglinux_card)

    if config_exists or not skel_exists:
        program_card = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=12,
        )
        program_card.add_css_class("card")
        program_card.add_css_class("restore-desc-card")

        prog_icon = Gtk.Image.new_from_icon_name("restore-default-symbolic")
        prog_icon.set_pixel_size(24)
        prog_icon.set_valign(Gtk.Align.CENTER)
        program_card.append(prog_icon)

        prog_text_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=2,
        )
        prog_text_box.set_hexpand(True)
        prog_text_box.set_valign(Gtk.Align.CENTER)
        prog_title = Gtk.Label(label=_("Program defaults"))
        prog_title.add_css_class("heading")
        prog_title.set_xalign(0)
        prog_text_box.append(prog_title)

        program_card.append(prog_text_box)

        program_btn = Gtk.Button(label=_("Restore"))
        program_btn.add_css_class("suggested-action")
        program_btn.add_css_class("pill")
        program_btn.set_valign(Gtk.Align.CENTER)
        program_btn.connect(
            "clicked",
            lambda _b: _confirm_reset(parent, dialog, entry, ResetMode.PROGRAM_DEFAULT, on_complete),
        )
        program_card.append(program_btn)

        modes_box.append(program_card)

    content_box.append(modes_box)

    scroll.set_child(content_box)
    toolbar_view.set_content(scroll)
    dialog.set_content(toolbar_view)
    dialog.present()


def _confirm_reset(
    parent: Adw.ApplicationWindow,
    options_dialog: Adw.Window,
    entry: AppEntry,
    mode: ResetMode,
    on_complete: callable | None,
) -> None:
    """Show a destructive AlertDialog before proceeding."""

    if mode == ResetMode.BIGLINUX_DEFAULT:
        mode_label = _("BigLinux defaults")
    else:
        mode_label = _("program defaults")

    alert = Adw.AlertDialog()
    alert.set_heading(_("Restore settings?"))
    alert.set_body(
        _("All customizations for %s will be lost.\n\n"
          "Mode: %s\n\n"
          "You may need to restart the application to see the changes.")
        % (get_localized_name(entry), mode_label)
    )
    alert.set_close_response("cancel")

    alert.add_response("cancel", _("Cancel"))
    alert.add_response("restore", _("Restore"))
    alert.set_response_appearance("restore", Adw.ResponseAppearance.DESTRUCTIVE)

    alert.connect(
        "response",
        _on_confirm_response,
        parent,
        options_dialog,
        entry,
        mode,
        on_complete,
    )
    alert.present(options_dialog)


def _on_confirm_response(
    alert: Adw.AlertDialog,
    response: str,
    parent: Adw.ApplicationWindow,
    options_dialog: Adw.Window,
    entry: AppEntry,
    mode: ResetMode,
    on_complete: callable | None,
) -> None:
    if response != "restore":
        return

    # Check if app is running
    pids = get_running_pids(entry)
    if pids:
        _show_running_dialog(parent, options_dialog, entry, mode, on_complete)
        return

    # Close the options dialog and execute
    options_dialog.destroy()
    _execute_reset(parent, entry, mode, on_complete)


def _show_running_dialog(
    parent: Adw.ApplicationWindow,
    options_dialog: Adw.Window,
    entry: AppEntry,
    mode: ResetMode,
    on_complete: callable | None,
) -> None:
    """Warn that the app is running and offer to close it."""
    alert = Adw.AlertDialog()
    alert.set_heading(_("Application is running"))
    alert.set_body(
        _("%s is running and will be closed so that "
          "the restore can be completed.") % get_localized_name(entry)
    )

    alert.add_response("cancel", _("Cancel"))
    alert.add_response("close_and_restore", _("Close and restore"))
    alert.set_response_appearance("close_and_restore", Adw.ResponseAppearance.DESTRUCTIVE)
    alert.set_close_response("cancel")

    def on_response(_alert: Adw.AlertDialog, resp: str) -> None:
        if resp != "close_and_restore":
            return
        kill_app(entry)
        options_dialog.destroy()
        _execute_reset(parent, entry, mode, on_complete)

    alert.connect("response", on_response)
    alert.present(options_dialog)


def _execute_reset(
    parent: Adw.ApplicationWindow,
    entry: AppEntry,
    mode: ResetMode,
    on_complete: callable | None,
) -> None:
    """Run the reset in a background thread, then show results."""

    # Show a spinner dialog
    spinner_dialog = Adw.Dialog()
    spinner_dialog.set_title(_("Restoring…"))
    spinner_dialog.set_content_width(420)
    spinner_dialog.set_content_height(220)

    spinner_box = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL,
        spacing=16,
    )
    spinner_box.set_valign(Gtk.Align.CENTER)
    spinner_box.set_halign(Gtk.Align.CENTER)

    spinner = Adw.Spinner()
    spinner.set_size_request(48, 48)
    spinner_box.append(spinner)

    spinner_label = Gtk.Label(
        label=_("Restoring settings for %s…") % get_localized_name(entry)
    )
    spinner_label.add_css_class("title-4")
    spinner_box.append(spinner_label)

    toolbar = Adw.ToolbarView()
    toolbar.add_top_bar(Adw.HeaderBar())
    toolbar.set_content(spinner_box)
    spinner_dialog.set_child(toolbar)
    spinner_dialog.present(parent)

    def _worker() -> None:
        result = reset_app(entry, mode)
        GLib.idle_add(_on_reset_done, result, spinner_dialog, parent, entry, on_complete)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()


def _on_reset_done(
    result: ResetResult,
    spinner_dialog: Adw.Dialog,
    parent: Adw.ApplicationWindow,
    entry: AppEntry,
    on_complete: callable | None,
) -> bool:
    """Called on the main thread after reset completes."""
    spinner_dialog.close()

    if result.success:
        _show_success_dialog(parent, entry, result)
    else:
        _show_error_dialog(parent, entry, result)

    if on_complete:
        on_complete(result)

    return GLib.SOURCE_REMOVE


def _build_app_icon_with_badge(entry: AppEntry) -> Gtk.Overlay:
    """Build the app icon (48px) with a small check badge in the upper-right."""
    import os

    overlay = Gtk.Overlay()

    # Main app icon
    if entry.icon.startswith("/") and os.path.isfile(entry.icon):
        app_icon = Gtk.Image.new_from_file(entry.icon)
    elif entry.icon:
        app_icon = Gtk.Image.new_from_icon_name(entry.icon)
    else:
        app_icon = Gtk.Image.new_from_icon_name("application-x-executable")
    app_icon.set_pixel_size(48)
    overlay.set_child(app_icon)

    # Small check badge (16px) upper-right
    badge = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
    badge.set_pixel_size(16)
    badge.add_css_class("success")
    badge.set_halign(Gtk.Align.END)
    badge.set_valign(Gtk.Align.START)
    overlay.add_overlay(badge)

    return overlay


def _show_success_dialog(
    parent: Adw.ApplicationWindow,
    entry: AppEntry,
    result: ResetResult,
) -> None:
    """Show a compact success dialog with the app icon + check badge above text."""

    dialog = Adw.Dialog()
    dialog.set_content_width(360)
    dialog.set_content_height(-1)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    box.set_margin_top(24)
    box.set_margin_bottom(24)
    box.set_margin_start(24)
    box.set_margin_end(24)
    box.set_halign(Gtk.Align.CENTER)
    box.set_valign(Gtk.Align.CENTER)

    # App icon with check badge — above text
    icon_widget = _build_app_icon_with_badge(entry)
    icon_widget.set_halign(Gtk.Align.CENTER)
    box.append(icon_widget)

    # Heading
    heading = Gtk.Label(label=_("Settings restored"))
    heading.add_css_class("title-3")
    heading.set_halign(Gtk.Align.CENTER)
    box.append(heading)

    # Description
    if entry.logout_required:
        desc_text = _(
            "Settings for %s have been restored.\n"
            "You need to log out to complete the process."
        ) % get_localized_name(entry)
    else:
        desc_text = _(
            "Settings for %s have been restored successfully."
        ) % get_localized_name(entry)

    desc = Gtk.Label(label=desc_text)
    desc.add_css_class("dim-label")
    desc.set_wrap(True)
    desc.set_halign(Gtk.Align.CENTER)
    desc.set_justify(Gtk.Justification.CENTER)
    box.append(desc)

    # Buttons
    btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    btn_box.set_halign(Gtk.Align.CENTER)
    btn_box.set_margin_top(8)

    if entry.logout_required:
        close_btn = Gtk.Button(label=_("Close"))
        close_btn.connect("clicked", lambda _b: dialog.close())
        btn_box.append(close_btn)

        logout_btn = Gtk.Button(label=_("Log out"))
        logout_btn.add_css_class("destructive-action")
        logout_btn.connect("clicked", lambda _b: _logout_session())
        btn_box.append(logout_btn)
    else:
        ok_btn = Gtk.Button(label=_("OK"))
        ok_btn.add_css_class("suggested-action")
        ok_btn.add_css_class("pill")
        ok_btn.connect("clicked", lambda _b: dialog.close())
        btn_box.append(ok_btn)

    box.append(btn_box)
    dialog.set_child(box)
    dialog.present(parent)


def _show_error_dialog(
    parent: Adw.ApplicationWindow,
    entry: AppEntry,
    result: ResetResult,
) -> None:
    """Show a compact error dialog."""

    dialog = Adw.AlertDialog()
    dialog.set_heading(_("Restore error"))
    dialog.set_body(
        _("An error occurred while restoring settings for %s:\n%s")
        % (get_localized_name(entry), result.message)
    )
    dialog.add_response("ok", _("Close"))
    dialog.set_close_response("ok")
    dialog.present(parent)


def _logout_session() -> None:
    """Attempt to logout from the current desktop session."""
    import os
    import subprocess

    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()

    logout_commands = {
        "KDE": ["qdbus", "org.kde.ksmserver", "/KSMServer", "logout", "1", "0", "2"],
        "PLASMA": ["qdbus", "org.kde.ksmserver", "/KSMServer", "logout", "1", "0", "2"],
        "GNOME": ["gnome-session-quit", "--no-prompt"],
        "XFCE": ["xfce4-session-logout", "--logout"],
        "X-CINNAMON": ["cinnamon-session-quit", "--logout", "--no-prompt"],
        "CINNAMON": ["cinnamon-session-quit", "--logout", "--no-prompt"],
        "MATE": ["mate-session-save", "--logout"],
        "BUDGIE": ["budgie-session", "--logout"],
        "DEEPIN": ["dbus-send", "--session", "--dest=com.deepin.SessionManager",
                    "--type=method_call", "/com/deepin/SessionManager",
                    "com.deepin.SessionManager.RequestLogout"],
    }

    for de_key, cmd in logout_commands.items():
        if de_key in desktop:
            try:
                subprocess.Popen(cmd)
            except FileNotFoundError:
                pass
            return

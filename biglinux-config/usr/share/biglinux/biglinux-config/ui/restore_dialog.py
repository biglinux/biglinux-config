"""Restore dialog — modal for choosing reset mode and confirming."""

from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from utils import _, set_label
from data.app_registry import AppEntry
from backend.reset_manager import (
    ResetMode,
    ResetResult,
    format_size,
    get_config_size,
    get_running_pids,
    has_config,
    has_skel,
    kill_app,
    reset_app,
)


def show_restore_dialog(
    parent: Adw.ApplicationWindow,
    entry: AppEntry,
    on_complete: callable | None = None,
) -> None:
    """Present the restore options dialog for an application."""

    dialog = Adw.Dialog()
    dialog.set_title(_("Restore Settings"))
    dialog.set_content_width(540)
    dialog.set_content_height(480)

    toolbar_view = Adw.ToolbarView()

    header = Adw.HeaderBar()
    header.set_show_end_title_buttons(True)
    toolbar_view.add_top_bar(header)

    content_box = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL,
        spacing=24,
    )
    content_box.set_margin_top(12)
    content_box.set_margin_bottom(24)
    content_box.set_margin_start(24)
    content_box.set_margin_end(24)

    # App info header
    app_icon = Gtk.Image()
    app_icon.set_pixel_size(64)
    if entry.icon.startswith("/"):
        import os
        if os.path.isfile(entry.icon):
            app_icon.set_from_file(entry.icon)
        else:
            app_icon.set_from_icon_name("application-x-executable")
    else:
        app_icon.set_from_icon_name(entry.icon)
    app_icon.set_halign(Gtk.Align.CENTER)

    app_name_label = Gtk.Label(label=entry.name)
    app_name_label.add_css_class("title-1")
    app_name_label.set_halign(Gtk.Align.CENTER)

    content_box.append(app_icon)
    content_box.append(app_name_label)

    # Config info
    config_exists = has_config(entry)
    skel_exists = has_skel(entry)

    if config_exists:
        size = get_config_size(entry)
        paths_display = "\n".join(f"  • {p}" for p in entry.config_paths[:5])
        if len(entry.config_paths) > 5:
            paths_display += f"\n  … +{len(entry.config_paths) - 5}"
        info_text = _("Settings size: %s") % format_size(size)
        info_label = Gtk.Label(label=info_text)
        info_label.add_css_class("dim-label")
        info_label.set_halign(Gtk.Align.CENTER)
        content_box.append(info_label)

    # Options group
    group = Adw.PreferencesGroup()
    group.set_title(_("Choose restore mode"))
    set_label(group, _("Restore options"))

    # Option 1: BigLinux default (from skel)
    if skel_exists:
        skel_row = Adw.ActionRow()
        skel_row.set_title(_("Restore BigLinux defaults"))
        skel_row.set_subtitle(
            _("Restores BigLinux settings from /etc/skel")
        )
        skel_row.set_activatable(True)
        set_label(skel_row, _("Restore BigLinux default settings for %s") % entry.name)

        skel_icon = Gtk.Image.new_from_icon_name("biglinux-symbolic")
        skel_icon.set_pixel_size(28)
        skel_row.add_prefix(skel_icon)

        arrow_skel = Gtk.Image.new_from_icon_name("go-next-symbolic")
        skel_row.add_suffix(arrow_skel)

        skel_row.connect(
            "activated",
            lambda _r: _confirm_reset(parent, dialog, entry, ResetMode.BIGLINUX_DEFAULT, on_complete),
        )
        group.add(skel_row)

    # Option 2: Program default (remove dotfiles)
    if config_exists or not skel_exists:
        default_row = Adw.ActionRow()
        default_row.set_title(_("Restore program defaults"))
        default_row.set_subtitle(
            _("Removes settings so the program recreates its defaults")
        )
        default_row.set_activatable(True)
        set_label(default_row, _("Restore default settings for %s") % entry.name)

        default_icon = Gtk.Image.new_from_icon_name("restore-default-symbolic")
        default_icon.set_pixel_size(28)
        default_row.add_prefix(default_icon)

        arrow_default = Gtk.Image.new_from_icon_name("go-next-symbolic")
        default_row.add_suffix(arrow_default)

        default_row.connect(
            "activated",
            lambda _r: _confirm_reset(parent, dialog, entry, ResetMode.PROGRAM_DEFAULT, on_complete),
        )
        group.add(default_row)

    content_box.append(group)

    # If no config and no skel — nothing to do
    if not config_exists and not skel_exists:
        empty_label = Gtk.Label()
        empty_label.set_markup(
            f'<span size="large">{_("No settings found for this application.")}</span>'
        )
        empty_label.set_wrap(True)
        empty_label.set_halign(Gtk.Align.CENTER)
        content_box.append(empty_label)

    toolbar_view.set_content(content_box)
    dialog.set_child(toolbar_view)
    dialog.present(parent)


def _confirm_reset(
    parent: Adw.ApplicationWindow,
    options_dialog: Adw.Dialog,
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
        % (entry.name, mode_label)
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
    alert.present(parent)


def _on_confirm_response(
    alert: Adw.AlertDialog,
    response: str,
    parent: Adw.ApplicationWindow,
    options_dialog: Adw.Dialog,
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
    options_dialog.close()
    _execute_reset(parent, entry, mode, on_complete)


def _show_running_dialog(
    parent: Adw.ApplicationWindow,
    options_dialog: Adw.Dialog,
    entry: AppEntry,
    mode: ResetMode,
    on_complete: callable | None,
) -> None:
    """Warn that the app is running and offer to close it."""
    alert = Adw.AlertDialog()
    alert.set_heading(_("Application is running"))
    alert.set_body(
        _("%s is running and will be closed so that "
          "the restore can be completed.") % entry.name
    )

    alert.add_response("cancel", _("Cancel"))
    alert.add_response("close_and_restore", _("Close and restore"))
    alert.set_response_appearance("close_and_restore", Adw.ResponseAppearance.DESTRUCTIVE)
    alert.set_close_response("cancel")

    def on_response(_alert: Adw.AlertDialog, resp: str) -> None:
        if resp != "close_and_restore":
            return
        kill_app(entry)
        options_dialog.close()
        _execute_reset(parent, entry, mode, on_complete)

    alert.connect("response", on_response)
    alert.present(parent)


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
        label=_("Restoring settings for %s…") % entry.name
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
        ) % entry.name
    else:
        desc_text = _(
            "Settings for %s have been restored successfully."
        ) % entry.name

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
        % (entry.name, result.message)
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

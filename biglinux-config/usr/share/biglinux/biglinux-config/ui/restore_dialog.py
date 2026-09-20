"""Restore dialog — modal for choosing reset mode and confirming."""

from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gio, Gtk

from utils import _, ngettext, set_label
from data.app_registry import AppEntry
from ui import backup_dialog
from backend.app_detector import get_localized_name
from backend.reset_manager import (
    ResetMode,
    ResetResult,
    ResetStatus,
    format_size,
    get_running_pids,
    has_config,
    has_skel,
    kill_app,
    reset_app,
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

    config_exists = has_config(entry)
    skel_exists = has_skel(entry)

    dialog = Adw.Window()
    dialog.set_default_size(420, 560)
    dialog.set_modal(True)
    dialog.set_transient_for(parent)

    # Flat header that blends into the content (no visible title bar chrome).
    toolbar_view = Adw.ToolbarView()
    toolbar_view.set_top_bar_style(Adw.ToolbarStyle.FLAT)
    toolbar_view.set_extend_content_to_top_edge(True)
    header = Adw.HeaderBar()
    header.set_show_title(False)
    toolbar_view.add_top_bar(header)

    # Content scrolls only if it genuinely overflows; otherwise the window
    # shrink-wraps to the content (no dead space, no needless scrollbar).
    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroll.set_propagate_natural_height(True)
    scroll.set_max_content_height(760)
    scroll.set_vexpand(True)

    clamp = Adw.Clamp()
    clamp.set_maximum_size(380)
    clamp.set_tightening_threshold(380)

    content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
    content_box.set_margin_top(4)
    content_box.set_margin_bottom(24)
    content_box.set_margin_start(12)
    content_box.set_margin_end(12)

    # ── Header block: icon + name + one-line summary ──
    head_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    head_box.set_halign(Gtk.Align.CENTER)
    head_box.set_margin_top(8)
    head_box.set_margin_bottom(2)

    app_icon = Gtk.Image()
    app_icon.set_pixel_size(72)
    if entry.icon.startswith("/"):
        if os.path.isfile(entry.icon):
            app_icon.set_from_file(entry.icon)
        else:
            app_icon.set_from_icon_name("application-x-executable")
    else:
        app_icon.set_from_icon_name(entry.icon)
    app_icon.set_halign(Gtk.Align.CENTER)
    head_box.append(app_icon)

    app_name_label = Gtk.Label(label=get_localized_name(entry))
    app_name_label.add_css_class("title-2")
    app_name_label.set_halign(Gtk.Align.CENTER)
    app_name_label.set_justify(Gtk.Justification.CENTER)
    app_name_label.set_wrap(True)
    head_box.append(app_name_label)

    # Compute path sizes once (used by summary and the details expander).
    def _path_size(raw_path: str) -> int:
        expanded = os.path.expanduser(raw_path)
        targets = glob.glob(expanded) if ("*" in expanded or "?" in expanded) else [expanded]
        total = 0
        for target in targets:
            if os.path.isdir(target) and not os.path.islink(target):
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

    existing_paths = [p for p in entry.config_paths if os.path.lexists(os.path.expanduser(p))]
    path_sizes = {p: _path_size(p) for p in existing_paths}
    total_size = sum(path_sizes.values())

    if existing_paths:
        n = len(existing_paths)
        count_base = ngettext("%d item", "%d items", n)
        summary_text = f"{count_base % n} · {format_size(total_size)}"
    else:
        summary_text = _("No settings stored yet")

    summary_label = Gtk.Label(label=summary_text)
    summary_label.add_css_class("dim-label")
    summary_label.set_halign(Gtk.Align.CENTER)
    head_box.append(summary_label)
    content_box.append(head_box)

    # ── Empty state ──
    if not config_exists and not skel_exists:
        status = Adw.StatusPage()
        status.set_icon_name("folder-symbolic")
        status.set_title(_("Nothing to restore"))
        status.set_description(
            _("This application has no settings stored yet."))
        status.set_vexpand(True)
        content_box.append(status)

        close_btn = Gtk.Button(label=_("Close"))
        close_btn.set_halign(Gtk.Align.CENTER)
        close_btn.add_css_class("pill")
        close_btn.connect("clicked", lambda _b: dialog.close())
        content_box.append(close_btn)

        clamp.set_child(content_box)
        scroll.set_child(clamp)
        toolbar_view.set_content(scroll)
        dialog.set_content(toolbar_view)
        dialog.present()
        return

    # Helper: build a consistent activatable action row.
    def _action_row(icon_name, title, subtitle, on_activate,
                    sensitive=True, accent=None):
        row = Adw.ActionRow()
        row.set_title(title)
        if subtitle:
            row.set_subtitle(subtitle)
        row.set_title_lines(1)
        icon = Gtk.Image.new_from_icon_name(icon_name)
        if accent:
            icon.add_css_class(accent)
        row.add_prefix(icon)
        chevron = Gtk.Image.new_from_icon_name("go-next-symbolic")
        chevron.add_css_class("dim-label")
        row.add_suffix(chevron)
        row.set_activatable(True)
        row.set_sensitive(sensitive)
        row.connect("activated", lambda _r: on_activate())
        return row

    # ── Backup (non-destructive) ──
    backup_group = Adw.PreferencesGroup()
    backup_group.set_title(_("Backup"))

    backup_group.add(_action_row(
        "document-save-symbolic",
        _("Export settings…"),
        _("Save this application's settings to a file")
        if config_exists else _("No settings to export yet"),
        lambda: backup_dialog.show_single_export(parent, entry),
        sensitive=config_exists,
    ))
    backup_group.add(_action_row(
        "document-open-symbolic",
        _("Import settings…"),
        _("Restore settings from a backup file"),
        lambda: backup_dialog.show_single_import(parent, entry),
    ))
    content_box.append(backup_group)

    # ── Restore (destructive) ──
    restore_group = Adw.PreferencesGroup()
    restore_group.set_title(_("Restore defaults"))
    restore_group.set_description(
        _("These actions replace your current settings."))

    if skel_exists:
        restore_group.add(_action_row(
            "biglinux-symbolic",
            _("BigLinux defaults"),
            _("Apply the settings recommended by BigLinux"),
            lambda: _confirm_reset(parent, dialog, entry,
                                   ResetMode.BIGLINUX_DEFAULT, on_complete),
        ))

    if config_exists or not skel_exists:
        restore_group.add(_action_row(
            "restore-default-symbolic",
            _("Program defaults"),
            _("Remove customizations so the app resets itself"),
            lambda: _confirm_reset(parent, dialog, entry,
                                   ResetMode.PROGRAM_DEFAULT, on_complete),
            accent="error",
        ))
    content_box.append(restore_group)

    # ── Details: affected files (collapsed) ──
    if existing_paths:
        details_group = Adw.PreferencesGroup()
        expander = Adw.ExpanderRow()
        expander.set_title(_("Files that will be affected"))
        expander.set_subtitle(summary_text)
        exp_icon = Gtk.Image.new_from_icon_name("view-list-symbolic")
        expander.add_prefix(exp_icon)

        for cfg_path in existing_paths:
            row = Adw.ActionRow()
            row.add_css_class("property")
            row.set_title(cfg_path)
            row.set_title_lines(1)
            row.set_subtitle(format_size(path_sizes.get(cfg_path, 0)))
            row.set_subtitle_lines(1)
            prefix_icon = Gtk.Image.new_from_icon_name(_get_mimetype_icon(cfg_path))
            row.add_prefix(prefix_icon)
            open_btn = Gtk.Button()
            open_btn.set_icon_name("folder-open-symbolic")
            open_btn.set_valign(Gtk.Align.CENTER)
            open_btn.add_css_class("flat")
            open_btn.set_tooltip_text(_("Open in file manager"))
            set_label(open_btn, _("Open %s in file manager") % cfg_path)
            open_btn.connect("clicked",
                             lambda _b, p=cfg_path: _open_path_in_filemanager(p))
            row.add_suffix(open_btn)
            expander.add_row(row)

        details_group.add(expander)
        content_box.append(details_group)

    clamp.set_child(content_box)
    scroll.set_child(clamp)
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

    # Offer a safety backup of the current configuration first (recommended).
    backup_check = Gtk.CheckButton(
        label=_("Create a backup of the current settings before restoring")
    )
    backup_check.set_active(True)
    backup_check.set_margin_top(6)
    if not has_config(entry):
        # Nothing to back up.
        backup_check.set_active(False)
        backup_check.set_sensitive(False)
    alert.set_extra_child(backup_check)

    alert.add_response("cancel", _("Cancel"))
    alert.add_response("restore", _("Restore"))
    alert.set_response_appearance("restore", Adw.ResponseAppearance.DESTRUCTIVE)

    def on_response(_alert: Adw.AlertDialog, response: str) -> None:
        if response != "restore":
            return
        backup_first = backup_check.get_active()
        pids = get_running_pids(entry)
        if pids:
            _show_running_dialog(parent, options_dialog, entry, mode,
                                 on_complete, backup_first)
            return
        options_dialog.destroy()
        _execute_reset(parent, entry, mode, on_complete, backup_first)

    alert.connect("response", on_response)
    alert.present(options_dialog)


def _show_running_dialog(
    parent: Adw.ApplicationWindow,
    options_dialog: Adw.Window,
    entry: AppEntry,
    mode: ResetMode,
    on_complete: callable | None,
    backup_first: bool = False,
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
        _execute_reset(parent, entry, mode, on_complete, backup_first)

    alert.connect("response", on_response)
    alert.present(options_dialog)


def _execute_reset(
    parent: Adw.ApplicationWindow,
    entry: AppEntry,
    mode: ResetMode,
    on_complete: callable | None,
    backup_first: bool = False,
) -> None:
    """Run the reset in a background thread, then show results."""

    cancel_event = threading.Event()

    # Show a spinner dialog
    spinner_dialog = Adw.Dialog()
    spinner_dialog.set_title(_("Restoring…"))
    spinner_dialog.set_content_width(420)
    spinner_dialog.set_content_height(240)

    spinner_box = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL,
        spacing=16,
    )
    spinner_box.set_valign(Gtk.Align.CENTER)
    spinner_box.set_halign(Gtk.Align.CENTER)
    spinner_box.set_margin_start(24)
    spinner_box.set_margin_end(24)

    spinner = Adw.Spinner()
    spinner.set_size_request(48, 48)
    spinner_box.append(spinner)

    label_text = (
        _("Backing up, then restoring settings for %s…")
        if backup_first else _("Restoring settings for %s…")
    ) % get_localized_name(entry)
    spinner_label = Gtk.Label(label=label_text)
    spinner_label.add_css_class("title-4")
    spinner_label.set_wrap(True)
    spinner_label.set_justify(Gtk.Justification.CENTER)
    spinner_box.append(spinner_label)

    cancel_btn = Gtk.Button(label=_("Cancel"))
    cancel_btn.set_halign(Gtk.Align.CENTER)
    cancel_btn.connect("clicked", lambda _b: cancel_event.set())
    spinner_box.append(cancel_btn)

    # Closing the dialog also cancels the worker.
    spinner_dialog.connect("closed", lambda _d: cancel_event.set())

    toolbar = Adw.ToolbarView()
    toolbar.add_top_bar(Adw.HeaderBar())
    toolbar.set_content(spinner_box)
    spinner_dialog.set_child(toolbar)
    spinner_dialog.present(parent)

    def _worker() -> None:
        result = reset_app(entry, mode, backup_first=backup_first,
                           cancel_event=cancel_event)
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
    elif result.status is ResetStatus.CANCELLED:
        # User cancelled — nothing was changed (rolled back). Stay silent.
        pass
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

    # Safety-backup note (if one was created before the reset).
    if getattr(result, "backup_path", ""):
        backup_note = Gtk.Label(
            label=_("A backup of your previous settings was saved to:\n%s")
            % result.backup_path
        )
        backup_note.add_css_class("dim-label")
        backup_note.add_css_class("caption")
        backup_note.set_wrap(True)
        backup_note.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        backup_note.set_halign(Gtk.Align.CENTER)
        backup_note.set_justify(Gtk.Justification.CENTER)
        backup_note.set_selectable(True)
        box.append(backup_note)

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

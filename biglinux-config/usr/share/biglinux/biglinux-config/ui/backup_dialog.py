"""Backup/restore dialog — export and import dotfiles as .tar.gz."""

from __future__ import annotations

import os
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

from utils import _, set_label
from data.app_registry import AppEntry
from backend.backup_manager import (
    BackupResult,
    RestoreFromBackupResult,
    export_backup,
    get_default_backup_name,
    import_backup,
    read_backup_manifest,
)
from backend.reset_manager import format_size, get_config_size, has_config


# ---------------------------------------------------------------------------
# Export dialog
# ---------------------------------------------------------------------------

def show_export_dialog(
    parent: Adw.ApplicationWindow,
    apps: list[AppEntry],
) -> None:
    """Present the export dialog with app selection checkboxes."""

    # Filter to apps that actually have config on disk
    available = [a for a in apps if has_config(a)]
    available.sort(key=lambda a: a.name.lower())

    dialog = Adw.Dialog()
    dialog.set_title(_("Export Settings"))
    dialog.set_content_width(560)
    dialog.set_content_height(600)

    toolbar_view = Adw.ToolbarView()
    header = Adw.HeaderBar()
    toolbar_view.add_top_bar(header)

    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroll.set_vexpand(True)

    content_box = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL,
        spacing=16,
    )
    content_box.set_margin_top(12)
    content_box.set_margin_bottom(24)
    content_box.set_margin_start(24)
    content_box.set_margin_end(24)

    # Description
    desc = Gtk.Label(
        label=_("Select the applications whose settings you want to export. "
                "A .tar.gz archive will be created with the dotfiles."),
    )
    desc.set_wrap(True)
    desc.set_xalign(0)
    desc.add_css_class("dim-label")
    content_box.append(desc)

    # Full directory checkbox
    full_dir_row = Adw.SwitchRow()
    full_dir_row.set_title(_("Copy full directories"))
    full_dir_row.set_subtitle(
        _("Include all files in each config directory, not just the listed paths")
    )

    options_group = Adw.PreferencesGroup()
    options_group.set_title(_("Options"))
    options_group.add(full_dir_row)
    content_box.append(options_group)

    # App selection group
    apps_group = Adw.PreferencesGroup()
    apps_group.set_title(_("Applications (%d available)") % len(available))
    set_label(apps_group, _("Select applications to export"))

    # Select all / deselect all buttons
    select_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    select_box.set_halign(Gtk.Align.END)

    select_all_btn = Gtk.Button(label=_("Select all"))
    select_all_btn.add_css_class("flat")
    select_box.append(select_all_btn)

    deselect_all_btn = Gtk.Button(label=_("Deselect all"))
    deselect_all_btn.add_css_class("flat")
    select_box.append(deselect_all_btn)

    content_box.append(select_box)

    # Checkboxes for each app
    check_rows: list[tuple[Adw.ActionRow, Gtk.CheckButton, AppEntry]] = []

    for app_entry in available:
        row = Adw.ActionRow()
        row.set_title(app_entry.name)

        size = get_config_size(app_entry)
        paths_str = ", ".join(app_entry.config_paths[:3])
        if len(app_entry.config_paths) > 3:
            paths_str += f" (+{len(app_entry.config_paths) - 3})"
        row.set_subtitle(f"{format_size(size)} — {paths_str}")

        icon = Gtk.Image.new_from_icon_name(
            app_entry.icon if not app_entry.icon.startswith("/") else "application-x-executable"
        )
        icon.set_pixel_size(32)
        row.add_prefix(icon)

        check = Gtk.CheckButton()
        check.set_active(True)
        set_label(check, _("Include %s") % app_entry.name)
        row.add_suffix(check)
        row.set_activatable_widget(check)

        apps_group.add(row)
        check_rows.append((row, check, app_entry))

    content_box.append(apps_group)

    # Select all / deselect all handlers
    def _select_all(_btn: Gtk.Button) -> None:
        for _, chk, _ in check_rows:
            chk.set_active(True)

    def _deselect_all(_btn: Gtk.Button) -> None:
        for _, chk, _ in check_rows:
            chk.set_active(False)

    select_all_btn.connect("clicked", _select_all)
    deselect_all_btn.connect("clicked", _deselect_all)

    scroll.set_child(content_box)
    toolbar_view.set_content(scroll)

    # Bottom bar with export button
    bottom_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    bottom_box.set_margin_top(12)
    bottom_box.set_margin_bottom(12)
    bottom_box.set_margin_start(24)
    bottom_box.set_margin_end(24)
    bottom_box.set_halign(Gtk.Align.END)

    cancel_btn = Gtk.Button(label=_("Cancel"))
    cancel_btn.connect("clicked", lambda _b: dialog.close())
    bottom_box.append(cancel_btn)

    export_btn = Gtk.Button(label=_("Export…"))
    export_btn.add_css_class("suggested-action")
    set_label(export_btn, _("Choose destination and export"))
    bottom_box.append(export_btn)

    toolbar_view.add_bottom_bar(bottom_box)

    def _on_export_clicked(_btn: Gtk.Button) -> None:
        selected = [entry for _, chk, entry in check_rows if chk.get_active()]
        if not selected:
            return
        full_dir = full_dir_row.get_active()
        _pick_save_location(parent, dialog, selected, full_dir)

    export_btn.connect("clicked", _on_export_clicked)

    dialog.set_child(toolbar_view)
    dialog.present(parent)


def _pick_save_location(
    parent: Adw.ApplicationWindow,
    export_dialog: Adw.Dialog,
    entries: list[AppEntry],
    full_directory: bool,
) -> None:
    """Open a native file chooser to pick the archive save location."""
    file_dialog = Gtk.FileDialog()
    file_dialog.set_title(_("Save backup as"))
    file_dialog.set_initial_name(get_default_backup_name())

    # Default to ~/Documents or ~/
    docs_dir = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOCUMENTS)
    if docs_dir:
        file_dialog.set_initial_folder(Gio.File.new_for_path(docs_dir))

    gz_filter = Gtk.FileFilter()
    gz_filter.set_name(_("Compressed archives (*.tar.gz)"))
    gz_filter.add_pattern("*.tar.gz")
    filter_list = Gio.ListStore.new(Gtk.FileFilter)
    filter_list.append(gz_filter)
    file_dialog.set_filters(filter_list)
    file_dialog.set_default_filter(gz_filter)

    def _on_save_response(dialog_obj: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
        try:
            gfile = dialog_obj.save_finish(result)
        except GLib.Error:
            return
        path = gfile.get_path()
        if not path:
            return
        if not path.endswith(".tar.gz"):
            path += ".tar.gz"
        export_dialog.close()
        _execute_export(parent, entries, path, full_directory)

    file_dialog.save(parent, None, _on_save_response)


def _execute_export(
    parent: Adw.ApplicationWindow,
    entries: list[AppEntry],
    archive_path: str,
    full_directory: bool,
) -> None:
    """Run the export in a background thread with a spinner dialog."""
    spinner_dialog = Adw.Dialog()
    spinner_dialog.set_title(_("Exporting…"))
    spinner_dialog.set_content_width(420)
    spinner_dialog.set_content_height(220)

    spinner_box = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL, spacing=16
    )
    spinner_box.set_valign(Gtk.Align.CENTER)
    spinner_box.set_halign(Gtk.Align.CENTER)

    spinner = Adw.Spinner()
    spinner.set_size_request(48, 48)
    spinner_box.append(spinner)

    spinner_label = Gtk.Label(
        label=_("Exporting settings for %d applications…") % len(entries)
    )
    spinner_label.add_css_class("title-4")
    spinner_box.append(spinner_label)

    toolbar = Adw.ToolbarView()
    toolbar.add_top_bar(Adw.HeaderBar())
    toolbar.set_content(spinner_box)
    spinner_dialog.set_child(toolbar)
    spinner_dialog.present(parent)

    def _worker() -> None:
        result = export_backup(entries, archive_path, full_directory)
        GLib.idle_add(_on_export_done, result, spinner_dialog, parent)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()


def _on_export_done(
    result: BackupResult,
    spinner_dialog: Adw.Dialog,
    parent: Adw.ApplicationWindow,
) -> bool:
    spinner_dialog.close()

    result_dialog = Adw.Dialog()
    result_dialog.set_content_width(540)
    result_dialog.set_content_height(380)

    toolbar = Adw.ToolbarView()
    toolbar.add_top_bar(Adw.HeaderBar())

    if result.success:
        status = Adw.StatusPage()
        status.set_icon_name("document-save-symbolic")
        status.set_title(_("Backup created!"))
        status.set_description(
            _("%d applications exported (%s)\n\nSaved to:\n%s")
            % (result.app_count, format_size(result.total_size), result.archive_path)
        )

        ok_btn = Gtk.Button(label=_("OK"))
        ok_btn.set_halign(Gtk.Align.CENTER)
        ok_btn.add_css_class("pill")
        ok_btn.add_css_class("suggested-action")
        ok_btn.connect("clicked", lambda _b: result_dialog.close())
        status.set_child(ok_btn)
    else:
        status = Adw.StatusPage()
        status.set_icon_name("dialog-error-symbolic")
        status.set_title(_("Export error"))
        status.set_description(
            _("An error occurred while creating the backup:\n%s") % result.message
        )
        ok_btn = Gtk.Button(label=_("Close"))
        ok_btn.set_halign(Gtk.Align.CENTER)
        ok_btn.add_css_class("pill")
        ok_btn.connect("clicked", lambda _b: result_dialog.close())
        status.set_child(ok_btn)

    toolbar.set_content(status)
    result_dialog.set_child(toolbar)
    result_dialog.present(parent)

    return GLib.SOURCE_REMOVE


# ---------------------------------------------------------------------------
# Import dialog
# ---------------------------------------------------------------------------

def show_import_dialog(parent: Adw.ApplicationWindow) -> None:
    """Open a file chooser to select a backup archive, then show import options."""
    file_dialog = Gtk.FileDialog()
    file_dialog.set_title(_("Open backup file"))

    gz_filter = Gtk.FileFilter()
    gz_filter.set_name(_("BigLinux backups (*.tar.gz)"))
    gz_filter.add_pattern("*.tar.gz")
    filter_list = Gio.ListStore.new(Gtk.FileFilter)
    filter_list.append(gz_filter)
    file_dialog.set_filters(filter_list)
    file_dialog.set_default_filter(gz_filter)

    docs_dir = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOCUMENTS)
    if docs_dir:
        file_dialog.set_initial_folder(Gio.File.new_for_path(docs_dir))

    def _on_open_response(dialog_obj: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
        try:
            gfile = dialog_obj.open_finish(result)
        except GLib.Error:
            return
        path = gfile.get_path()
        if path:
            _show_import_options(parent, path)

    file_dialog.open(parent, None, _on_open_response)


def _show_import_options(
    parent: Adw.ApplicationWindow,
    archive_path: str,
) -> None:
    """Read the manifest and show a dialog with selectable apps to restore."""
    manifest = read_backup_manifest(archive_path)
    if manifest is None:
        _show_import_error(parent, _("This file is not a valid BigLinux backup archive."))
        return

    apps_in_backup = manifest.get("apps", [])
    if not apps_in_backup:
        _show_import_error(parent, _("The backup archive contains no application settings."))
        return

    dialog = Adw.Dialog()
    dialog.set_title(_("Import Settings"))
    dialog.set_content_width(560)
    dialog.set_content_height(550)

    toolbar_view = Adw.ToolbarView()
    header = Adw.HeaderBar()
    toolbar_view.add_top_bar(header)

    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroll.set_vexpand(True)

    content_box = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL, spacing=16
    )
    content_box.set_margin_top(12)
    content_box.set_margin_bottom(24)
    content_box.set_margin_start(24)
    content_box.set_margin_end(24)

    # Backup info
    ts = manifest.get("timestamp", "?")
    hostname = manifest.get("hostname", "?")
    full_dir = manifest.get("full_directory", False)

    info_label = Gtk.Label()
    info_label.set_markup(
        _("<b>Backup from:</b> %s\n<b>Host:</b> %s\n<b>Full directories:</b> %s")
        % (ts, hostname, _("Yes") if full_dir else _("No"))
    )
    info_label.set_xalign(0)
    info_label.set_wrap(True)
    info_label.add_css_class("dim-label")
    content_box.append(info_label)

    # Warning banner
    banner = Adw.Banner()
    banner.set_title(
        _("Importing will overwrite existing settings for selected applications.")
    )
    banner.set_revealed(True)
    content_box.append(banner)

    # App selection
    apps_group = Adw.PreferencesGroup()
    apps_group.set_title(_("Applications in backup (%d)") % len(apps_in_backup))

    select_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    select_box.set_halign(Gtk.Align.END)

    select_all_btn = Gtk.Button(label=_("Select all"))
    select_all_btn.add_css_class("flat")
    select_box.append(select_all_btn)

    deselect_all_btn = Gtk.Button(label=_("Deselect all"))
    deselect_all_btn.add_css_class("flat")
    select_box.append(deselect_all_btn)

    content_box.append(select_box)

    check_rows: list[tuple[Gtk.CheckButton, str, str]] = []  # (check, app_id, name)

    for app_info in apps_in_backup:
        row = Adw.ActionRow()
        row.set_title(app_info["name"])
        paths_str = ", ".join(app_info["paths"][:3])
        if len(app_info["paths"]) > 3:
            paths_str += f" (+{len(app_info['paths']) - 3})"
        row.set_subtitle(paths_str)

        check = Gtk.CheckButton()
        check.set_active(True)
        set_label(check, _("Include %s") % app_info["name"])
        row.add_suffix(check)
        row.set_activatable_widget(check)

        apps_group.add(row)
        check_rows.append((check, app_info["app_id"], app_info["name"]))

    content_box.append(apps_group)

    def _select_all(_btn: Gtk.Button) -> None:
        for chk, _, _ in check_rows:
            chk.set_active(True)

    def _deselect_all(_btn: Gtk.Button) -> None:
        for chk, _, _ in check_rows:
            chk.set_active(False)

    select_all_btn.connect("clicked", _select_all)
    deselect_all_btn.connect("clicked", _deselect_all)

    scroll.set_child(content_box)
    toolbar_view.set_content(scroll)

    # Bottom bar
    bottom_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    bottom_box.set_margin_top(12)
    bottom_box.set_margin_bottom(12)
    bottom_box.set_margin_start(24)
    bottom_box.set_margin_end(24)
    bottom_box.set_halign(Gtk.Align.END)

    cancel_btn = Gtk.Button(label=_("Cancel"))
    cancel_btn.connect("clicked", lambda _b: dialog.close())
    bottom_box.append(cancel_btn)

    import_btn = Gtk.Button(label=_("Import"))
    import_btn.add_css_class("destructive-action")
    set_label(import_btn, _("Import selected settings"))
    bottom_box.append(import_btn)

    toolbar_view.add_bottom_bar(bottom_box)

    def _on_import_clicked(_btn: Gtk.Button) -> None:
        selected_ids = {app_id for chk, app_id, _ in check_rows if chk.get_active()}
        if not selected_ids:
            return
        dialog.close()
        _confirm_import(parent, archive_path, selected_ids)

    import_btn.connect("clicked", _on_import_clicked)

    dialog.set_child(toolbar_view)
    dialog.present(parent)


def _confirm_import(
    parent: Adw.ApplicationWindow,
    archive_path: str,
    selected_ids: set[str],
) -> None:
    """Confirm before overwriting settings."""
    alert = Adw.AlertDialog()
    alert.set_heading(_("Import settings?"))
    alert.set_body(
        _("Existing settings for %d selected applications will be overwritten.\n\n"
          "This action cannot be undone.")
        % len(selected_ids)
    )
    alert.set_close_response("cancel")
    alert.add_response("cancel", _("Cancel"))
    alert.add_response("import", _("Import"))
    alert.set_response_appearance("import", Adw.ResponseAppearance.DESTRUCTIVE)

    def _on_response(_alert: Adw.AlertDialog, response: str) -> None:
        if response == "import":
            _execute_import(parent, archive_path, selected_ids)

    alert.connect("response", _on_response)
    alert.present(parent)


def _execute_import(
    parent: Adw.ApplicationWindow,
    archive_path: str,
    selected_ids: set[str],
) -> None:
    """Run the import in a background thread with a spinner."""
    spinner_dialog = Adw.Dialog()
    spinner_dialog.set_title(_("Importing…"))
    spinner_dialog.set_content_width(420)
    spinner_dialog.set_content_height(220)

    spinner_box = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL, spacing=16
    )
    spinner_box.set_valign(Gtk.Align.CENTER)
    spinner_box.set_halign(Gtk.Align.CENTER)

    spinner = Adw.Spinner()
    spinner.set_size_request(48, 48)
    spinner_box.append(spinner)

    spinner_label = Gtk.Label(
        label=_("Importing settings from backup…")
    )
    spinner_label.add_css_class("title-4")
    spinner_box.append(spinner_label)

    toolbar = Adw.ToolbarView()
    toolbar.add_top_bar(Adw.HeaderBar())
    toolbar.set_content(spinner_box)
    spinner_dialog.set_child(toolbar)
    spinner_dialog.present(parent)

    def _worker() -> None:
        result = import_backup(archive_path, selected_ids)
        GLib.idle_add(_on_import_done, result, spinner_dialog, parent)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()


def _on_import_done(
    result: RestoreFromBackupResult,
    spinner_dialog: Adw.Dialog,
    parent: Adw.ApplicationWindow,
) -> bool:
    spinner_dialog.close()

    result_dialog = Adw.Dialog()
    result_dialog.set_content_width(540)
    result_dialog.set_content_height(400)

    toolbar = Adw.ToolbarView()
    toolbar.add_top_bar(Adw.HeaderBar())

    if result.success:
        status = Adw.StatusPage()
        status.set_icon_name("emblem-ok-symbolic")
        status.set_title(_("Settings imported!"))

        desc_parts = [_("%d applications restored.") % len(result.restored_apps)]
        if result.restored_apps:
            desc_parts.append("\n" + ", ".join(result.restored_apps))
        if result.skipped_apps:
            desc_parts.append(
                "\n\n" + _("Skipped: %s") % ", ".join(result.skipped_apps)
            )
        status.set_description("\n".join(desc_parts))

        ok_btn = Gtk.Button(label=_("OK"))
        ok_btn.set_halign(Gtk.Align.CENTER)
        ok_btn.add_css_class("pill")
        ok_btn.add_css_class("suggested-action")
        ok_btn.connect("clicked", lambda _b: result_dialog.close())
        status.set_child(ok_btn)
    else:
        status = Adw.StatusPage()
        status.set_icon_name("dialog-error-symbolic")
        status.set_title(_("Import error"))
        status.set_description(
            _("An error occurred while importing settings:\n%s") % result.message
        )
        ok_btn = Gtk.Button(label=_("Close"))
        ok_btn.set_halign(Gtk.Align.CENTER)
        ok_btn.add_css_class("pill")
        ok_btn.connect("clicked", lambda _b: result_dialog.close())
        status.set_child(ok_btn)

    toolbar.set_content(status)
    result_dialog.set_child(toolbar)
    result_dialog.present(parent)

    return GLib.SOURCE_REMOVE


def _show_import_error(parent: Adw.ApplicationWindow, message: str) -> None:
    """Show a simple error dialog for invalid backup files."""
    alert = Adw.AlertDialog()
    alert.set_heading(_("Invalid backup"))
    alert.set_body(message)
    alert.add_response("ok", _("OK"))
    alert.set_close_response("ok")
    alert.present(parent)

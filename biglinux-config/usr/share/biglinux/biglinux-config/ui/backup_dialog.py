"""Backup/restore dialog — export and import dotfiles as .tar.gz."""

from __future__ import annotations

import os
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

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

    # App selection group — starts with loading indicator
    apps_group = Adw.PreferencesGroup()
    apps_group.set_title(_("Applications"))
    set_label(apps_group, _("Select applications to export"))

    # Select/deselect all checkbox in the group header (hidden during scan)
    select_all_check = Gtk.CheckButton()
    select_all_check.set_active(True)
    select_all_check.set_valign(Gtk.Align.CENTER)
    select_all_check.set_margin_end(12)
    select_all_check.set_visible(False)
    set_label(select_all_check, _("Select or deselect all"))
    apps_group.set_header_suffix(select_all_check)

    # Loading indicator
    loading_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    loading_box.set_margin_top(24)
    loading_box.set_margin_bottom(24)
    loading_box.set_halign(Gtk.Align.CENTER)

    loading_label = Gtk.Label(label=_("Scanning applications…"))
    loading_label.add_css_class("dim-label")
    loading_box.append(loading_label)

    progress_bar = Gtk.ProgressBar()
    progress_bar.set_size_request(300, -1)
    loading_box.append(progress_bar)

    apps_group.add(loading_box)

    content_box.append(apps_group)

    scroll.set_child(content_box)
    toolbar_view.set_content(scroll)

    # Bottom bar with export button (disabled during scan)
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
    export_btn.set_sensitive(False)
    set_label(export_btn, _("Choose destination and export"))
    bottom_box.append(export_btn)

    toolbar_view.add_bottom_bar(bottom_box)

    dialog.set_child(toolbar_view)
    dialog.present(parent)

    # Scan apps in background thread
    check_rows: list[tuple[Adw.ActionRow, Gtk.CheckButton, AppEntry]] = []
    total = len(apps)

    def _scan_worker() -> None:
        available: list[tuple[AppEntry, int]] = []
        for i, app in enumerate(apps):
            if has_config(app):
                size = get_config_size(app)
                available.append((app, size))
            fraction = (i + 1) / total
            GLib.idle_add(_update_progress, app.name, fraction)
        available.sort(key=lambda t: t[0].name.lower())
        GLib.idle_add(_populate_rows, available)

    def _update_progress(name: str, fraction: float) -> bool:
        loading_label.set_label(_("Scanning: %s") % name)
        progress_bar.set_fraction(fraction)
        return False

    def _populate_rows(available: list[tuple[AppEntry, int]]) -> bool:
        apps_group.remove(loading_box)
        apps_group.set_title(_("Applications (%d available)") % len(available))

        for app_entry, size in available:
            row = Adw.ActionRow()
            row.set_title(app_entry.name)

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

        select_all_check.set_visible(True)
        export_btn.set_sensitive(True)
        return False

    # Toggle all checkboxes when the header checkbox changes
    _toggling = [False]  # guard against recursive toggling

    def _on_select_all_toggled(_chk: Gtk.CheckButton) -> None:
        if _toggling[0]:
            return
        active = select_all_check.get_active()
        _toggling[0] = True
        for _, chk, _ in check_rows:
            chk.set_active(active)
        _toggling[0] = False

    select_all_check.connect("toggled", _on_select_all_toggled)

    def _on_export_clicked(_btn: Gtk.Button) -> None:
        selected = [entry for _, chk, entry in check_rows if chk.get_active()]
        if not selected:
            return
        full_dir = full_dir_row.get_active()
        _pick_save_location(parent, dialog, selected, full_dir)

    export_btn.connect("clicked", _on_export_clicked)

    threading.Thread(target=_scan_worker, daemon=True).start()


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
    """Run the export in a background thread with a progress dialog."""
    cancel_event = threading.Event()

    progress_dialog = Adw.Dialog()
    progress_dialog.set_title(_("Exporting…"))
    progress_dialog.set_content_width(420)
    progress_dialog.set_content_height(260)

    def _on_dialog_closed(_dialog: Adw.Dialog) -> None:
        cancel_event.set()

    progress_dialog.connect("closed", _on_dialog_closed)

    progress_box = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL, spacing=16
    )
    progress_box.set_valign(Gtk.Align.CENTER)
    progress_box.set_halign(Gtk.Align.CENTER)
    progress_box.set_margin_start(24)
    progress_box.set_margin_end(24)

    spinner = Adw.Spinner()
    spinner.set_size_request(48, 48)
    progress_box.append(spinner)

    title_label = Gtk.Label(
        label=_("Exporting settings for %d applications…") % len(entries)
    )
    title_label.add_css_class("title-4")
    progress_box.append(title_label)

    progress_bar = Gtk.ProgressBar()
    progress_bar.set_show_text(True)
    progress_box.append(progress_bar)

    app_label = Gtk.Label(label="")
    app_label.add_css_class("dim-label")
    app_label.set_ellipsize(3)  # Pango.EllipsizeMode.END
    progress_box.append(app_label)

    toolbar = Adw.ToolbarView()
    toolbar.add_top_bar(Adw.HeaderBar())
    toolbar.set_content(progress_box)
    progress_dialog.set_child(toolbar)
    progress_dialog.present(parent)

    def _update_progress(current: int, total: int, app_name: str) -> None:
        if cancel_event.is_set():
            return
        def _do_update() -> bool:
            fraction = (current + 1) / total if total > 0 else 0
            progress_bar.set_fraction(fraction)
            progress_bar.set_text(f"{current + 1}/{total}")
            app_label.set_label(app_name)
            return False
        GLib.idle_add(_do_update)

    def _worker() -> None:
        result = export_backup(
            entries, archive_path, full_directory,
            progress_callback=_update_progress,
            cancel_event=cancel_event,
        )
        if not cancel_event.is_set():
            GLib.idle_add(_on_export_done, result, progress_dialog, parent)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()


def _on_export_done(
    result: BackupResult,
    progress_dialog: Adw.Dialog,
    parent: Adw.ApplicationWindow,
) -> bool:
    progress_dialog.close()

    if result.success:
        dialog = Adw.Dialog()
        dialog.set_content_width(400)
        dialog.set_content_height(-1)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(24)
        box.set_margin_end(24)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)

        # App icon with green check badge (upper-right)
        overlay = Gtk.Overlay()
        app_icon = Gtk.Image.new_from_icon_name("restore-settings")
        app_icon.set_pixel_size(48)
        overlay.set_child(app_icon)

        badge = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
        badge.set_pixel_size(16)
        badge.add_css_class("success")
        badge.set_halign(Gtk.Align.END)
        badge.set_valign(Gtk.Align.START)
        overlay.add_overlay(badge)

        overlay.set_halign(Gtk.Align.CENTER)
        box.append(overlay)

        heading = Gtk.Label(label=_("Backup created!"))
        heading.add_css_class("title-3")
        heading.set_halign(Gtk.Align.CENTER)
        box.append(heading)

        desc = Gtk.Label(
            label=_("%d applications exported (%s)")
            % (result.app_count, format_size(result.total_size))
        )
        desc.add_css_class("dim-label")
        desc.set_wrap(True)
        desc.set_halign(Gtk.Align.CENTER)
        desc.set_justify(Gtk.Justification.CENTER)
        box.append(desc)

        # "Saved to:" row with path and open-in-file-manager button
        saved_label = Gtk.Label(label=_("Saved to:"))
        saved_label.add_css_class("dim-label")
        saved_label.set_halign(Gtk.Align.CENTER)
        saved_label.set_margin_top(4)
        box.append(saved_label)

        path_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        path_row.set_halign(Gtk.Align.CENTER)

        path_label = Gtk.Label(label=result.archive_path)
        path_label.add_css_class("dim-label")
        path_label.set_wrap(True)
        path_label.set_ellipsize(3)  # Pango.EllipsizeMode.END
        path_label.set_max_width_chars(35)
        path_row.append(path_label)

        open_btn = Gtk.Button()
        open_btn.set_icon_name("folder-open-symbolic")
        open_btn.set_tooltip_text(_("Open in file manager"))
        open_btn.add_css_class("flat")
        open_btn.add_css_class("circular")

        def _open_folder(_btn: Gtk.Button, path: str = result.archive_path) -> None:
            folder = os.path.dirname(path)
            Gio.AppInfo.launch_default_for_uri(
                Gio.File.new_for_path(folder).get_uri(), None
            )

        open_btn.connect("clicked", _open_folder)
        path_row.append(open_btn)
        box.append(path_row)

        ok_btn = Gtk.Button(label=_("OK"))
        ok_btn.set_halign(Gtk.Align.CENTER)
        ok_btn.add_css_class("pill")
        ok_btn.add_css_class("suggested-action")
        ok_btn.set_margin_top(8)
        ok_btn.connect("clicked", lambda _b: dialog.close())
        box.append(ok_btn)

        dialog.set_child(box)
        dialog.present(parent)
    elif result.message == "cancelled":
        pass  # User cancelled — do nothing
    else:
        error_dialog = Adw.AlertDialog.new(
            _("Export error"),
            _("An error occurred while creating the backup:\n%s") % result.message,
        )
        error_dialog.add_response("close", _("Close"))
        error_dialog.present(parent)

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
    """Open dialog immediately with loading, read manifest in background."""
    dialog = Adw.Dialog()
    dialog.set_title(_("Import Settings"))
    dialog.set_content_width(560)
    dialog.set_content_height(550)

    toolbar_view = Adw.ToolbarView()
    header = Adw.HeaderBar()
    toolbar_view.add_top_bar(header)

    # Initial loading state
    loading_box = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL, spacing=16
    )
    loading_box.set_valign(Gtk.Align.CENTER)
    loading_box.set_halign(Gtk.Align.CENTER)

    spinner = Adw.Spinner()
    spinner.set_size_request(48, 48)
    loading_box.append(spinner)

    loading_label = Gtk.Label(label=_("Reading backup…"))
    loading_label.add_css_class("title-4")
    loading_box.append(loading_label)

    progress_bar = Gtk.ProgressBar()
    progress_bar.set_margin_start(48)
    progress_bar.set_margin_end(48)
    progress_bar.pulse()
    loading_box.append(progress_bar)

    toolbar_view.set_content(loading_box)
    dialog.set_child(toolbar_view)
    dialog.present(parent)

    # Pulse animation
    pulse_active = [True]

    def _pulse() -> bool:
        if pulse_active[0]:
            progress_bar.pulse()
            return True
        return False

    GLib.timeout_add(100, _pulse)

    def _read_worker() -> None:
        manifest = read_backup_manifest(archive_path)
        GLib.idle_add(
            _on_manifest_ready, manifest, dialog, toolbar_view,
            header, parent, archive_path, pulse_active,
        )

    threading.Thread(target=_read_worker, daemon=True).start()


def _on_manifest_ready(
    manifest: dict | None,
    dialog: Adw.Dialog,
    toolbar_view: Adw.ToolbarView,
    header: Adw.HeaderBar,
    parent: Adw.ApplicationWindow,
    archive_path: str,
    pulse_active: list[bool],
) -> bool:
    """Populate the import dialog after manifest is read."""
    pulse_active[0] = False

    if manifest is None:
        dialog.close()
        _show_import_error(parent, _("This file is not a valid BigLinux backup archive."))
        return False

    apps_in_backup = manifest.get("apps", [])
    if not apps_in_backup:
        dialog.close()
        _show_import_error(parent, _("The backup archive contains no application settings."))
        return False

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

    # Backup info with icon
    info_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
    info_box.set_margin_bottom(4)

    info_icon = Gtk.Image.new_from_icon_name("restore-settings")
    info_icon.set_pixel_size(48)
    info_icon.set_valign(Gtk.Align.CENTER)
    info_box.append(info_icon)

    ts = manifest.get("timestamp", "?")
    hostname = manifest.get("hostname", "?")
    full_dir = manifest.get("full_directory", False)

    info_details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

    info_date = Gtk.Label(label=ts)
    info_date.add_css_class("title-4")
    info_date.set_xalign(0)
    info_details.append(info_date)

    info_host = Gtk.Label(label=_("Host: %s") % hostname)
    info_host.add_css_class("dim-label")
    info_host.set_xalign(0)
    info_details.append(info_host)

    info_full = Gtk.Label(
        label=_("Full directories: %s") % (_("Yes") if full_dir else _("No"))
    )
    info_full.add_css_class("dim-label")
    info_full.set_xalign(0)
    info_details.append(info_full)

    info_box.append(info_details)
    content_box.append(info_box)

    # Warning banner with exclamation icon
    warning_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    warning_box.add_css_class("card")
    warning_box.set_margin_top(4)
    warning_box.set_margin_bottom(4)

    _ensure_import_css()

    warning_box.add_css_class("import-warning-card")

    warn_icon = Gtk.Image.new_from_icon_name("dialog-warning-symbolic")
    warn_icon.set_pixel_size(24)
    warn_icon.add_css_class("warning")
    warn_icon.set_margin_start(12)
    warn_icon.set_margin_top(10)
    warn_icon.set_margin_bottom(10)
    warning_box.append(warn_icon)

    warn_label = Gtk.Label(
        label=_("Importing will overwrite existing settings for selected applications.")
    )
    warn_label.set_wrap(True)
    warn_label.set_xalign(0)
    warn_label.set_margin_top(10)
    warn_label.set_margin_bottom(10)
    warn_label.set_margin_end(12)
    warning_box.append(warn_label)

    content_box.append(warning_box)

    # App selection group with single checkbox header
    apps_group = Adw.PreferencesGroup()
    apps_group.set_title(_("Applications in backup (%d)") % len(apps_in_backup))

    select_all_check = Gtk.CheckButton()
    select_all_check.set_active(True)
    select_all_check.set_margin_end(12)
    select_all_check.set_tooltip_text(_("Select/deselect all"))
    apps_group.set_header_suffix(select_all_check)

    check_rows: list[tuple[Gtk.CheckButton, str, str]] = []

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

    updating_select_all = [False]

    def _on_row_check_toggled(_chk: Gtk.CheckButton) -> None:
        if updating_select_all[0]:
            return
        all_active = all(c.get_active() for c, _aid, _nm in check_rows)
        any_active = any(c.get_active() for c, _aid, _nm in check_rows)
        updating_select_all[0] = True
        if all_active:
            select_all_check.set_active(True)
            select_all_check.set_inconsistent(False)
        elif any_active:
            select_all_check.set_inconsistent(True)
        else:
            select_all_check.set_active(False)
            select_all_check.set_inconsistent(False)
        updating_select_all[0] = False

    for chk, _aid, _nm in check_rows:
        chk.connect("toggled", _on_row_check_toggled)

    def _on_select_all_toggled(_chk: Gtk.CheckButton) -> None:
        if updating_select_all[0]:
            return
        updating_select_all[0] = True
        active = select_all_check.get_active()
        select_all_check.set_inconsistent(False)
        for chk, _aid, _nm in check_rows:
            chk.set_active(active)
        updating_select_all[0] = False

    select_all_check.connect("toggled", _on_select_all_toggled)

    content_box.append(apps_group)

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

    return False


_import_css_loaded = False


def _ensure_import_css() -> None:
    global _import_css_loaded
    if _import_css_loaded:
        return
    _import_css_loaded = True
    css = b"""
    .import-warning-card {
        background-color: alpha(@warning_color, 0.12);
        border: 1px solid alpha(@warning_color, 0.3);
    }
    """
    provider = Gtk.CssProvider()
    provider.load_from_data(css)
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(),
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )


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
    """Run the import in a background thread with a progress dialog."""
    cancel_event = threading.Event()

    progress_dialog = Adw.Dialog()
    progress_dialog.set_title(_("Importing…"))
    progress_dialog.set_content_width(420)
    progress_dialog.set_content_height(260)

    def _on_dialog_closed(_dialog: Adw.Dialog) -> None:
        cancel_event.set()

    progress_dialog.connect("closed", _on_dialog_closed)

    progress_box = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL, spacing=16
    )
    progress_box.set_valign(Gtk.Align.CENTER)
    progress_box.set_halign(Gtk.Align.CENTER)
    progress_box.set_margin_start(24)
    progress_box.set_margin_end(24)

    spinner = Adw.Spinner()
    spinner.set_size_request(48, 48)
    progress_box.append(spinner)

    title_label = Gtk.Label(
        label=_("Importing settings from backup…")
    )
    title_label.add_css_class("title-4")
    progress_box.append(title_label)

    progress_bar = Gtk.ProgressBar()
    progress_bar.set_show_text(True)
    progress_bar.set_text("0%")
    progress_bar.pulse()
    progress_box.append(progress_bar)

    app_label = Gtk.Label(label=_("Preparing…"))
    app_label.add_css_class("dim-label")
    app_label.set_ellipsize(3)  # Pango.EllipsizeMode.END
    progress_box.append(app_label)

    toolbar = Adw.ToolbarView()
    toolbar.add_top_bar(Adw.HeaderBar())
    toolbar.set_content(progress_box)
    progress_dialog.set_child(toolbar)
    progress_dialog.present(parent)

    # Pulse bar while preparing
    pulse_active = [True]

    def _pulse() -> bool:
        if pulse_active[0]:
            progress_bar.pulse()
            return True
        return False

    GLib.timeout_add(100, _pulse)

    def _update_progress(current: int, total: int, app_name: str) -> None:
        if cancel_event.is_set():
            return
        def _do_update() -> bool:
            pulse_active[0] = False
            fraction = min(current / total, 1.0) if total > 0 else 0
            progress_bar.set_fraction(fraction)
            pct = int(fraction * 100)
            progress_bar.set_text(f"{pct}%")
            if app_name:
                app_label.set_label(app_name)
            return False
        GLib.idle_add(_do_update)

    def _worker() -> None:
        result = import_backup(
            archive_path, selected_ids,
            progress_callback=_update_progress,
            cancel_event=cancel_event,
        )
        if not cancel_event.is_set():
            GLib.idle_add(_on_import_done, result, progress_dialog, parent)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()


def _on_import_done(
    result: RestoreFromBackupResult,
    progress_dialog: Adw.Dialog,
    parent: Adw.ApplicationWindow,
) -> bool:
    progress_dialog.close()

    if result.success:
        dialog = Adw.Dialog()
        dialog.set_content_width(400)
        dialog.set_content_height(-1)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(24)
        box.set_margin_end(24)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)

        # App icon with green check badge (upper-right)
        overlay = Gtk.Overlay()
        app_icon = Gtk.Image.new_from_icon_name("restore-settings")
        app_icon.set_pixel_size(48)
        overlay.set_child(app_icon)

        badge = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
        badge.set_pixel_size(16)
        badge.add_css_class("success")
        badge.set_halign(Gtk.Align.END)
        badge.set_valign(Gtk.Align.START)
        overlay.add_overlay(badge)

        overlay.set_halign(Gtk.Align.CENTER)
        box.append(overlay)

        heading = Gtk.Label(label=_("Settings imported!"))
        heading.add_css_class("title-3")
        heading.set_halign(Gtk.Align.CENTER)
        box.append(heading)

        desc_parts = [_("%d applications restored.") % len(result.restored_apps)]
        if result.restored_apps:
            desc_parts.append("\n" + ", ".join(result.restored_apps))
        if result.skipped_apps:
            desc_parts.append(
                "\n\n" + _("Skipped: %s") % ", ".join(result.skipped_apps)
            )

        desc = Gtk.Label(label="\n".join(desc_parts))
        desc.add_css_class("dim-label")
        desc.set_wrap(True)
        desc.set_halign(Gtk.Align.CENTER)
        desc.set_justify(Gtk.Justification.CENTER)
        box.append(desc)

        ok_btn = Gtk.Button(label=_("OK"))
        ok_btn.set_halign(Gtk.Align.CENTER)
        ok_btn.add_css_class("pill")
        ok_btn.add_css_class("suggested-action")
        ok_btn.set_margin_top(8)
        ok_btn.connect("clicked", lambda _b: dialog.close())
        box.append(ok_btn)

        dialog.set_child(box)
        dialog.present(parent)
    elif result.message == "cancelled":
        pass  # User cancelled — do nothing
    else:
        error_dialog = Adw.AlertDialog.new(
            _("Import error"),
            _("An error occurred while importing settings:\n%s") % result.message,
        )
        error_dialog.add_response("close", _("Close"))
        error_dialog.present(parent)

    return GLib.SOURCE_REMOVE


def _show_import_error(parent: Adw.ApplicationWindow, message: str) -> None:
    """Show a simple error dialog for invalid backup files."""
    alert = Adw.AlertDialog()
    alert.set_heading(_("Invalid backup"))
    alert.set_body(message)
    alert.add_response("ok", _("OK"))
    alert.set_close_response("ok")
    alert.present(parent)

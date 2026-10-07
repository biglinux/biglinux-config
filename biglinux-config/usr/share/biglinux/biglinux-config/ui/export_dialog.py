"""Export dialog: choose applications and save their settings as a backup."""

from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from i18n import _, ngettext
from ui import app_image, set_label
from ui.jobs import run_job
from ui.operation_dialogs import (
    backup_file_dialog,
    build_progress_dialog,
    chosen_path,
    show_error_dialog,
    show_result_dialog,
)
from data.app_registry import AppEntry, is_sensitive
from backend.backup_manager import (
    BackupResult,
    export_backup,
    get_app_backup_name,
    get_default_backup_name,
)
from backend.app_detector import get_localized_name
from backend.reset_manager import get_config_size, has_config


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
                "Close these applications before exporting. A .tar.gz archive will be created with the dotfiles."),
    )
    desc.set_wrap(True)
    desc.set_xalign(0)
    desc.add_css_class("dim-label")
    content_box.append(desc)

    # Privacy warning banner (revealed when a sensitive app is selected).
    privacy_banner = Adw.Banner()
    privacy_banner.set_title(
        _("This backup may contain private data (passwords, cookies, sessions). "
          "Keep it in a safe place."))
    privacy_banner.set_revealed(False)
    content_box.append(privacy_banner)

    # Full directory checkbox
    full_dir_row = Adw.SwitchRow()
    full_dir_row.set_title(_("Include cache files"))
    full_dir_row.set_subtitle(
        _("Also back up cache directories. Makes the archive larger; usually not needed")
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

    scan_cancel = threading.Event()
    dialog.connect("closed", lambda _d: scan_cancel.set())

    # Scan apps in background thread
    check_rows: list[tuple[Adw.ActionRow, Gtk.CheckButton, AppEntry]] = []
    total = len(apps)

    def _scan_worker():
        available: list[tuple[AppEntry, int]] = []
        for i, app in enumerate(apps):
            if scan_cancel.is_set():
                return
            if has_config(app):
                size = get_config_size(app, cancel_event=scan_cancel)
                available.append((app, size))
            fraction = (i + 1) / total
            GLib.idle_add(_update_progress, app.name, fraction)
        available.sort(key=lambda t: get_localized_name(t[0]).lower())
        return available

    def _update_progress(name: str, fraction: float) -> bool:
        if scan_cancel.is_set():
            return False
        loading_label.set_label(_("Scanning: %s") % name)
        progress_bar.set_fraction(fraction)
        return False

    def _populate_rows(available: list[tuple[AppEntry, int]]) -> bool:
        if scan_cancel.is_set():
            return False
        apps_group.remove(loading_box)
        apps_group.set_title(_("Applications (%d available)") % len(available))

        for app_entry, size in available:
            name = get_localized_name(app_entry)
            row = Adw.ActionRow()
            row.set_use_markup(False)
            row.set_title(name)

            paths_str = ", ".join(app_entry.config_paths[:3])
            if len(app_entry.config_paths) > 3:
                paths_str += f" (+{len(app_entry.config_paths) - 3})"
            row.set_subtitle(f"{GLib.format_size(size)} — {paths_str}")

            row.add_prefix(app_image(app_entry.icon, 32))

            if is_sensitive(app_entry):
                warn = Gtk.Image.new_from_icon_name("dialog-warning-symbolic")
                warn.add_css_class("warning")
                warn.set_tooltip_text(_("May contain private data"))
                row.add_suffix(warn)

            check = Gtk.CheckButton()
            check.set_active(True)
            set_label(check, _("Include %s") % name)
            check.connect("toggled", lambda _c: _update_privacy_banner())
            row.add_suffix(check)
            row.set_activatable_widget(check)

            apps_group.add(row)
            check_rows.append((row, check, app_entry))

        select_all_check.set_visible(True)
        export_btn.set_sensitive(bool(check_rows))
        _update_privacy_banner()
        return False

    _toggling = [False]  # guard against recursive toggling

    def _update_privacy_banner() -> None:
        active = [chk.get_active() for _row, chk, _entry in check_rows]
        privacy_banner.set_revealed(any(
            is_sensitive(entry) for _row, chk, entry in check_rows if chk.get_active()))
        export_btn.set_sensitive(any(active))
        if not _toggling[0]:
            _toggling[0] = True
            select_all_check.set_inconsistent(any(active) and not all(active))
            select_all_check.set_active(all(active))
            _toggling[0] = False

    def _on_select_all_toggled(_chk: Gtk.CheckButton) -> None:
        if _toggling[0]:
            return
        active = select_all_check.get_active()
        _toggling[0] = True
        select_all_check.set_inconsistent(False)
        for _row, chk, _entry in check_rows:
            chk.set_active(active)
        _toggling[0] = False
        _update_privacy_banner()

    select_all_check.connect("toggled", _on_select_all_toggled)

    def _on_export_clicked(_btn: Gtk.Button) -> None:
        selected = [entry for _row, chk, entry in check_rows if chk.get_active()]
        if not selected:
            return
        _pick_save_location(parent, _("Save backup as"), get_default_backup_name(),
                            selected, full_dir_row.get_active(), on_chosen=dialog.close)

    export_btn.connect("clicked", _on_export_clicked)

    def scan_failed(error):
        if not scan_cancel.is_set():
            loading_label.set_text(_("Could not scan applications: %s") % error)
    run_job(parent, _scan_worker, lambda available: _populate_rows(available or []),
            cancel_event=scan_cancel, failed=scan_failed)


def _pick_save_location(
    parent: Adw.ApplicationWindow,
    title: str,
    initial_name: str,
    entries: list[AppEntry],
    full_directory: bool,
    on_chosen=None,
) -> None:
    """Ask where to save the archive, then export *entries* there."""
    def on_response(file_dialog, result):
        path = chosen_path(file_dialog.save_finish, result)
        if path:
            if on_chosen:
                on_chosen()
            _execute_export(parent, entries, path, full_directory)

    backup_file_dialog(title, initial_name).save(parent, None, on_response)


def _execute_export(
    parent: Adw.ApplicationWindow,
    entries: list[AppEntry],
    archive_path: str,
    full_directory: bool,
) -> None:
    """Run the export in a background thread with a progress dialog."""
    cancel_event = threading.Event()
    title = ngettext(
        "Exporting settings for %d application…",
        "Exporting settings for %d applications…",
        len(entries),
    ) % len(entries)
    progress_dialog, update = build_progress_dialog(parent, title, cancel_event)

    run_job(parent,
            lambda: export_backup(entries, archive_path, full_directory,
                                  progress_callback=update, cancel_event=cancel_event),
            lambda result: _on_export_done(result, progress_dialog, parent),
            cancel_event=cancel_event,
            failed=lambda error: _on_export_done(BackupResult(False, str(error), archive_path, 0, 0),
                                                  progress_dialog, parent))


def _on_export_done(
    result: BackupResult,
    progress_dialog: Adw.Dialog,
    parent: Adw.ApplicationWindow,
) -> bool:
    progress_dialog.force_close()
    if result.success:
        body = ngettext("%(count)d application exported (%(size)s)",
                        "%(count)d applications exported (%(size)s)",
                        result.app_count) % {"count": result.app_count,
                                             "size": GLib.format_size(result.total_size)}
        if result.message:
            body += "\n\n" + result.message
        show_result_dialog(parent, "restore-settings", _("Backup created!"), body,
                           file_path=result.archive_path)
    elif result.message != "cancelled":
        show_error_dialog(parent, _("Export error"),
                          _("An error occurred while creating the backup:\n%s") % result.message)
    return GLib.SOURCE_REMOVE


def show_single_export(parent: Adw.ApplicationWindow, entry: AppEntry) -> None:
    """Export just one application's configuration to a .tar.gz."""

    def _open_chooser() -> None:
        _pick_save_location(parent, _("Export %s settings") % get_localized_name(entry),
                            get_app_backup_name(entry.app_id), [entry], False)

    if is_sensitive(entry):
        alert = Adw.AlertDialog()
        alert.set_heading(_("This backup may contain private data"))
        alert.set_body(
            _("Settings for %s can include passwords, cookies or session tokens. "
              "Store the backup file in a safe place.") % get_localized_name(entry))
        alert.set_close_response("cancel")
        alert.add_response("cancel", _("Cancel"))
        alert.add_response("continue", _("Continue"))
        alert.set_response_appearance("continue", Adw.ResponseAppearance.SUGGESTED)
        alert.connect(
            "response",
            lambda _a, resp: _open_chooser() if resp == "continue" else None)
        alert.present(parent)
    else:
        _open_chooser()

"""Import dialog: pick a backup, choose its applications and restore them."""

from __future__ import annotations

import threading
from datetime import datetime

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from i18n import _, ngettext
from ui import set_label
from ui.jobs import run_job
from ui.operation_dialogs import (
    backup_file_dialog,
    build_progress_dialog,
    chosen_path,
    show_error_dialog,
    show_result_dialog,
)
from data.app_registry import AppEntry
from backend.backup_manager import (
    RestoreFromBackupResult,
    import_backup,
    read_backup_manifest,
)
from backend.app_detector import get_localized_name


def _choose_backup(parent: Adw.ApplicationWindow, title: str, on_path) -> None:
    def on_response(file_dialog, result):
        path = chosen_path(file_dialog.open_finish, result)
        if path:
            on_path(path)

    backup_file_dialog(title).open(parent, None, on_response)


def show_import_dialog(parent: Adw.ApplicationWindow) -> None:
    """Open a file chooser to select a backup archive, then show import options."""
    _choose_backup(parent, _("Open backup file"),
                   lambda path: _show_import_options(parent, path))


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
    dismissed = [False]
    def dismissed_dialog(_d):
        dismissed[0] = True
        pulse_active[0] = False
    dialog.connect("closed", dismissed_dialog)

    def _pulse() -> bool:
        if pulse_active[0]:
            progress_bar.pulse()
            return True
        return False

    GLib.timeout_add(100, _pulse)

    def _read_worker() -> None:
        manifest = read_backup_manifest(archive_path)
        def deliver():
            if not dismissed[0]:
                return _on_manifest_ready(manifest, dialog, toolbar_view, header,
                                          parent, archive_path, pulse_active)
            return GLib.SOURCE_REMOVE
        GLib.idle_add(deliver)

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

    apps_in_backup = manifest["applications"]
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

    ts = manifest.get("created_at", "?")
    try:  # Locale date instead of the raw ISO 8601 stored in the manifest.
        ts = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S%z").astimezone().strftime("%c")
    except ValueError:
        pass
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
        label=_("Cache files included: %s") % (_("Yes") if full_dir else _("No"))
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
        row.set_use_markup(False)
        row.set_title(app_info["name"])
        paths_str = ", ".join(app_info["roots"][:3])
        if len(app_info["roots"]) > 3:
            paths_str += f" (+{len(app_info['roots']) - 3})"
        row.set_subtitle(paths_str)

        check = Gtk.CheckButton()
        check.set_active(True)
        set_label(check, _("Include %s") % app_info["name"])
        row.add_suffix(check)
        row.set_activatable_widget(check)

        apps_group.add(row)
        check_rows.append((check, app_info["app_id"], app_info["name"]))

    updating_select_all = [False]
    import_button = [None]

    def _on_row_check_toggled(_chk: Gtk.CheckButton) -> None:
        if updating_select_all[0]:
            return
        if import_button[0] is not None:
            import_button[0].set_sensitive(any(c.get_active() for c, _aid, _nm in check_rows))
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
        if import_button[0] is not None:
            import_button[0].set_sensitive(active and bool(check_rows))

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
    import_button[0] = import_btn
    import_btn.add_css_class("destructive-action")
    set_label(import_btn, _("Import selected settings"))
    bottom_box.append(import_btn)

    toolbar_view.add_bottom_bar(bottom_box)

    def _on_import_clicked(_btn: Gtk.Button) -> None:
        selected_ids = {app_id for chk, app_id, _ in check_rows if chk.get_active()}
        if not selected_ids:
            return
        dialog.close()
        _confirm_import(parent, archive_path, selected_ids, legacy=manifest["version"] == 1)

    import_btn.connect("clicked", _on_import_clicked)

    return False


def _confirm_import(
    parent: Adw.ApplicationWindow,
    archive_path: str,
    selected_ids: set[str],
    *, legacy: bool = False,
) -> None:
    """Confirm before overwriting settings."""
    alert = Adw.AlertDialog()
    alert.set_heading(_("Import settings?"))
    body = _("The existing settings for the selected applications (%d) will be overwritten.\n\n"
             "Close those applications first and create a backup of the current settings. "
             "Import only backups you trust: integrity checks do not authenticate the sender.") % len(selected_ids)
    if legacy:
        body += "\n\n" + _("Legacy backup: no checksums are available to verify file contents.")
    alert.set_body(body)
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
    progress_dialog, update = build_progress_dialog(
        parent, _("Importing settings from backup…"), cancel_event)

    run_job(parent,
            lambda: import_backup(archive_path, selected_ids,
                                  progress_callback=update, cancel_event=cancel_event),
            lambda result: _on_import_done(result, progress_dialog, parent),
            cancel_event=cancel_event,
            failed=lambda error: _on_import_done(RestoreFromBackupResult(False, str(error), [], []),
                                                  progress_dialog, parent))


def _on_import_done(
    result: RestoreFromBackupResult,
    progress_dialog: Adw.Dialog,
    parent: Adw.ApplicationWindow,
) -> bool:
    progress_dialog.force_close()
    if result.success:
        count = len(result.restored_apps)
        parts = [ngettext("%d application restored.", "%d applications restored.", count) % count]
        if result.message:
            parts.append(result.message)
        if result.restored_apps:
            parts.append(", ".join(result.restored_apps))
        if result.skipped_apps:
            parts.append(_("Skipped: %s") % ", ".join(result.skipped_apps))
        show_result_dialog(parent, "restore-settings", _("Settings imported!"), "\n\n".join(parts))
    elif result.message != "cancelled":
        show_error_dialog(parent, _("Import error"),
                          _("An error occurred while importing settings:\n%s") % result.message)
    return GLib.SOURCE_REMOVE


def _show_import_error(parent: Adw.ApplicationWindow, message: str) -> None:
    """Explain why a chosen file cannot be imported."""
    show_error_dialog(parent, _("Invalid backup"), message)


def show_single_import(parent: Adw.ApplicationWindow, entry: AppEntry) -> None:
    """Import one application's configuration, validating it matches the app."""
    _choose_backup(parent, _("Import %s settings") % get_localized_name(entry),
                   lambda path: _single_import_check(parent, path, entry))


def _single_import_check(
    parent: Adw.ApplicationWindow, archive_path: str, entry: AppEntry
) -> None:
    """Validate that *archive_path* actually contains *entry* before importing."""

    def _worker() -> None:
        manifest = read_backup_manifest(archive_path)
        GLib.idle_add(_done, manifest)

    def _done(manifest) -> bool:
        if manifest is None:
            _show_import_error(
                parent, _("This file is not a valid BigLinux backup."))
            return GLib.SOURCE_REMOVE
        ids = {a.get("app_id") for a in manifest.get("applications", [])}
        if entry.app_id not in ids:
            names = ", ".join(
                a.get("name", "") for a in manifest.get("applications", [])
            ) or "—"
            _show_import_error(
                parent,
                _("This backup does not contain settings for %s.\n\n"
                  "It contains: %s") % (get_localized_name(entry), names))
            return GLib.SOURCE_REMOVE
        _confirm_import(parent, archive_path, {entry.app_id}, legacy=manifest["version"] == 1)
        return GLib.SOURCE_REMOVE

    threading.Thread(target=_worker, daemon=True).start()

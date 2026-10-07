"""Dialogs shared by the export, import and reset flows."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk, Pango

from i18n import _
from ui import app_image


def backup_file_dialog(title: str, initial_name: str = "") -> Gtk.FileDialog:
    """File chooser for backup archives, starting in the Documents folder."""
    file_dialog = Gtk.FileDialog(title=title)
    if initial_name:
        file_dialog.set_initial_name(initial_name)
    docs_dir = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOCUMENTS)
    if docs_dir:
        file_dialog.set_initial_folder(Gio.File.new_for_path(docs_dir))
    gz_filter = Gtk.FileFilter(name=_("BigLinux backups (*.tar.gz)"))
    gz_filter.add_pattern("*.tar.gz")
    filters = Gio.ListStore.new(Gtk.FileFilter)
    filters.append(gz_filter)
    file_dialog.set_filters(filters)
    file_dialog.set_default_filter(gz_filter)
    return file_dialog


def chosen_path(finish: Callable, result: Gio.AsyncResult) -> str | None:
    """Local path picked in a FileDialog, or None when cancelled."""
    try:
        return finish(result).get_path()
    except GLib.Error:
        return None


def open_in_file_manager(parent: Gtk.Window, path: str) -> None:
    """Show *path* in the file manager: a file is selected in its folder."""
    launcher = Gtk.FileLauncher(file=Gio.File.new_for_path(path))
    directory = os.path.isdir(path)

    def finished(source, result):
        try:
            (source.launch_finish if directory else source.open_containing_folder_finish)(result)
        except GLib.Error as exc:
            if not exc.matches(Gtk.dialog_error_quark(), Gtk.DialogError.DISMISSED):
                show_error_dialog(parent, _("Could not open the file manager"), exc.message)

    if directory:
        launcher.launch(parent, None, finished)
    else:
        launcher.open_containing_folder(parent, None, finished)


def show_error_dialog(parent: Gtk.Widget, heading: str, body: str) -> None:
    alert = Adw.AlertDialog(heading=heading, body=body)
    alert.add_response("close", _("Close"))
    alert.set_close_response("close")
    alert.present(parent)


def show_result_dialog(
    parent: Gtk.Widget,
    icon: str,
    heading: str,
    body: str,
    *,
    file_path: str = "",
    buttons: list[tuple[str, str, Callable | None]] | None = None,
) -> None:
    """Success summary: *icon* with a check badge, text, the saved file with
    an "open folder" button, then *buttons* as (label, css class, callback);
    every button closes the dialog. Defaults to a single OK button."""
    dialog = Adw.Dialog()
    dialog.set_content_width(400)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                  halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
    box.set_margin_top(24)
    box.set_margin_bottom(24)
    box.set_margin_start(24)
    box.set_margin_end(24)

    overlay = Gtk.Overlay(halign=Gtk.Align.CENTER)
    overlay.set_child(app_image(icon, 48))
    badge = Gtk.Image.new_from_icon_name("object-select-symbolic")
    badge.set_pixel_size(16)
    badge.add_css_class("success")
    badge.set_halign(Gtk.Align.END)
    badge.set_valign(Gtk.Align.START)
    overlay.add_overlay(badge)
    box.append(overlay)

    title = Gtk.Label(label=heading, wrap=True, justify=Gtk.Justification.CENTER)
    title.add_css_class("title-3")
    box.append(title)

    text = Gtk.Label(label=body, wrap=True, justify=Gtk.Justification.CENTER)
    text.add_css_class("dim-label")
    box.append(text)

    if file_path:
        saved = Gtk.Label(label=_("Saved to:"), margin_top=4)
        saved.add_css_class("dim-label")
        box.append(saved)
        row = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER)
        name = Gtk.Label(label=os.path.basename(file_path), tooltip_text=file_path,
                         ellipsize=Pango.EllipsizeMode.MIDDLE, max_width_chars=36)
        row.append(name)
        open_btn = Gtk.Button(icon_name="folder-open-symbolic",
                              tooltip_text=_("Open in file manager"))
        open_btn.add_css_class("flat")
        open_btn.add_css_class("circular")
        open_btn.update_property([Gtk.AccessibleProperty.LABEL], [_("Open in file manager")])
        open_btn.connect("clicked", lambda _b: open_in_file_manager(parent.get_root(), file_path))
        row.append(open_btn)
        box.append(row)

    actions = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER, margin_top=8)
    first = None
    for label, css, callback in buttons or [(_("OK"), "suggested-action", None)]:
        button = Gtk.Button(label=label)
        button.add_css_class("pill")
        if css:
            button.add_css_class(css)

        def clicked(_b, callback=callback):
            dialog.close()
            if callback:
                callback()
        button.connect("clicked", clicked)
        actions.append(button)
        first = first or button
    box.append(actions)

    dialog.set_child(box)
    dialog.present(parent)
    # Focus the action, not the first label (a selectable one would show as selected).
    dialog.set_focus(first)


def build_progress_dialog(
    parent: Adw.ApplicationWindow,
    title_text: str,
    cancel_event: threading.Event,
):
    """Create a consistent byte-based progress dialog.

    Returns ``(dialog, update)`` where ``update(done, total, label)`` is safe to
    call from a worker thread (it re-marshals to the main loop).  The dialog has a
    real Cancel button in the header; closing it also cancels.
    """
    dialog = Adw.Dialog()
    dialog.set_content_width(400)
    dialog.set_content_height(-1)
    dialog.set_can_close(False)

    header = Adw.HeaderBar()
    header.set_show_title(False)
    cancel_btn = Gtk.Button(label=_("Cancel"))
    cancel_btn.add_css_class("flat")
    def request_cancel(*_args):
        cancel_event.set()
        cancel_btn.set_sensitive(False)
        cancel_btn.set_label(_("Cancelling…"))
    cancel_btn.connect("clicked", request_cancel)
    dialog.connect("close-attempt", request_cancel)
    header.pack_start(cancel_btn)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    box.set_valign(Gtk.Align.CENTER)
    box.set_margin_top(12)
    box.set_margin_bottom(28)
    box.set_margin_start(24)
    box.set_margin_end(24)

    spinner = Adw.Spinner()
    spinner.set_size_request(40, 40)
    spinner.set_halign(Gtk.Align.CENTER)
    box.append(spinner)

    title_label = Gtk.Label(label=title_text)
    title_label.add_css_class("title-4")
    title_label.set_wrap(True)
    title_label.set_justify(Gtk.Justification.CENTER)
    box.append(title_label)

    progress_bar = Gtk.ProgressBar()
    progress_bar.set_show_text(True)
    progress_bar.set_text("0%")
    progress_bar.pulse()
    box.append(progress_bar)

    sub_label = Gtk.Label(label=_("Preparing…"))
    sub_label.add_css_class("dim-label")
    sub_label.add_css_class("caption")
    sub_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
    box.append(sub_label)

    toolbar = Adw.ToolbarView()
    toolbar.set_top_bar_style(Adw.ToolbarStyle.FLAT)
    toolbar.add_top_bar(header)
    toolbar.set_content(box)
    dialog.set_child(toolbar)
    dialog.present(parent)

    latest = [None]
    lock = threading.Lock()
    closed = [False]

    def tick():
        if closed[0]:
            return GLib.SOURCE_REMOVE
        with lock:
            progress = latest[0]
            latest[0] = None
        if cancel_event.is_set():
            cancel_btn.set_sensitive(False)
            sub_label.set_text(_("Cancelling safely; keeping recovery data…"))
        elif progress is not None:
            done, total, label = progress
            frac = min(max(done / total, 0), 1) if total > 0 else 0
            progress_bar.set_fraction(frac)
            progress_bar.set_text(f"{int(frac * 100)}% · {GLib.format_size(done)} / {GLib.format_size(total)}")
            sub_label.set_text(label or _("Preparing…"))
        elif progress_bar.get_fraction() == 0:
            progress_bar.pulse()
        return GLib.SOURCE_CONTINUE

    timer = GLib.timeout_add(120, tick)

    def finish(_dialog):
        closed[0] = True
        GLib.source_remove(timer)
        with lock:
            latest[0] = None
    dialog.connect("closed", finish)

    def update(done: int, total: int, label: str) -> None:
        # One replaceable sample, not an unbounded GLib idle queue per chunk.
        with lock:
            if not closed[0]:
                latest[0] = (done, total, label)

    return dialog, update

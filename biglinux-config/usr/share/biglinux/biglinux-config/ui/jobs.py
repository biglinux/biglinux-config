"""Worker lifetime tied to the application; all completion runs on the main loop."""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable

logger = logging.getLogger("biglinux-config")


def run_job(parent, work: Callable, done: Callable, *, cancel_event=None, failed=None):
    """Start on the GTK thread. Never daemonize filesystem mutation/rollback.

    Closing the parent requests cancellation, but leaves the app alive until
    delivery. Completion is unconditional, including cancellation and failures.
    """
    from gi.repository import GLib

    application = parent.get_application()
    if application is not None:
        application.hold()
        count = getattr(application, "_pending_jobs", 0)
        application._pending_jobs = count + 1
        quit_action = application.lookup_action("quit")
        if count == 0 and quit_action is not None:
            application._quit_was_enabled = quit_action.get_enabled()
            quit_action.set_enabled(False)

    def request_close(_window):
        if cancel_event is not None:
            cancel_event.set()
        return True  # Do not abandon an operation half-way through rollback.

    close_handler = parent.connect("close-request", request_close)

    def deliver(value, error):
        try:
            if error is None:
                done(value)
            elif failed is not None:
                failed(error)
            else:
                from gi.repository import Adw
                from utils import _
                alert = Adw.AlertDialog.new(_("Operation failed"), str(error))
                alert.add_response("close", _("Close"))
                alert.present(parent)
        finally:
            parent.disconnect(close_handler)
            if application is not None:
                application._pending_jobs -= 1
                action = application.lookup_action("quit")
                if application._pending_jobs == 0 and action is not None:
                    action.set_enabled(getattr(application, "_quit_was_enabled", True))
                application.release()
        return GLib.SOURCE_REMOVE

    def worker():
        value, error = None, None
        try:
            value = work()
        except Exception as exc:
            logger.exception("Worker failed")
            error = exc
        GLib.idle_add(deliver, value, error)

    thread = threading.Thread(target=worker, name="biglinux-config-job", daemon=False)
    try:
        thread.start()
    except Exception as exc:
        deliver(None, exc)
    return thread

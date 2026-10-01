"""Exercise worker lifetime and dispatch with a fake GLib scheduler, not GTK."""
import queue
import sys
import threading
import types

import pytest
from ui.jobs import run_job


class Action:
    enabled = True
    def get_enabled(self): return self.enabled
    def set_enabled(self, value): self.enabled = value


class App:
    def __init__(self): self.count, self.action = 0, Action()
    def hold(self): self.count += 1
    def release(self): self.count -= 1
    def lookup_action(self, name): return self.action


class Window:
    def __init__(self): self.app, self.handlers = App(), {}
    def get_application(self): return self.app
    def connect(self, signal, callback):
        handler = len(self.handlers) + 1
        self.handlers[handler] = callback
        return handler
    def disconnect(self, handler): self.handlers.pop(handler)


@pytest.fixture
def scheduler(monkeypatch):
    pending = queue.Queue()
    repo = types.ModuleType("gi.repository")
    repo.GLib = types.SimpleNamespace(idle_add=lambda cb, *args: pending.put((cb, args)), SOURCE_REMOVE=False)
    monkeypatch.setitem(sys.modules, "gi", types.ModuleType("gi"))
    monkeypatch.setitem(sys.modules, "gi.repository", repo)
    return pending


def deliver(scheduler):
    callback, args = scheduler.get(timeout=2)
    return callback(*args)


def test_completion_runs_on_main_thread_and_balances_hold(scheduler):
    window, received = Window(), []
    main_thread = threading.get_ident()
    def work():
        assert threading.get_ident() != main_thread
        return "done"
    def done(value):
        assert threading.get_ident() == main_thread
        received.append(value)
    thread = run_job(window, work, done)
    thread.join(timeout=2)
    assert not thread.daemon and not thread.is_alive()
    assert window.app.count == 1 and not window.app.action.enabled
    deliver(scheduler)
    assert received == ["done"]
    assert window.app.count == 0 and window.app.action.enabled
    assert not window.handlers


def test_cancel_does_not_suppress_failed_recovery_result(scheduler):
    window, received, event = Window(), [], threading.Event()
    thread = run_job(window, lambda: "recovery_required", received.append, cancel_event=event)
    thread.join(timeout=2)
    assert next(iter(window.handlers.values()))(window) is True
    assert event.is_set()
    deliver(scheduler)
    assert received == ["recovery_required"]


def test_worker_exception_has_error_completion(scheduler):
    window, errors = Window(), []
    def fail(): raise OSError("injected worker failure")
    thread = run_job(window, fail, lambda _: pytest.fail("success callback"), failed=errors.append)
    thread.join(timeout=2)
    deliver(scheduler)
    assert isinstance(errors[0], OSError)
    assert window.app.count == 0 and not window.handlers


def test_completion_exception_still_releases_lifetime(scheduler):
    window = Window()
    def fail(_): raise ValueError("UI callback failed")
    thread = run_job(window, lambda: None, fail)
    thread.join(timeout=2)
    with pytest.raises(ValueError): deliver(scheduler)
    assert window.app.count == 0 and window.app.action.enabled
    assert not window.handlers


def test_two_jobs_keep_quit_disabled_until_both_complete(scheduler):
    window = Window()
    threads = [run_job(window, lambda: None, lambda _: None) for _ in range(2)]
    for thread in threads: thread.join(timeout=2)
    deliver(scheduler)
    assert window.app.count == 1 and not window.app.action.enabled
    deliver(scheduler)
    assert window.app.count == 0 and window.app.action.enabled


def test_thread_start_failure_releases_lifetime(scheduler, monkeypatch):
    window, errors = Window(), []
    def fail(_): raise RuntimeError("no worker thread available")
    monkeypatch.setattr(threading.Thread, "start", fail)
    run_job(window, lambda: None, lambda _: None, failed=errors.append)
    assert isinstance(errors[0], RuntimeError)
    assert window.app.count == 0 and window.app.action.enabled

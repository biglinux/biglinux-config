"""Positive failure-injection tests: originals must survive every failed reset."""
import json
import os
import threading
from dataclasses import replace
from pathlib import Path

import pytest
from backend import dconf_manager as dc, reset_manager as rm
from backend.transactions import operation_lock, OperationBusy
from data.app_registry import APP_REGISTRY, AppEntry, get_reset_paths
from conftest import make_tree


def entry(**kwargs):
    return AppEntry("app", "App", "", "/bin/true", "system", ["~/.config/app"], **kwargs)


def test_missing_skel_must_not_fall_back_to_removal(fake_home):
    make_tree(fake_home / ".config/app", {"value": "USER"})
    result = rm.reset_app(entry(), rm.ResetMode.BIGLINUX_DEFAULT)
    assert result.status is rm.ResetStatus.FAILED
    assert (fake_home / ".config/app/value").read_text() == "USER"


def test_skel_changes_only_paths_with_templates(fake_home, fake_skel, monkeypatch):
    monkeypatch.setattr(rm, "SKEL_ROOT", str(fake_skel))
    make_tree(fake_skel / ".config", {"app": "DEFAULT"})
    make_tree(fake_home / ".config", {"app": "USER", "app-extra": "KEEP"})
    app = replace(entry(skel_paths=[str(fake_skel / ".config/app")]),
                  config_paths=["~/.config/app", "~/.config/app-extra"])
    result = rm.reset_app(app, rm.ResetMode.BIGLINUX_DEFAULT)
    assert result.success, result.message
    assert (fake_home / ".config/app").read_text() == "DEFAULT"
    assert (fake_home / ".config/app-extra").read_text() == "KEEP"


def test_partial_template_copy_never_touches_live(fake_home, fake_skel, monkeypatch):
    monkeypatch.setattr(rm, "SKEL_ROOT", str(fake_skel))
    make_tree(fake_skel / ".config/app", {"file": "DEFAULT"})
    make_tree(fake_home / ".config/app", {"file": "USER"})
    def fail(source, destination, **kwargs):
        Path(destination).mkdir()
        (Path(destination) / "partial").write_text("incomplete")
        raise OSError("copy failed after creating files")
    monkeypatch.setattr(rm.shutil, "copytree", fail)
    result = rm.reset_app(entry(skel_paths=[str(fake_skel / ".config/app")]), rm.ResetMode.BIGLINUX_DEFAULT)
    assert result.status is rm.ResetStatus.FAILED
    assert (fake_home / ".config/app/file").read_text() == "USER"
    assert not list(fake_home.glob(".biglinux-config-reset-*"))


def test_reset_failed_rollback_keeps_originals(fake_home, monkeypatch):
    make_tree(fake_home / ".config", {"app": "ORIGINAL", "second": "SECOND"})
    real_rename = os.rename
    def fail(source, destination):
        if source == str(fake_home / ".config/second") or "/originals/" in str(source):
            raise OSError("injected rename failure")
        return real_rename(source, destination)
    monkeypatch.setattr(os, "rename", fail)
    app = replace(entry(), config_paths=["~/.config/app", "~/.config/second"])
    result = rm.reset_app(app, rm.ResetMode.PROGRAM_DEFAULT)
    assert result.status is rm.ResetStatus.RECOVERY_REQUIRED
    recovery = Path(result.recovery_path)
    assert (recovery / "originals/.config/app").read_text() == "ORIGINAL"
    assert json.loads((recovery / "recovery.json").read_text())["files"]
    assert recovery.stat().st_mode & 0o777 == 0o700


def test_reset_unlinks_leaf_symlink_not_target(fake_home):
    make_tree(fake_home / ".config/other", {"value": "KEEP"})
    (fake_home / ".config/app").symlink_to("other")
    result = rm.reset_app(entry(), rm.ResetMode.PROGRAM_DEFAULT)
    assert result.success
    assert not (fake_home / ".config/app").is_symlink()
    assert (fake_home / ".config/other/value").read_text() == "KEEP"


def test_dconf_snapshot_failure_precedes_filesystem_changes(fake_home, monkeypatch):
    make_tree(fake_home / ".config/app", {"value": "KEEP"})
    def fail(_):
        raise dc.DconfError("D-Bus unavailable")
    monkeypatch.setattr(dc, "dump_strict", fail)
    result = rm.reset_app(entry(dconf_paths=["/org/example/"]), rm.ResetMode.PROGRAM_DEFAULT)
    assert result.status is rm.ResetStatus.FAILED
    assert (fake_home / ".config/app/value").read_text() == "KEEP"


def test_dconf_failure_rolls_back_files_and_clears_new_keys(fake_home, monkeypatch):
    make_tree(fake_home / ".config/app", {"value": "KEEP"})
    calls = []
    monkeypatch.setattr(dc, "dump_strict", lambda _: "[/]\nold='value'\n")
    def reset(ns):
        calls.append(("reset", ns))
        return len(calls) > 1  # first attempted reset fails; rollback succeeds
    monkeypatch.setattr(dc, "reset", reset)
    monkeypatch.setattr(dc, "load", lambda ns, text: calls.append(("load", ns)) or True)
    result = rm.reset_app(entry(dconf_paths=["/org/example/"]), rm.ResetMode.PROGRAM_DEFAULT)
    assert result.status is rm.ResetStatus.ROLLED_BACK
    assert [kind for kind, ns in calls] == ["reset", "reset", "load"]
    assert (fake_home / ".config/app/value").read_text() == "KEEP"


def test_unexpected_dconf_rollback_exception_preserves_recovery(fake_home, monkeypatch):
    make_tree(fake_home / ".config/app", {"value": "KEEP"})
    monkeypatch.setattr(dc, "dump_strict", lambda _: "[/]\nold='value'\n")
    def fail(_):
        raise RuntimeError("unexpected command error")
    monkeypatch.setattr(dc, "reset", fail)
    result = rm.reset_app(entry(dconf_paths=["/org/example/"]), rm.ResetMode.PROGRAM_DEFAULT)
    assert result.status is rm.ResetStatus.RECOVERY_REQUIRED
    assert Path(result.recovery_path, "recovery.json").exists()
    assert (fake_home / ".config/app/value").read_text() == "KEEP"


def test_cancel_precedes_safety_backup(fake_home, monkeypatch):
    event = threading.Event(); event.set()
    monkeypatch.setattr(rm, "_safety_backup", lambda *a: pytest.fail("backup must not start"))
    result = rm.reset_app(entry(), rm.ResetMode.PROGRAM_DEFAULT, backup_first=True, cancel_event=event)
    assert result.status is rm.ResetStatus.CANCELLED
    assert not list(fake_home.glob(".biglinux-config-reset-*"))


def test_overlapping_globs_removed_once(fake_home):
    make_tree(fake_home / ".config/app", {"first": "1", "second": "2"})
    app = replace(entry(), config_paths=["~/.config/app/*", "~/.config/app", "~/.config/app/first"])
    result = rm.reset_app(app, rm.ResetMode.PROGRAM_DEFAULT)
    assert result.success, result.message
    assert len(result.removed_paths) == 1


def test_concurrent_operation_rejected_and_nested_operation_allowed(fake_home):
    errors = []
    def worker():
        try:
            with operation_lock():
                errors.append("unexpected entry")
        except OperationBusy:
            errors.append("busy")
    with operation_lock():
        with operation_lock():
            thread = threading.Thread(target=worker)
            thread.start(); thread.join(timeout=2)
            assert not thread.is_alive()
    assert errors == ["busy"]
    with operation_lock():
        pass  # released even after a refused operation


def test_desktop_session_never_automatically_terminated(monkeypatch):
    monkeypatch.setattr(os, "pidfd_open", lambda *a: pytest.fail("no signals to desktop"))
    assert not rm.kill_app(entry(is_de=True))


@pytest.mark.parametrize("app_id", ["gnome-boxes", "steam", "bottles"])
def test_data_heavy_registry_roots_are_not_reset_wholesale(app_id):
    app = next(app for app in APP_REGISTRY if app.app_id == app_id)
    assert app.reset_paths is not None
    assert set(app.config_paths) - set(get_reset_paths(app))


def test_no_raw_dconf_database_in_registry_templates():
    assert all(not source.endswith("/.config/dconf") for app in APP_REGISTRY for source in app.skel_paths)


def test_operation_lock_blocks_an_independent_process(fake_home):
    import os
    import subprocess
    import sys
    from conftest import APP_ROOT
    from backend.transactions import operation_lock
    code = """from backend.transactions import operation_lock, OperationBusy
try:
    with operation_lock():
        raise SystemExit(2)
except OperationBusy:
    print('operation busy')
"""
    environment = dict(os.environ, PYTHONPATH=str(APP_ROOT))
    with operation_lock():
        result = subprocess.run([sys.executable, "-c", code], env=environment,
                                capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stderr
    assert "operation busy" in result.stdout

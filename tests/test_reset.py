"""Behavioural tests for the rewritten reset engine."""

from __future__ import annotations

import os
import subprocess
import time

import backend.reset_manager as rm
from backend.reset_manager import ResetMode, ResetStatus
from data.app_registry import AppEntry
from conftest import make_tree


def _entry(app_id="app", config=("~/.config/app",), skel=()):
    return AppEntry(
        app_id=app_id,
        name=app_id.title(),
        icon="",
        binary="/bin/true",
        category="system",
        config_paths=list(config),
        skel_paths=list(skel),
    )


# --------------------------------------------------------------------------- #
# Program default
# --------------------------------------------------------------------------- #
def test_program_default_removes_config(fake_home):
    make_tree(fake_home / ".config" / "app", {"a": "1", "b": "2"})
    res = rm.reset_app(_entry(), ResetMode.PROGRAM_DEFAULT)
    assert res.status is ResetStatus.SUCCESS
    assert not (fake_home / ".config" / "app").exists()


def test_program_default_missing_config_is_success(fake_home):
    res = rm.reset_app(_entry(), ResetMode.PROGRAM_DEFAULT)
    assert res.status is ResetStatus.SUCCESS
    assert res.removed_paths == []


# --------------------------------------------------------------------------- #
# BigLinux default (skel)
# --------------------------------------------------------------------------- #
def test_biglinux_default_restores_skel(fake_home, fake_skel, monkeypatch):
    monkeypatch.setattr(rm, "SKEL_ROOT", str(fake_skel))
    make_tree(fake_skel / ".config", {"apprc": "SKEL"})
    make_tree(fake_home / ".config", {"apprc": "USER"})
    entry = _entry(
        config=["~/.config/apprc"], skel=[str(fake_skel / ".config" / "apprc")]
    )
    res = rm.reset_app(entry, ResetMode.BIGLINUX_DEFAULT)
    assert res.status is ResetStatus.SUCCESS
    assert (fake_home / ".config" / "apprc").read_text() == "SKEL"


def test_biglinux_default_refuses_structural_skel(fake_home, fake_skel, monkeypatch):
    """A skel that maps to ~/.config must never wipe the whole directory."""
    monkeypatch.setattr(rm, "SKEL_ROOT", str(fake_skel))
    make_tree(fake_skel / ".config", {"apprc": "SKEL"})
    make_tree(fake_home / ".config" / "firefox", {"prefs.js": "keepme"})
    entry = _entry(
        config=["~/.config/apprc"], skel=[str(fake_skel / ".config")]
    )  # structural dest ~/.config
    rm.reset_app(entry, ResetMode.BIGLINUX_DEFAULT)
    # Unrelated app config survives.
    assert (fake_home / ".config" / "firefox" / "prefs.js").read_text() == "keepme"


def test_has_skel_false_for_structural(fake_home, fake_skel, monkeypatch):
    monkeypatch.setattr(rm, "SKEL_ROOT", str(fake_skel))
    make_tree(fake_skel / ".config", {"x": "y"})
    entry = _entry(skel=[str(fake_skel / ".config")])
    assert rm.has_skel(entry) is False


def test_has_skel_true_for_specific(fake_home, fake_skel, monkeypatch):
    monkeypatch.setattr(rm, "SKEL_ROOT", str(fake_skel))
    make_tree(fake_skel / ".config", {"apprc": "y"})
    entry = _entry(skel=[str(fake_skel / ".config" / "apprc")])
    assert rm.has_skel(entry) is True


def test_skel_outside_root_ignored(fake_home, fake_skel, tmp_path, monkeypatch):
    monkeypatch.setattr(rm, "SKEL_ROOT", str(fake_skel))
    outside = tmp_path / "outside" / "evil"
    make_tree(outside.parent, {"evil": "x"})
    entry = _entry(skel=[str(outside)])
    assert rm.has_skel(entry) is False


# --------------------------------------------------------------------------- #
# Rollback
# --------------------------------------------------------------------------- #
def test_reset_rollback_on_skel_failure(fake_home, fake_skel, monkeypatch):
    monkeypatch.setattr(rm, "SKEL_ROOT", str(fake_skel))
    make_tree(fake_skel / ".config", {"apprc": "SKEL"})
    make_tree(fake_home / ".config", {"apprc": "USER"})
    entry = _entry(
        config=["~/.config/apprc"], skel=[str(fake_skel / ".config" / "apprc")]
    )

    def boom(*a, **k):
        raise OSError("copy failed")

    monkeypatch.setattr(rm.shutil, "copy2", boom)

    res = rm.reset_app(entry, ResetMode.BIGLINUX_DEFAULT)
    assert res.status is ResetStatus.ROLLED_BACK
    # Original user config restored intact.
    assert (fake_home / ".config" / "apprc").read_text() == "USER"
    leftovers = [
        p for p in os.listdir(fake_home) if p.startswith(".biglinux-config-reset")
    ]
    assert leftovers == []


# --------------------------------------------------------------------------- #
# Backup before reset
# --------------------------------------------------------------------------- #
def test_backup_first_creates_backup(fake_home, tmp_path, monkeypatch):
    make_tree(fake_home / ".config" / "app", {"a": "data"})
    monkeypatch.setattr(rm, "PRE_RESET_DIR", str(tmp_path / "prebak"))
    res = rm.reset_app(_entry(), ResetMode.PROGRAM_DEFAULT, backup_first=True)
    assert res.status is ResetStatus.SUCCESS
    assert res.backup_path and os.path.exists(res.backup_path)
    # And it is a valid, importable backup.
    import backend.backup_manager as bm

    assert bm.verify_backup(res.backup_path)[0] is True


# --------------------------------------------------------------------------- #
# Precise process matching (uses our own child process)
# --------------------------------------------------------------------------- #
def test_get_running_pids_and_kill(fake_home):
    sleeper = subprocess.Popen(["sleep", "30"])
    try:
        entry = AppEntry(
            app_id="sleep",
            name="Sleep",
            icon="",
            binary="/usr/bin/sleep",
            category="system",
            config_paths=[],
            process_name="sleep",
        )
        time.sleep(0.2)
        pids = rm.get_running_pids(entry)
        assert sleeper.pid in pids
        assert rm.kill_app(entry) is True
        time.sleep(0.2)
        assert sleeper.poll() is not None
    finally:
        if sleeper.poll() is None:
            sleeper.kill()


def test_get_running_pids_no_false_positive(fake_home):
    # A binary that is not running must yield no pids.
    entry = AppEntry(
        app_id="nope",
        name="Nope",
        icon="",
        binary="/usr/bin/this-binary-does-not-exist-xyz",
        category="system",
        config_paths=[],
        process_name="this-binary-xyz-nope",
    )
    assert rm.get_running_pids(entry) == []

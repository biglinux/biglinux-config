"""Regressions found with real profiles: links, runtime files, sockets, a
symlinked HOME path and archives the importer would reject."""

from __future__ import annotations

import os
import socket
import tarfile

import pytest

import backend.backup_manager as bm
import backend.reset_manager as rm
from backend import paths
from backend.archive_policy import ArchiveLimits, BackupError
from backend.backup_manager import ImportStatus
from conftest import make_tree, register
from data.app_registry import AppEntry


def _entry(app_id="app", config=("~/.config/app",)):
    return register(AppEntry(app_id=app_id, name=app_id.title(), icon="", binary="/bin/true",
                             category="system", config_paths=list(config)))


def _members(archive):
    with tarfile.open(archive, "r:gz") as tar:
        return {m.name: m for m in tar.getmembers()}


def test_absolute_link_inside_home_becomes_portable(fake_home, tmp_path):
    # Discord (Flatpak) and Steam store absolute links to their own files.
    app = fake_home / ".config/app"
    make_tree(app, {"app-1.0": {"Discord": "binary"}})
    (app / "Discord").symlink_to(app / "app-1.0/Discord")
    archive = tmp_path / "b.tar.gz"
    result = bm.export_backup([_entry()], str(archive))
    assert result.success, result.message
    assert result.message == ""
    assert _members(archive)[".config/app/Discord"].linkname == "app-1.0/Discord"

    (app / "Discord").unlink()
    assert bm.import_backup(str(archive)).status is ImportStatus.SUCCESS
    assert os.readlink(app / "Discord") == "app-1.0/Discord"
    assert (app / "Discord").read_text() == "binary"


def test_link_outside_home_is_left_out_and_reported(fake_home, tmp_path):
    app = fake_home / ".config/app"
    make_tree(app, {"settings": "keep"})
    (app / "theme").symlink_to("/usr/share/themes")
    archive = tmp_path / "b.tar.gz"
    result = bm.export_backup([_entry()], str(archive))
    assert result.success, result.message
    assert "~/.config/app/theme" in result.message
    names = _members(archive)
    assert ".config/app/settings" in names and ".config/app/theme" not in names


def test_chromium_runtime_markers_are_not_saved(fake_home, tmp_path):
    profile = fake_home / ".config/app"
    make_tree(profile, {"Preferences": "{}"})
    (profile / "SingletonLock").symlink_to("otherhost-1234")
    (profile / "SingletonSocket").symlink_to("/tmp/.org.chromium.Chromium.x/SingletonSocket")
    (profile / "SingletonCookie").symlink_to("1234567890")
    archive = tmp_path / "b.tar.gz"
    result = bm.export_backup([_entry()], str(archive))
    assert result.success, result.message
    assert result.message == ""
    assert not {n for n in _members(archive) if "Singleton" in n}


def test_sockets_and_pipes_are_skipped(fake_home, tmp_path):
    app = fake_home / ".config/app"
    make_tree(app, {"settings": "keep"})
    os.mkfifo(app / "steam.pipe")
    server = socket.socket(socket.AF_UNIX)
    try:
        server.bind(str(app / "ipc.sock"))
        archive = tmp_path / "b.tar.gz"
        result = bm.export_backup([_entry()], str(archive))
    finally:
        server.close()
    assert result.success, result.message
    assert set(_members(archive)) >= {".config/app/settings"}
    assert not {".config/app/steam.pipe", ".config/app/ipc.sock"} & set(_members(archive))


def test_home_reached_through_a_symlink_still_works(tmp_path, monkeypatch):
    real = tmp_path / "disk" / "user"
    make_tree(real / ".config/app", {"a": "data"})
    (tmp_path / "home").symlink_to(tmp_path / "disk")
    monkeypatch.setenv("HOME", str(tmp_path / "home" / "user"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "home" / "user" / ".local/state"))
    entry = _entry()
    [target] = paths.expand_targets(entry.config_paths)
    assert paths.safe_removable(target) == target == str(real / ".config/app")

    archive = tmp_path / "b.tar.gz"
    assert bm.export_backup([entry], str(archive)).success
    result = rm.reset_app(entry, rm.ResetMode.PROGRAM_DEFAULT)
    assert result.status is rm.ResetStatus.SUCCESS, result.message
    assert not (real / ".config/app").exists()
    assert bm.import_backup(str(archive)).status is ImportStatus.SUCCESS
    assert (real / ".config/app/a").read_text() == "data"


def test_oversized_export_fails_before_writing(fake_home, tmp_path):
    make_tree(fake_home / ".config/app", {"big": "x" * 64})
    records, _roots, total, _skipped = bm._build_inventory([_entry()], include_cache=False)
    with pytest.raises(BackupError, match="cannot be backed up"):
        bm._check_export_limits(records, total, ArchiveLimits(max_file_size=10))
    with pytest.raises(BackupError, match="too large"):
        bm._check_export_limits(records, total, ArchiveLimits(max_total_size=10))
    bm._check_export_limits(records, total)  # default limits accept it


def test_has_skel_matches_the_reset_plan(fake_home, fake_skel, monkeypatch):
    monkeypatch.setattr(rm, "SKEL_ROOT", str(fake_skel))
    make_tree(fake_skel / ".config", {})
    # A dangling template link: offering it would make the reset fail.
    (fake_skel / ".config/apprc").symlink_to("/nonexistent/apprc")
    entry = AppEntry(app_id="app", name="App", icon="", binary="/bin/true", category="system",
                     config_paths=["~/.config/apprc"], skel_paths=[str(fake_skel / ".config/apprc")])
    assert rm.has_skel(entry) == bool(rm._skel_plan(entry)) is False

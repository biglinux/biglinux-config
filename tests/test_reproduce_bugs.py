"""Regression sentinels for the historical safety fixes.

Each test encodes the *original defective* behaviour.  After the fixes landed
they no longer reproduce, so they are marked ``xfail(strict=True)``: the suite
stays green and any regression that reintroduces a bug would flip an xfail into
an unexpected pass and fail CI.
"""

from __future__ import annotations

import os
import tarfile

import pytest

import backend.backup_manager as bm
import backend.reset_manager as rm
from data.app_registry import AppEntry
from conftest import make_tree

_FIXED = pytest.mark.xfail(strict=True, reason="fixed regression sentinel")


# P1 (full_directory was a no-op) is now covered positively by
# tests/test_backup.py::test_cache_excluded_by_default — the flag has a real
# effect, so a dedicated reproduction is no longer meaningful.


# --------------------------------------------------------------------------- #
# P2 — manifest is written at the END of the archive (forces a full scan)
# --------------------------------------------------------------------------- #
@_FIXED
def test_p2_manifest_is_last_member(fake_home, tmp_path):
    make_tree(fake_home / ".config" / "app", {"a.txt": "a"})
    entry = AppEntry(
        app_id="app",
        name="App",
        icon="",
        binary="/bin/true",
        category="system",
        config_paths=["~/.config/app"],
    )
    arc = tmp_path / "b.tar.gz"
    bm.export_backup([entry], str(arc))
    with tarfile.open(arc, "r:gz") as t:
        names = [m.name for m in t.getmembers()]
    assert names[-1] == bm.MANIFEST_NAME, "manifest at end forces double read on import"


# --------------------------------------------------------------------------- #
# C4 — export writes directly to the final path (not atomic .part + rename)
# --------------------------------------------------------------------------- #
@_FIXED
def test_c4_export_not_atomic(fake_home, tmp_path, monkeypatch):
    make_tree(fake_home / ".config" / "app", {"a.txt": "a"})
    entry = AppEntry(
        app_id="app",
        name="App",
        icon="",
        binary="/bin/true",
        category="system",
        config_paths=["~/.config/app"],
    )
    arc = tmp_path / "out.tar.gz"
    opened = {}
    real_open = tarfile.open

    def spy(name=None, *a, **k):
        opened["path"] = name
        return real_open(name, *a, **k)

    monkeypatch.setattr(bm.tarfile, "open", spy)
    bm.export_backup([entry], str(arc))
    assert opened["path"] == str(arc), (
        "export opened the final path directly; a crash mid-write would corrupt "
        "an existing backup (no .part + atomic rename)"
    )


# --------------------------------------------------------------------------- #
# C3 — import is not transactional: a mid-extraction failure leaves HOME in a
#      mixed old/new state with no rollback
# --------------------------------------------------------------------------- #
@_FIXED
def test_c3_import_no_rollback(fake_home, tmp_path, monkeypatch):
    # Build an archive holding two files for one app.
    make_tree(fake_home / ".config" / "app", {"a.txt": "NEW-A", "b.txt": "NEW-B"})
    entry = AppEntry(
        app_id="app",
        name="App",
        icon="",
        binary="/bin/true",
        category="system",
        config_paths=["~/.config/app"],
    )
    arc = tmp_path / "bak.tar.gz"
    bm.export_backup([entry], str(arc))

    # Replace HOME content with the "current" config we must NOT lose on failure.
    make_tree(fake_home / ".config" / "app", {"a.txt": "OLD-A", "b.txt": "OLD-B"})

    # Make the second file copy blow up mid-import.
    calls = {"n": 0}
    real_copy = bm.shutil.copyfileobj

    def flaky(src, dst, *a, **k):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("simulated write failure")
        return real_copy(src, dst, *a, **k)

    monkeypatch.setattr(bm.shutil, "copyfileobj", flaky)
    result = bm.import_backup(str(arc))
    assert result.success is False

    # Current behaviour is WORSE than half-overwrite: the directory member is
    # rmtree'd up-front, so both previous files are destroyed. b.txt is left as a
    # truncated (empty) file from the crashed copy. No rollback whatsoever.
    a = (fake_home / ".config" / "app" / "a.txt").read_text()
    b = (fake_home / ".config" / "app" / "b.txt").read_text()
    assert a != "OLD-A" and b != "OLD-B", (
        "import destroyed the previous config with no rollback on failure"
    )
    assert b != "NEW-B", "b.txt was left truncated by the crashed copy"


# --------------------------------------------------------------------------- #
# C5 — symlinks are lost on round-trip (silently skipped on extract)
# --------------------------------------------------------------------------- #
@_FIXED
def test_c5_symlink_roundtrip_lost(fake_home, tmp_path):
    appdir = fake_home / ".config" / "app"
    make_tree(appdir, {"real.txt": "data"})
    (appdir / "link.txt").symlink_to("real.txt")
    entry = AppEntry(
        app_id="app",
        name="App",
        icon="",
        binary="/bin/true",
        category="system",
        config_paths=["~/.config/app"],
    )
    arc = tmp_path / "s.tar.gz"
    bm.export_backup([entry], str(arc), full_directory=True)

    # Wipe and re-import into a clean home.
    import shutil as _sh

    _sh.rmtree(appdir)
    bm.import_backup(str(arc))

    assert (appdir / "real.txt").exists()
    # Current behaviour: the symlink member is silently skipped on extract.
    assert not (appdir / "link.txt").exists(), (
        "symlink was silently dropped on import -> round-trip loses symlinks"
    )


# --------------------------------------------------------------------------- #
# C1 — de-kde style BigLinux-default reset WIPES the whole ~/.config
#      (reads the real /etc/skel/.config read-only; writes only inside fake HOME)
# --------------------------------------------------------------------------- #
@_FIXED
@pytest.mark.skipif(
    not os.path.isdir("/etc/skel/.config"),
    reason="requires /etc/skel/.config to reproduce the broad-rmtree path",
)
def test_c1_biglinux_default_wipes_whole_config(fake_home, monkeypatch):
    # Sentinel config for an unrelated app that must survive.
    make_tree(fake_home / ".config" / "firefox-sentinel", {"prefs.js": "keepme"})
    make_tree(fake_home / ".config", {"plasmarc": "x"})

    entry = AppEntry(
        app_id="de-kde",
        name="KDE",
        icon="",
        binary="/bin/true",
        category="desktop_env",
        config_paths=["~/.config/plasmarc"],
        skel_paths=["/etc/skel/.config"],
        is_de=True,
    )
    rm.reset_app(entry, rm.ResetMode.BIGLINUX_DEFAULT)

    sentinel = fake_home / ".config" / "firefox-sentinel" / "prefs.js"
    # Proves the catastrophe: unrelated app config is destroyed.
    assert not sentinel.exists(), (
        "expected the current code to wipe the whole ~/.config (catastrophic bug)"
    )

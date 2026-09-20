"""Behavioural tests for the rewritten backup engine (correct behaviour)."""

from __future__ import annotations

import io
import json
import os
import tarfile
import threading

import backend.backup_manager as bm
from backend.backup_manager import ImportStatus
from data.app_registry import AppEntry
from conftest import make_tree


def _entry(app_id="app", paths=("~/.config/app",)):
    return AppEntry(
        app_id=app_id,
        name=app_id.title(),
        icon="",
        binary="/bin/true",
        category="system",
        config_paths=list(paths),
    )


def _export(entries, arc, **kw):
    r = bm.export_backup(entries, str(arc), **kw)
    assert r.success, r.message
    return r


# --------------------------------------------------------------------------- #
# Round-trip fidelity
# --------------------------------------------------------------------------- #
def test_roundtrip_files_dirs_unicode_spaces_perms(fake_home, tmp_path):
    appdir = fake_home / ".config" / "app"
    make_tree(
        appdir,
        {
            "plain.txt": "hello",
            "sub dir": {"a b.txt": "spaces", "ção.txt": "unicode"},
            "empty": {},
        },
    )
    (appdir / "script.sh").write_text("#!/bin/sh\n")
    os.chmod(appdir / "script.sh", 0o755)

    arc = tmp_path / "b.tar.gz"
    _export([_entry()], arc)

    # capture then wipe
    import shutil

    shutil.rmtree(appdir)
    res = bm.import_backup(str(arc))
    assert res.status is ImportStatus.SUCCESS

    assert (appdir / "plain.txt").read_text() == "hello"
    assert (appdir / "sub dir" / "a b.txt").read_text() == "spaces"
    assert (appdir / "sub dir" / "ção.txt").read_text() == "unicode"
    assert (appdir / "empty").is_dir()
    assert oct(os.stat(appdir / "script.sh").st_mode & 0o777) == oct(0o755)


def test_roundtrip_preserves_symlinks(fake_home, tmp_path):
    appdir = fake_home / ".config" / "app"
    make_tree(appdir, {"real.txt": "data"})
    (appdir / "rel.link").symlink_to("real.txt")
    arc = tmp_path / "s.tar.gz"
    _export([_entry()], arc, full_directory=True)
    import shutil

    shutil.rmtree(appdir)
    assert bm.import_backup(str(arc)).status is ImportStatus.SUCCESS
    assert (appdir / "rel.link").is_symlink()
    assert os.readlink(appdir / "rel.link") == "real.txt"


# --------------------------------------------------------------------------- #
# full_directory now has a real effect (cache exclusion)
# --------------------------------------------------------------------------- #
def test_cache_excluded_by_default(fake_home, tmp_path):
    appdir = fake_home / ".config" / "app"
    make_tree(appdir, {"real.conf": "keep", "Cache": {"junk.bin": "x"}})
    arc = tmp_path / "n.tar.gz"
    _export([_entry()], arc, full_directory=False)
    with tarfile.open(arc, "r:gz") as t:
        names = {m.name for m in t.getmembers()}
    assert ".config/app/real.conf" in names
    assert ".config/app/Cache/junk.bin" not in names

    arc2 = tmp_path / "f.tar.gz"
    _export([_entry()], arc2, full_directory=True)
    with tarfile.open(arc2, "r:gz") as t:
        names2 = {m.name for m in t.getmembers()}
    assert ".config/app/Cache/junk.bin" in names2


# --------------------------------------------------------------------------- #
# Manifest first + metadata
# --------------------------------------------------------------------------- #
def test_manifest_is_first_member(fake_home, tmp_path):
    make_tree(fake_home / ".config" / "app", {"a": "a"})
    arc = tmp_path / "m.tar.gz"
    _export([_entry()], arc)
    with tarfile.open(arc, "r:gz") as t:
        first = t.next()
    assert first.name == bm.MANIFEST_NAME
    man = bm.read_backup_manifest(str(arc))
    assert man["version"] == bm.BACKUP_VERSION
    assert man["applications"][0]["app_id"] == "app"
    assert man["file_count"] >= 1


# --------------------------------------------------------------------------- #
# Atomic export
# --------------------------------------------------------------------------- #
def test_export_cancel_preserves_existing_backup(fake_home, tmp_path):
    make_tree(fake_home / ".config" / "app", {f"f{i}": "x" * 100 for i in range(50)})
    arc = tmp_path / "keep.tar.gz"
    _export([_entry()], arc)
    original = arc.read_bytes()

    ev = threading.Event()
    ev.set()  # cancel immediately
    r = bm.export_backup([_entry()], str(arc), cancel_event=ev)
    assert r.success is False and r.message == "cancelled"
    # Existing valid backup untouched, no leftover .part
    assert arc.read_bytes() == original
    assert not (tmp_path / "keep.tar.gz.part").exists()


def test_export_failure_leaves_no_partial(fake_home, tmp_path, monkeypatch):
    make_tree(fake_home / ".config" / "app", {"a": "a"})
    arc = tmp_path / "x.tar.gz"

    def boom(*a, **k):
        raise OSError("disk error")

    monkeypatch.setattr(bm.tarfile, "open", boom)
    r = bm.export_backup([_entry()], str(arc))
    assert r.success is False
    assert not arc.exists()
    assert not (tmp_path / "x.tar.gz.part").exists()


# --------------------------------------------------------------------------- #
# Integrity verification
# --------------------------------------------------------------------------- #
def test_verify_detects_truncation(fake_home, tmp_path):
    make_tree(fake_home / ".config" / "app", {"a": "a" * 5000})
    arc = tmp_path / "v.tar.gz"
    _export([_entry()], arc)
    ok, _ = bm.verify_backup(str(arc))
    assert ok
    data = bytearray(arc.read_bytes())
    arc.write_bytes(data[: len(data) // 2])  # truncate
    ok2, msg = bm.verify_backup(str(arc))
    assert ok2 is False


def test_verify_detects_checksum_tamper(fake_home, tmp_path):
    make_tree(fake_home / ".config" / "app", {"a": "original"})
    arc = tmp_path / "t.tar.gz"
    _export([_entry()], arc)
    # Rebuild archive with a tampered file body but original checksums member.
    members = []
    with tarfile.open(arc, "r:gz") as t:
        for m in t.getmembers():
            f = t.extractfile(m)
            data = f.read() if f else b""
            members.append((m, data))
    out = tmp_path / "t2.tar.gz"
    with tarfile.open(out, "w:gz") as t:
        for m, data in members:
            if m.name == ".config/app/a":
                data = b"TAMPERED"
                m.size = len(data)
            ti = m
            t.addfile(ti, io.BytesIO(data))
    ok, msg = bm.verify_backup(str(out))
    assert ok is False and "hecksum" in msg


# --------------------------------------------------------------------------- #
# Transactional import + rollback
# --------------------------------------------------------------------------- #
def test_import_rollback_on_failure(fake_home, tmp_path, monkeypatch):
    make_tree(fake_home / ".config" / "app", {"a.txt": "NEW-A", "b.txt": "NEW-B"})
    arc = tmp_path / "r.tar.gz"
    _export([_entry()], arc)
    # current config that must survive a failed import
    make_tree(fake_home / ".config" / "app", {"a.txt": "OLD-A", "b.txt": "OLD-B"})

    # Force the final swap to fail.
    real_rename = os.rename
    calls = {"n": 0}

    def flaky_rename(a, b):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("swap failed")
        return real_rename(a, b)

    monkeypatch.setattr(bm.os, "rename", flaky_rename)

    res = bm.import_backup(str(arc))
    assert res.success is False
    assert res.status is ImportStatus.ROLLED_BACK
    # previous config fully intact
    assert (fake_home / ".config" / "app" / "a.txt").read_text() == "OLD-A"
    assert (fake_home / ".config" / "app" / "b.txt").read_text() == "OLD-B"
    # no staging litter
    leftovers = [
        p for p in os.listdir(fake_home) if p.startswith(".biglinux-config-restore")
    ]
    assert leftovers == []


def test_import_cancel_leaves_home_untouched(fake_home, tmp_path):
    make_tree(fake_home / ".config" / "app", {"a.txt": "NEW"})
    arc = tmp_path / "c.tar.gz"
    _export([_entry()], arc)
    make_tree(fake_home / ".config" / "app", {"a.txt": "OLD"})
    ev = threading.Event()
    ev.set()
    res = bm.import_backup(str(arc), cancel_event=ev)
    assert res.status is ImportStatus.CANCELLED
    assert (fake_home / ".config" / "app" / "a.txt").read_text() == "OLD"


def test_partial_selection(fake_home, tmp_path):
    make_tree(fake_home / ".config" / "app1", {"x": "1"})
    make_tree(fake_home / ".config" / "app2", {"y": "2"})
    e1 = _entry("app1", ["~/.config/app1"])
    e2 = _entry("app2", ["~/.config/app2"])
    arc = tmp_path / "multi.tar.gz"
    _export([e1, e2], arc)
    import shutil

    shutil.rmtree(fake_home / ".config" / "app1")
    shutil.rmtree(fake_home / ".config" / "app2")
    res = bm.import_backup(str(arc), selected_app_ids={"app1"})
    assert res.status is ImportStatus.SUCCESS
    assert (fake_home / ".config" / "app1" / "x").exists()
    assert not (fake_home / ".config" / "app2").exists()
    assert "App2" in res.skipped_apps


# --------------------------------------------------------------------------- #
# Security: malicious archives
# --------------------------------------------------------------------------- #
def _make_manifest_archive(arc, members, roots):
    """Build an archive with a valid v2 manifest plus arbitrary members."""
    manifest = {
        "format": bm.BACKUP_FORMAT,
        "version": 2,
        "created_at": "",
        "total_size": 0,
        "file_count": len(members),
        "applications": [{"app_id": "app", "name": "App", "roots": roots}],
    }
    with tarfile.open(arc, "w:gz") as t:
        data = json.dumps(manifest).encode()
        ti = tarfile.TarInfo(bm.MANIFEST_NAME)
        ti.size = len(data)
        t.addfile(ti, io.BytesIO(data))
        for name, body, kind, link in members:
            ti = tarfile.TarInfo(name)
            if kind == "sym":
                ti.type = tarfile.SYMTYPE
                ti.linkname = link
                t.addfile(ti)
            else:
                ti.size = len(body)
                t.addfile(ti, io.BytesIO(body))


def test_reject_path_traversal(fake_home, tmp_path):
    arc = tmp_path / "evil.tar.gz"
    _make_manifest_archive(
        arc,
        [(".config/app/../../../../etc/evil", b"pwned", "file", "")],
        roots=[".config/app"],
    )
    res = bm.import_backup(str(arc))
    assert res.success is False
    assert not os.path.exists("/tmp/etc/evil")


def test_reject_absolute_path(fake_home, tmp_path):
    arc = tmp_path / "abs.tar.gz"
    _make_manifest_archive(arc, [("/etc/evil2", b"x", "file", "")], roots=["/etc"])
    res = bm.import_backup(str(arc))
    assert res.success is False


def test_reject_symlink_escape(fake_home, tmp_path):
    arc = tmp_path / "esc.tar.gz"
    _make_manifest_archive(
        arc,
        [(".config/app/escape", b"", "sym", "/etc/passwd")],
        roots=[".config/app"],
    )
    res = bm.import_backup(str(arc))
    assert res.success is False
    assert not (fake_home / ".config" / "app" / "escape").exists()


# --------------------------------------------------------------------------- #
# Backward compat with v1 archives
# --------------------------------------------------------------------------- #
def test_reads_v1_archive(fake_home, tmp_path):
    # Build a legacy v1 archive: files then manifest LAST with apps/paths.
    make_tree(fake_home / ".config" / "app", {"a.txt": "v1data"})
    arc = tmp_path / "v1.tar.gz"
    with tarfile.open(arc, "w:gz") as t:
        t.add(str(fake_home / ".config" / "app"), arcname=".config/app")
        man = {
            "version": 1,
            "timestamp": "2020",
            "apps": [{"app_id": "app", "name": "App", "paths": [".config/app"]}],
        }
        data = json.dumps(man).encode()
        ti = tarfile.TarInfo(bm.MANIFEST_NAME)
        ti.size = len(data)
        t.addfile(ti, io.BytesIO(data))
    m = bm.read_backup_manifest(str(arc))
    assert m["version"] == 1
    assert m["applications"][0]["roots"] == [".config/app"]

    import shutil

    shutil.rmtree(fake_home / ".config" / "app")
    res = bm.import_backup(str(arc))
    assert res.status is ImportStatus.SUCCESS
    assert (fake_home / ".config" / "app" / "a.txt").read_text() == "v1data"


def test_file_disappearing_mid_export_is_skipped(fake_home, tmp_path):
    appdir = fake_home / ".config" / "app"
    make_tree(appdir, {"a.txt": "a", "b.txt": "b"})
    arc = tmp_path / "vanish.tar.gz"

    def cb(done, total, label):
        # Delete b.txt right after a.txt is processed.
        if label.endswith("a.txt"):
            try:
                (appdir / "b.txt").unlink()
            except OSError:
                pass

    r = bm.export_backup([_entry()], str(arc), progress_callback=cb)
    assert r.success  # whole backup does not fail for one vanished file
    with tarfile.open(arc, "r:gz") as t:
        names = {m.name for m in t.getmembers()}
    assert ".config/app/a.txt" in names
    assert ".config/app/b.txt" not in names


def test_nested_roots_multi_app(fake_home, tmp_path):
    make_tree(fake_home / ".config" / "x" / "sub", {"child": "C"})
    (fake_home / ".config" / "x" / "top").write_text("T")
    parent = _entry("parent", ["~/.config/x"])
    child = _entry("child", ["~/.config/x/sub"])
    arc = tmp_path / "nested.tar.gz"
    _export([parent, child], arc)
    import shutil

    shutil.rmtree(fake_home / ".config" / "x")
    res = bm.import_backup(str(arc))
    assert res.status is ImportStatus.SUCCESS
    assert (fake_home / ".config" / "x" / "top").read_text() == "T"
    assert (fake_home / ".config" / "x" / "sub" / "child").read_text() == "C"


def test_disk_space_guard(fake_home, tmp_path, monkeypatch):
    make_tree(fake_home / ".config" / "app", {"a": "a"})
    arc = tmp_path / "d.tar.gz"
    _export([_entry()], arc)

    real_manifest = bm.read_backup_manifest(str(arc))
    inflated = {**real_manifest, "total_size": 10**12}  # 1 TB
    monkeypatch.setattr(bm, "read_backup_manifest", lambda p: inflated)

    class FakeUsage:
        free = 1  # 1 byte free

    monkeypatch.setattr(bm.shutil, "disk_usage", lambda p: FakeUsage())

    res = bm.import_backup(str(arc))
    assert res.success is False
    assert "space" in res.message.lower()

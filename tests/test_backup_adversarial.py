"""Adversarial archives and injected I/O failures must never report false success."""
import hashlib
import io
import json
import os
import shutil
import tarfile
import threading
from dataclasses import replace

import pytest

from backend import backup_manager as bm
from backend.archive_policy import DEFAULT_LIMITS
from test_backup import _entry, _export
from conftest import make_tree


def archive(path, members, roots=(".config/app",), checksums=True, total_size=0):
    manifest = {"format": bm.BACKUP_FORMAT, "version": 2, "total_size": total_size,
                "applications": [{"app_id": "app", "name": "App", "roots": list(roots)}]}
    with tarfile.open(path, "w:gz") as tar:
        bm._add_bytes(tar, bm.MANIFEST_NAME, json.dumps(manifest).encode())
        digests = {}
        for member, data in members:
            tar.addfile(member, io.BytesIO(data) if member.isreg() else None)
            if member.isreg():
                digests[member.name] = hashlib.blake2b(data, digest_size=32).hexdigest()
        if checksums:
            bm._add_bytes(tar, bm.CHECKSUMS_NAME, json.dumps(digests).encode())


def file(name=".config/app/a", body=b"data"):
    member = tarfile.TarInfo(name)
    member.size = len(body)
    return member, body


def test_predictable_part_symlink_cannot_overwrite_another_file(fake_home, tmp_path):
    make_tree(fake_home / ".config/app", {"a": "settings"})
    target = tmp_path / "private"
    target.write_text("DO NOT TOUCH")
    arc = tmp_path / "backup.tar.gz"
    (tmp_path / "backup.tar.gz.part").symlink_to(target)
    _export([_entry()], arc)
    assert target.read_text() == "DO NOT TOUCH"
    assert (tmp_path / "backup.tar.gz.part").is_symlink()
    assert arc.stat().st_mode & 0o777 == 0o600


def test_hardlinked_sources_roundtrip_without_silent_loss(fake_home, tmp_path):
    app = fake_home / ".config/app"
    make_tree(app, {"one": "content"})
    os.link(app / "one", app / "two")
    arc = tmp_path / "hard.tar.gz"
    _export([_entry()], arc)
    shutil.rmtree(app)
    assert bm.import_backup(str(arc)).success
    assert (app / "one").read_text() == (app / "two").read_text() == "content"


def test_private_directory_permissions_are_preserved(fake_home, tmp_path):
    app = fake_home / ".config/app"
    make_tree(app, {"a": "secret"})
    app.chmod(0o700)
    arc = tmp_path / "private.tar.gz"
    _export([_entry()], arc)
    shutil.rmtree(app)
    assert bm.import_backup(str(arc)).success
    assert app.stat().st_mode & 0o777 == 0o700


def test_missing_checksum_member_is_rejected(fake_home, tmp_path):
    arc = tmp_path / "missing.tar.gz"
    archive(arc, [file()], checksums=False)
    assert not bm.verify_backup(str(arc))[0]
    assert not bm.import_backup(str(arc)).success
    assert not (fake_home / ".config/app").exists()


def test_duplicate_file_is_rejected_even_with_matching_hash(fake_home, tmp_path):
    arc = tmp_path / "duplicate.tar.gz"
    archive(arc, [file(), file()])
    assert not bm.verify_backup(str(arc))[0]
    assert not bm.import_backup(str(arc)).success


@pytest.mark.parametrize("root", [".config", ".local/share", ".var/app"])
def test_structural_root_never_replaces_unrelated_settings(fake_home, tmp_path, root):
    make_tree(fake_home / root, {"sentinel": "keep"})
    arc = tmp_path / "structural.tar.gz"
    archive(arc, [file(root + "/a")], roots=(root,))
    assert not bm.import_backup(str(arc)).success
    assert (fake_home / root / "sentinel").read_text() == "keep"


def test_existing_symlink_parent_does_not_escape_home(fake_home, tmp_path):
    outside = tmp_path / "outside"
    make_tree(outside, {"sentinel": "keep"})
    (fake_home / ".config").symlink_to(outside)
    arc = tmp_path / "escape.tar.gz"
    archive(arc, [file()])
    assert not bm.import_backup(str(arc)).success
    assert not (outside / "app").exists()
    assert (outside / "sentinel").read_text() == "keep"


def test_actual_size_limit_not_trusted_manifest_size(fake_home, tmp_path):
    arc = tmp_path / "large.tar.gz"
    archive(arc, [file(body=b"x" * 2048)], total_size=0)
    limits = replace(DEFAULT_LIMITS, max_file_size=1024)
    assert not bm.import_backup(str(arc), limits=limits).success
    assert not bm.verify_backup(str(arc), limits=limits)[0]


def test_corrupt_gzip_trailer_is_rejected(fake_home, tmp_path):
    arc = tmp_path / "trailer.tar.gz"
    archive(arc, [file()])
    arc.write_bytes(arc.read_bytes()[:-8])
    assert not bm.verify_backup(str(arc))[0]
    assert not bm.import_backup(str(arc)).success


def test_cancel_inside_large_file_preserves_previous_archive(fake_home, tmp_path):
    make_tree(fake_home / ".config/app", {"a": "x" * 2_000_000})
    arc = tmp_path / "cancel.tar.gz"
    arc.write_bytes(b"existing backup")
    event = threading.Event()
    def progress(done, total, label):
        if done:
            event.set()
    result = bm.export_backup([_entry()], str(arc), cancel_event=event, progress_callback=progress)
    assert not result.success
    assert result.message == "cancelled"
    assert arc.read_bytes() == b"existing backup"
    assert not list(tmp_path.glob(".biglinux-backup-*.part"))


def test_failed_rollback_retains_original_files_and_journal(fake_home, tmp_path, monkeypatch):
    make_tree(fake_home / ".config/app", {"a": "NEW"})
    arc = tmp_path / "recover.tar.gz"
    _export([_entry()], arc)
    (fake_home / ".config/app/a").write_text("OLD")
    real_rename = os.rename
    def rename(source, destination):
        # First move of the original works; install AND rollback both fail.
        if "/staging/" in str(source) or "/originals/" in str(source):
            raise OSError("simulated storage failure")
        return real_rename(source, destination)
    monkeypatch.setattr(bm.os, "rename", rename)
    result = bm.import_backup(str(arc))
    assert result.status is bm.ImportStatus.RECOVERY_REQUIRED
    assert result.recovery_path
    from pathlib import Path
    recovery = Path(result.recovery_path)
    assert (recovery / "originals/.config/app/a").read_text() == "OLD"
    assert (recovery / "recovery.json").exists()
    assert recovery.stat().st_mode & 0o777 == 0o700


def test_nested_roots_failure_restores_parent_once(fake_home, tmp_path, monkeypatch):
    make_tree(fake_home / ".config/app", {"top": "NEW", "sub": {"x": "NEW"}})
    arc = tmp_path / "nested.tar.gz"
    _export([_entry(), _entry("child", ["~/.config/app/sub"])], arc)
    (fake_home / ".config/app/top").write_text("OLD")
    monkeypatch.setattr(bm, "_apply_dconf", lambda *a: (_ for _ in ()).throw(OSError("after swap")))
    result = bm.import_backup(str(arc))
    assert result.status is bm.ImportStatus.ROLLED_BACK
    assert (fake_home / ".config/app/top").read_text() == "OLD"


def test_persistent_web_data_is_not_treated_as_cache(fake_home, tmp_path):
    make_tree(fake_home / ".config/app", {"Service Worker": {"data": "keep"}, "blob_storage": {"data": "keep"}})
    arc = tmp_path / "offline.tar.gz"
    _export([_entry()], arc)
    with tarfile.open(arc) as tar:
        assert ".config/app/Service Worker/data" in tar.getnames()
        assert ".config/app/blob_storage/data" in tar.getnames()


def test_oversized_extended_header_read_is_bounded():
    source = bm._BoundedReader(io.BytesIO(), DEFAULT_LIMITS, lambda: None)
    with pytest.raises(bm.BackupError):
        source.read(4 * 1024**3)


def test_archive_inside_selected_folder_is_rejected(fake_home):
    make_tree(fake_home / ".config/app", {"a": "data"})
    arc = fake_home / ".config/app/backup.tar.gz"
    assert not bm.export_backup([_entry()], str(arc)).success
    assert not arc.exists()

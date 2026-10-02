"""Private, fail-closed configuration backups with verified staging and rollback.

Version 2 hashes every regular payload; version 1 remains structurally readable
but has no integrity guarantee. Neither format authenticates its author. Live
applications must be closed: this is not an application/database snapshot API.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import logging
import os
import shutil
import stat
import sys
import tarfile
import tempfile
import time
import zlib
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum

from gi.repository import GLib

from backend import dconf_manager, paths
from backend.archive_policy import (
    BACKUP_FORMAT, CHECKSUMS_NAME, DEFAULT_LIMITS, DCONF_PREFIX, MANIFEST_NAME,
    BackupError, DamagedBackup, MemberPolicy, normalise_manifest, read_json,
    validate_checksums,
)
from backend.transactions import (
    FileTransaction, fsync_directory, operation_lock, recovery_message,
)
from data.app_registry import APP_REGISTRY, AppEntry
from i18n import _

logger = logging.getLogger("biglinux-config")


def _changed(rel):
    return _("%s changed while the backup was being made. Close the application "
             "and try again.") % ("~/" + rel)


def _describe(exc):
    """User-facing text for an import failure."""
    if isinstance(exc, (DamagedBackup, tarfile.TarError, EOFError, gzip.BadGzipFile, zlib.error)):
        return (_("This file is damaged, incomplete or was not created by Restore Settings.")
                + "\n\n" + _("Details: %s") % exc)
    return str(exc)
BACKUP_VERSION = 2
SUPPORTED_VERSIONS = (1, 2)
_HASH_CHUNK = 1024 * 1024
_DCONF_PREFIX = DCONF_PREFIX
CACHE_COMPONENTS = frozenset({
    "Cache", "cache", "Cache_Data", "CachedData", "Code Cache", "GPUCache",
    "ShaderCache", "Crash Reports", "Crashpad", "GrShaderCache", "DawnCache",
    "component_crx_cache",
})
# Service Worker/blob_storage can hold persistent offline data; not caches.
ProgressCallback = Callable[[int, int, str], None]


class _Cancelled(Exception):
    pass


class ImportStatus(Enum):
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ROLLED_BACK = "rolled_back"
    RECOVERY_REQUIRED = "recovery_required"


@dataclass
class BackupResult:
    success: bool
    message: str
    archive_path: str
    app_count: int
    total_size: int
    file_count: int = 0


@dataclass
class RestoreFromBackupResult:
    success: bool
    message: str
    restored_apps: list[str]
    skipped_apps: list[str]
    status: ImportStatus = ImportStatus.FAILED
    recovery_path: str = ""


@dataclass
class _FileRecord:
    fullpath: str
    rel: str
    kind: str
    size: int
    mode: int
    mtime: int
    link_target: str = ""
    app_id: str = ""


def _cancel(event) -> None:
    if event is not None and event.is_set():
        raise _Cancelled()


def _notify(callback, done, total, label):
    """Presentation errors must never corrupt or roll back a committed backup."""
    if callback:
        try:
            callback(done, total, label)
        except Exception:
            logger.exception("Progress callback failed")


def _iter_entry_paths(top: str, include_cache=True, check_cancel=lambda: None):
    """Iterative scandir walk; prune cache subtrees BEFORE listing their files."""
    pending = [top]
    while pending:
        check_cancel()
        path = pending.pop()
        if not include_cache and _is_cache_path(os.path.relpath(path, paths.home())):
            continue
        yield path
        if not os.path.islink(path) and os.path.isdir(path):
            with os.scandir(path) as entries:
                pending.extend(sorted((item.path for item in entries), reverse=True))


def _is_cache_path(rel: str) -> bool:
    return any(component in CACHE_COMPONENTS for component in rel.split("/"))


def _build_inventory(entries, include_cache, check_cancel=lambda: None):
    records, app_roots, seen = [], {}, set()
    total_size = 0
    for entry in entries:
        roots = []
        for target in paths.expand_targets(entry.config_paths):
            check_cancel()
            real = paths.safe_removable(target)
            if real is None:
                raise BackupError(f"Unsafe configuration path: {target}")
            rel_root = os.path.relpath(real, paths.home())
            if not include_cache and _is_cache_path(rel_root):
                continue
            roots.append(rel_root)
            for full in _iter_entry_paths(real, include_cache, check_cancel):
                rel = os.path.relpath(full, paths.home())
                if rel in seen:
                    continue
                info = os.lstat(full)  # no silent omission of vanished/unreadable data
                if stat.S_ISREG(info.st_mode):
                    kind, size, link = "file", info.st_size, ""
                elif stat.S_ISDIR(info.st_mode):
                    kind, size, link = "dir", 0, ""
                elif stat.S_ISLNK(info.st_mode):
                    kind, size, link = "link", 0, os.readlink(full)
                    if not _symlink_is_safe(link, rel):
                        raise BackupError(_("Could not save %s. Close the application and try again.") % rel)
                else:
                    raise BackupError(_("Could not save %s. Close the application and try again.") % rel)
                if paths.archive_name(rel) is None:
                    raise BackupError(_("The file name %r cannot be stored in a backup.") % rel)
                seen.add(rel)
                total_size += size
                records.append(_FileRecord(full, rel, kind, size,
                    stat.S_IMODE(info.st_mode), int(info.st_mtime), link, entry.app_id))
        if roots:
            app_roots[entry.app_id] = roots
    return records, app_roots, total_size


def _collect_dconf(entries, check_cancel=lambda: None):
    members, sections = [], []
    cached = {}
    for entry in entries:
        items = []
        for index, namespace in enumerate(entry.dconf_paths):
            check_cancel()
            if namespace not in cached:
                cached[namespace] = dconf_manager.dump_strict(namespace)
            data = cached[namespace].encode("utf-8")
            if len(data) > DEFAULT_LIMITS.max_dconf_size:
                raise BackupError(f"dconf namespace exceeds the backup limit: {namespace}")
            member = f"{DCONF_PREFIX}/{entry.app_id}/{index}.ini"
            members.append((member, data))  # empty dumps also describe a valid state
            items.append({"path": namespace, "member": member})
        if items:
            sections.append({"app_id": entry.app_id, "name": entry.name, "items": items})
    return members, sections


def _system_metadata():
    distro = ""
    try:
        with open("/etc/os-release", encoding="utf-8") as src:
            for line in src:
                if line.startswith("PRETTY_NAME="):
                    distro = line.split("=", 1)[1].strip().strip('"')
                    break
    except OSError:
        pass
    return {"hostname": os.uname().nodename, "username": os.environ.get("USER", ""),
            "desktop": os.environ.get("XDG_CURRENT_DESKTOP", ""), "distribution": distro}


class _HashingReader:
    def __init__(self, source, hasher, check_cancel, progress):
        self.source, self.hasher = source, hasher
        self.check_cancel, self.progress = check_cancel, progress

    def read(self, size=-1):
        self.check_cancel()
        data = self.source.read(size)
        self.hasher.update(data)
        self.progress(len(data))
        return data


def export_backup(entries: list[AppEntry], archive_path: str, full_directory=False,
                  progress_callback=None, cancel_event=None) -> BackupResult:
    """Fail on any lost input; publish a complete 0600 archive atomically."""
    temporary = None
    archive_path = os.fspath(archive_path)
    try:
        with operation_lock():
            check_cancel = lambda: _cancel(cancel_event)
            check_cancel()
            if len({e.app_id for e in entries}) != len(entries):
                raise BackupError("Duplicate applications in export.")
            records, roots, total = _build_inventory(entries, full_directory, check_cancel)
            dconf_members, dconf_sections = _collect_dconf(entries, check_cancel)
            total += sum(len(data) for _, data in dconf_members)
            dconf_ids = {s["app_id"] for s in dconf_sections}
            manifest = normalise_manifest({
                "format": BACKUP_FORMAT, "version": BACKUP_VERSION,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "full_directory": bool(full_directory), "total_size": total,
                "file_count": len(records) + len(dconf_members), **_system_metadata(),
                "applications": [{"app_id": e.app_id, "name": e.name,
                                  "roots": roots.get(e.app_id, [])}
                                 for e in entries if e.app_id in roots or e.app_id in dconf_ids],
                "dconf": dconf_sections,
            })
            # Publishing inside a selected root creates recursive/self backups.
            for app_roots in roots.values():
                for root in app_roots:
                    if paths.is_within(os.path.join(paths.home(), root), archive_path):
                        raise BackupError(_("Choose a backup destination outside the selected applications' folders."))
            parent = os.path.dirname(os.path.abspath(archive_path))
            os.makedirs(parent, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix=".biglinux-backup-", suffix=".part", dir=parent)
            checksums, done = {}, 0
            policy = MemberPolicy()
            with os.fdopen(fd, "wb") as raw:
                with tarfile.open(fileobj=raw, mode="w:gz", compresslevel=6) as tar:
                    _add_bytes(tar, MANIFEST_NAME, json.dumps(manifest).encode("utf-8"), policy)
                    for rec in records:
                        check_cancel()
                        if paths.safe_removable(rec.fullpath) != rec.fullpath:
                            raise BackupError(_changed(rec.rel))
                        info = tarfile.TarInfo(rec.rel)
                        info.mode, info.mtime = rec.mode & 0o777, rec.mtime
                        if rec.kind == "dir":
                            if not stat.S_ISDIR(os.lstat(rec.fullpath).st_mode):
                                raise BackupError(_changed(rec.rel))
                            info.type = tarfile.DIRTYPE
                            policy.check(info)
                            tar.addfile(info)
                        elif rec.kind == "link":
                            if not os.path.islink(rec.fullpath) or os.readlink(rec.fullpath) != rec.link_target:
                                raise BackupError(_changed(rec.rel))
                            info.type, info.linkname = tarfile.SYMTYPE, rec.link_target
                            policy.check(info)
                            tar.addfile(info)
                        else:
                            # O_NONBLOCK prevents a raced FIFO from hanging open().
                            source_fd = os.open(rec.fullpath, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                            with os.fdopen(source_fd, "rb") as src:
                                before = os.fstat(src.fileno())
                                if not stat.S_ISREG(before.st_mode) or before.st_size != rec.size:
                                    raise BackupError(_changed(rec.rel))
                                info.size = before.st_size
                                info.mode = stat.S_IMODE(before.st_mode) & 0o777
                                policy.check(info)
                                hasher = hashlib.blake2b(digest_size=32)
                                def advance(count):
                                    nonlocal done
                                    done += count
                                    _notify(progress_callback, done, total, rec.rel)
                                tar.addfile(info, _HashingReader(src, hasher, check_cancel, advance))
                                after = os.fstat(src.fileno())
                                if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                                    raise BackupError(_changed(rec.rel))
                                checksums[rec.rel] = hasher.hexdigest()
                        _notify(progress_callback, done, total, rec.rel)
                    for member, data in dconf_members:
                        check_cancel()
                        _add_bytes(tar, member, data, policy)
                        checksums[member] = hashlib.blake2b(data, digest_size=32).hexdigest()
                        done += len(data)
                    payload = json.dumps(checksums).encode("utf-8")
                    if len(payload) > DEFAULT_LIMITS.max_metadata_size:
                        raise BackupError("Checksum manifest exceeds the backup limit.")
                    _add_bytes(tar, CHECKSUMS_NAME, payload, policy)
            # No fsync: the sources stay on disk, so a power cut costs only a rerun.
            check_cancel()
            os.replace(temporary, archive_path)
            temporary = None
            _notify(progress_callback, total, total, "")
            return BackupResult(True, "", archive_path, len(manifest["applications"]), total, len(records) + len(dconf_members))
    except _Cancelled:
        return BackupResult(False, "cancelled", archive_path, 0, 0)
    except Exception as exc:
        logger.exception("Backup failed")
        return BackupResult(False, str(exc), archive_path, 0, 0)
    finally:
        if temporary is not None:
            _quiet_unlink(temporary)


def _add_bytes(tar, name, data, policy=None):
    if name in (MANIFEST_NAME, CHECKSUMS_NAME) and len(data) > DEFAULT_LIMITS.max_metadata_size:
        raise DamagedBackup("Backup metadata exceeds the resource limit.")
    info = tarfile.TarInfo(name)
    info.size, info.mode, info.mtime = len(data), 0o600, int(time.time())
    if policy is not None:
        policy.check(info)
    tar.addfile(info, io.BytesIO(data))


def _quiet_unlink(path):
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


class _BoundedReader:
    """Sequential gzip reader limiting parser allocations and decompressed bytes.

    TarInfo extended headers are read by tarfile BEFORE MemberPolicy sees them.
    Bounding each read prevents a forged PAX/GNU header from allocating gigabytes.
    Forward seeks are implemented in small reads so cancellation and byte limits
    also apply to skipped files in manifest-last archives.
    """
    def __init__(self, source, limits, check_cancel):
        self.source, self.limits, self.check_cancel = source, limits, check_cancel
        self.position = 0
        self.parsing_header = True  # TarFile reads the first member in its constructor.
        self.header_bytes = 0
        self.budget = limits.max_total_size + limits.max_members * 4096

    def read(self, size=-1):
        self.check_cancel()
        if size < 0 or size > self.limits.max_metadata_size + 512:
            raise DamagedBackup("Oversized tar parser read (extended header).")
        if self.position + size > self.budget:
            raise DamagedBackup("Decompressed archive limit exceeded.")
        if self.parsing_header:
            self.header_bytes += size
            if self.header_bytes > self.limits.max_metadata_size + 512:
                raise DamagedBackup("Cumulative tar header budget exceeded.")
        data = self.source.read(size)
        self.position += len(data)
        return data

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        if whence != 0 or offset < self.position:
            raise DamagedBackup("Non-sequential archive access is not supported.")
        parsing = self.parsing_header
        self.parsing_header = False  # Skipped payload uses small buffers, not header allocations.
        try:
            while self.position < offset:
                chunk = self.read(min(_HASH_CHUNK, offset - self.position))
                if not chunk:
                    raise DamagedBackup("Truncated archive.")
        finally:
            self.parsing_header = parsing
        return self.position


@contextmanager
def _reader(source, *, limits=DEFAULT_LIMITS, check_cancel=lambda: None, complete=False):
    """Pinned source, bounded reads; a full scan also checks the gzip trailer."""
    owned = not hasattr(source, "read")
    src = open(source, "rb") if owned else source
    try:
        src.seek(0)
        kwargs = {"stream": True} if sys.version_info >= (3, 13) else {}
        with gzip.GzipFile(fileobj=src, mode="rb") as compressed:
            bounded = _BoundedReader(compressed, limits, check_cancel)
            with tarfile.open(fileobj=bounded, mode="r:", **kwargs) as tar:
                # Application-owned attribute; no private tarfile API is used.
                tar.biglinux_reader = bounded
                yield tar
            bounded.parsing_header = False
            if complete:
                while True:
                    remainder = bounded.read(_HASH_CHUNK)
                    if not remainder:
                        break
                    if remainder.strip(b"\0"):
                        raise DamagedBackup("Unexpected data after the tar end marker.")
    finally:
        if owned:
            src.close()


def _members(tar):
    """Bound a whole chain of PAX/GNU headers, not just each individual read."""
    iterator = iter(tar)
    reader = tar.biglinux_reader
    while True:
        reader.header_bytes = 0
        reader.parsing_header = True
        try:
            member = next(iterator)
        except StopIteration:
            return
        finally:
            reader.parsing_header = False
        yield member


def read_backup_manifest(archive_path, *, limits=DEFAULT_LIMITS, cancel_event=None):
    """Read bounded metadata, including legacy manifest-last archives."""
    try:
        policy = MemberPolicy(limits)
        with _reader(archive_path, limits=limits, check_cancel=lambda: _cancel(cancel_event)) as tar:
            for member in _members(tar):
                _cancel(cancel_event)
                name = policy.check(member)
                if name == MANIFEST_NAME:
                    return normalise_manifest(read_json(tar, member, limits.max_metadata_size))
    except _Cancelled:
        raise
    except (OSError, tarfile.TarError, ValueError, TypeError, EOFError, RecursionError, BackupError) as exc:
        logger.warning("Cannot read backup manifest: %s", exc)
    return None


# Kept for callers/tests using the previous helper name.
_normalise_manifest = normalise_manifest


def _matches_root(name, roots):
    return any(name == root or name.startswith(root + "/") for root in roots)


def _scan_archive(source, manifest, *, staging=None, restore_roots=(), selected_ids=None,
                  progress_callback=None, check_cancel=lambda: None, limits=DEFAULT_LIMITS):
    """One payload pass: validate every member, hash all files, stage only selection."""
    policy = MemberPolicy(limits)
    actual, expected = {}, None
    all_roots = [r for a in manifest["applications"] for r in a["roots"]]
    dconf_names = {i["member"] for s in manifest["dconf"] for i in s["items"]}
    wanted_dconf = {i["member"] for s in manifest["dconf"]
                   if selected_ids is None or s["app_id"] in selected_ids for i in s["items"]}
    texts, directories, seen_manifest, done = {}, [], False, 0
    with _reader(source, limits=limits, check_cancel=check_cancel, complete=True) as tar:
        for member in _members(tar):
            check_cancel()
            name = policy.check(member)
            if name == MANIFEST_NAME:
                current = normalise_manifest(read_json(tar, member, limits.max_metadata_size))
                if current != manifest:
                    raise DamagedBackup("Backup manifest changed during import.")
                seen_manifest = True
                continue
            if name == CHECKSUMS_NAME:
                expected = validate_checksums(read_json(tar, member, limits.max_metadata_size))
                continue
            if not _matches_root(name, all_roots) and name not in dconf_names:
                raise DamagedBackup(f"Unclaimed archive member: {name}")
            if name in dconf_names and (not member.isreg() or member.size > limits.max_dconf_size):
                raise DamagedBackup(f"Invalid/oversized dconf dump: {name}")
            if member.issym() and not _symlink_is_safe(member.linkname, name):
                raise BackupError(f"Unsafe symlink at the live destination: {name}")
            selected = staging is not None and _matches_root(name, restore_roots)
            target = paths.safe_extract_target(name, staging) if selected else None
            filtered = None
            if selected:
                if target is None:
                    raise BackupError(f"Unsafe staged destination: {name}")
                filtered = tarfile.data_filter(member, staging)
                if filtered is None:
                    raise DamagedBackup(f"Rejected archive member: {name}")
            if member.isdir():
                if selected:
                    os.makedirs(target, mode=0o700, exist_ok=True)
                    directories.append((target, member.mode, member.mtime))
                continue
            if member.issym():
                if selected:
                    os.makedirs(os.path.dirname(target), mode=0o700, exist_ok=True)
                    os.symlink(member.linkname, target)
                continue
            digest = hashlib.blake2b(digest_size=32)
            capture = io.BytesIO() if name in wanted_dconf else None
            output = None
            try:
                if selected:
                    os.makedirs(os.path.dirname(target), mode=0o700, exist_ok=True)
                    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
                    output = os.fdopen(fd, "wb")
                with tar.extractfile(member) as src:
                    while True:
                        check_cancel()
                        chunk = src.read(_HASH_CHUNK)
                        if not chunk:
                            break
                        digest.update(chunk)
                        if output:
                            output.write(chunk)
                        if capture is not None:
                            capture.write(chunk)
                        done += len(chunk)
                        _notify(progress_callback, done, max(manifest["total_size"], done), name)
                if output:
                    output.flush()
                    os.fchmod(output.fileno(), filtered.mode if filtered.mode is not None else 0o600)
                    os.fsync(output.fileno())
                actual[name] = digest.hexdigest()
                if capture is not None:
                    texts[name] = capture.getvalue().decode("utf-8")
            finally:
                if output:
                    output.close()
            if selected:
                os.utime(target, (member.mtime, member.mtime), follow_symlinks=False)
    if not seen_manifest:
        raise DamagedBackup("Manifest missing from archive.")
    if manifest["version"] == 2:
        if expected is None or expected.keys() != actual.keys():
            raise DamagedBackup("Missing or incomplete checksum manifest.")
        for name, digest in actual.items():
            if expected[name] != digest:
                raise DamagedBackup(f"Checksum mismatch: {name}")
    if not dconf_names.issubset(actual):
        raise DamagedBackup("A declared dconf dump is missing.")
    for root in all_roots:
        if root not in policy.names and root not in policy.parents:
            raise DamagedBackup(f"Declared application root is missing: {root}")
    # Directory modes are applied last, after writing all children. Never widen
    # a private profile to 0755 or retain setuid/setgid/sticky bits.
    for target, mode, mtime in sorted(directories, key=lambda item: len(item[0]), reverse=True):
        os.chmod(target, (mode & 0o755) | 0o700)
        os.utime(target, (mtime, mtime), follow_symlinks=False)
        fsync_directory(target)
    return texts


def verify_backup(archive_path, *, limits=DEFAULT_LIMITS):
    try:
        with open(archive_path, "rb") as source:
            manifest = read_backup_manifest(source, limits=limits)
            if manifest is None:
                return False, "No valid manifest found."
            texts = _scan_archive(source, manifest, limits=limits)
            _dconf_payloads(manifest, texts, None)
        return True, "" if manifest["version"] == 2 else "Legacy backup: no checksums available."
    except Exception as exc:
        return False, str(exc)


def _rollback_dconf(applied):
    errors = []
    for namespace, previous in reversed(applied):
        # dconf load MERGES; reset is necessary to remove imported-only keys.
        try:
            if not dconf_manager.reset(namespace) or (previous.strip() and not dconf_manager.load(namespace, previous)):
                errors.append(f"Could not restore dconf namespace {namespace}")
        except Exception as exc:
            errors.append(f"Could not restore dconf namespace {namespace}: {exc}")
    return errors


def _check_registered_scope(manifest, selected):
    """Checksums do not authenticate an archive: restore only what this
    installation itself would back up for each application."""
    scopes = {}
    for app in selected:
        app_id = app["app_id"]
        if app_id.startswith("flatpak-"):
            scopes[app_id] = ([f".var/app/{app_id.removeprefix('flatpak-')}"], [])
        else:
            entry = next((e for e in APP_REGISTRY if e.app_id == app_id), None)
            if entry is None:
                raise BackupError(_("This backup contains settings for %s, which this version does not support. Nothing was imported.") % app_id)
            scopes[app_id] = ([p.removeprefix("~/") for p in entry.config_paths],
                              entry.dconf_paths)
        allowed = scopes[app_id][0]
        for root in app["roots"]:
            if not any(root == p or root.startswith(p + "/") for p in allowed):
                raise BackupError(_("This backup tries to write to %(path)s, which is not a settings folder of %(app)s. Nothing was imported.") % {"path": "~/" + root, "app": app["name"]})
    for section in manifest["dconf"]:
        if section["app_id"] not in scopes:
            continue
        allowed = scopes[section["app_id"]][1]
        for item in section["items"]:
            if not any(item["path"].startswith(ns) for ns in allowed):
                raise BackupError(
                    _("This backup tries to change desktop settings (%(path)s) that do not "
                      "belong to %(app)s. Nothing was imported.")
                    % {"path": item["path"], "app": section["app_id"]})


def _dconf_payloads(manifest, texts, selected_ids):
    wanted = {}
    for section in manifest["dconf"]:
        if selected_ids is not None and section["app_id"] not in selected_ids:
            continue
        for item in section["items"]:
            ns, member = item["path"], item["member"]
            text = texts[member]
            if ns in wanted and wanted[ns] != text:
                raise DamagedBackup(f"Conflicting dumps for dconf namespace {ns}")
            wanted[ns] = text
    return wanted


def _apply_dconf(manifest, texts, selected_ids, transaction, check_cancel):
    wanted = _dconf_payloads(manifest, texts, selected_ids)
    for ns, text in wanted.items():
        check_cancel()
        transaction.dconf.append((ns, dconf_manager.dump_strict(ns)))
        transaction.write_journal()
        if not dconf_manager.reset(ns) or (text.strip() and not dconf_manager.load(ns, text)):
            raise BackupError(f"Failed to replace dconf namespace {ns}")


def import_backup(archive_path, selected_app_ids=None, progress_callback=None,
                  cancel_event=None, *, limits=DEFAULT_LIMITS):
    try:
        with operation_lock():
            return _import_backup(archive_path, selected_app_ids, progress_callback,
                                  cancel_event, limits=limits)
    except Exception as exc:
        return RestoreFromBackupResult(False, _describe(exc), [], [], ImportStatus.FAILED)


def _import_backup(archive_path, selected_app_ids=None, progress_callback=None,
                  cancel_event=None, *, limits=DEFAULT_LIMITS):
    """Validate everything before live writes; retain originals if rollback fails."""
    transaction, skipped = None, []
    try:
        with open(archive_path, "rb") as source:
            check_cancel = lambda: _cancel(cancel_event)
            check_cancel()
            manifest = read_backup_manifest(source, limits=limits, cancel_event=cancel_event)
            if manifest is None:
                raise DamagedBackup("no valid manifest found")
            selected = [app for app in manifest["applications"]
                        if selected_app_ids is None or app["app_id"] in selected_app_ids]
            skipped = [a["name"] for a in manifest["applications"] if a not in selected]
            if not selected:
                raise BackupError(_("Select at least one application to restore."))
            _check_registered_scope(manifest, selected)
            roots = sorted({r for app in selected for r in app["roots"]}, key=lambda r: (len(r), r))
            # Commit only disjoint top-level roots. Child apps still appear in results.
            disjoint = []
            for root in roots:
                if not _matches_root(root, disjoint):
                    disjoint.append(root)
            ids = {a["app_id"] for a in selected}
            if any(s["app_id"] in ids for s in manifest["dconf"]) and not dconf_manager.is_available():
                raise BackupError(_("The dconf tool is needed to restore these desktop settings. Install the dconf package."))
            free = shutil.disk_usage(paths.home()).free
            needed = manifest["total_size"] + 16 * 1024**2
            if free < needed:
                raise BackupError(_("Not enough free space: %(need)s needed, %(free)s available.") % {"need": GLib.format_size(needed), "free": GLib.format_size(free)})
            # Enforce observed bytes too; metadata is untrusted and can understate size.
            from dataclasses import replace
            scan_limits = replace(limits, max_total_size=min(limits.max_total_size, max(0, free - 16 * 1024**2)))
            transaction = FileTransaction(".biglinux-config-restore-")
            texts = _scan_archive(source, manifest, staging=transaction.staging,
                restore_roots=disjoint, selected_ids=ids, progress_callback=progress_callback,
                check_cancel=check_cancel, limits=scan_limits)
            _dconf_payloads(manifest, texts, ids)  # Conflicts fail BEFORE the first live rename.
            for root in disjoint:
                check_cancel()
                staged = os.path.join(transaction.staging, root)
                if not os.path.lexists(staged):
                    raise BackupError(f"Selected root was not staged: {root}")
                transaction.replace(os.path.join(paths.home(), root), staged)
            _apply_dconf(manifest, texts, ids, transaction, check_cancel)
            check_cancel()
            # Commit is complete. Cleanup failure cannot trigger rollback after
            # some originals have already been deleted.
            warning = ""
            try:
                transaction.cleanup()
            except OSError as exc:
                warning = f"Settings restored, but temporary files remain at {transaction.directory}: {exc}"
                logger.warning(warning)
            _notify(progress_callback, manifest["total_size"], manifest["total_size"], "")
            return RestoreFromBackupResult(True, warning, [a["name"] for a in selected], skipped, ImportStatus.SUCCESS)
    except Exception as exc:
        cancelled = isinstance(exc, _Cancelled)
        errors = []
        changed = transaction is not None and bool(transaction.records or transaction.dconf)
        if transaction:
            errors.extend(_rollback_dconf(transaction.dconf))
            errors.extend(transaction.rollback_files())
            if not errors:
                try:
                    transaction.cleanup()
                except OSError as cleanup_error:
                    errors.append(str(cleanup_error))
        if errors:
            message = recovery_message(_describe(exc), transaction.directory, errors)
            logger.error(message)
            return RestoreFromBackupResult(False, message, [], skipped,
                ImportStatus.RECOVERY_REQUIRED, transaction.directory)
        status = ImportStatus.CANCELLED if cancelled else (ImportStatus.ROLLED_BACK if changed else ImportStatus.FAILED)
        message = "cancelled" if cancelled else _describe(exc)
        logger.warning("Import did not complete: %s", message)
        return RestoreFromBackupResult(False, message, [], skipped, status)


def _symlink_is_safe(linkname, member_name):
    if not paths.safe_link(linkname, member_name):
        return False
    target = os.path.realpath(os.path.join(paths.home(), os.path.dirname(member_name), linkname))
    return target.startswith(paths.home() + os.sep)


def get_default_backup_name():
    return f"big-restore-dotfiles-{time.strftime('%Y%m%d_%H%M%S')}-{time.time_ns() % 1_000_000_000:09d}.tar.gz"


def get_app_backup_name(app_id):
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in app_id).removeprefix("flatpak-")
    return f"biglinux-config-{safe}-{time.strftime('%Y%m%d_%H%M%S')}-{time.time_ns() % 1_000_000_000:09d}.tar.gz"


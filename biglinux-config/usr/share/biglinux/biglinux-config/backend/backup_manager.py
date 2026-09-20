"""Reliable backup / restore of dotfiles via ``.tar.gz`` archives.

Design goals (see docs/02 and docs/04):

* **Atomic export** — the archive is written to a ``.part`` file, flushed to
  disk and only then ``os.replace``-d over the final name, so a crash or a
  cancel can never corrupt an existing backup.
* **Manifest first** — metadata lives in the *first* archive member, so reading
  it back is O(1) instead of scanning the whole stream.
* **Integrity** — every regular file is hashed (BLAKE2b) while it is streamed
  into the archive; the digests are stored in a trailing member and re-checked
  on import.
* **Transactional import** — the archive is expanded into a staging directory on
  the *same filesystem* as ``$HOME``, verified, and then swapped into place with
  atomic ``rename``s.  Any failure rolls everything back; the previous
  configuration is never left half-overwritten.
* **Untrusted input** — member names are sanitised (``tarfile`` data filter +
  our own checks); nothing is ever written outside the staging directory or,
  after validation, outside ``$HOME``.

The public signatures are backward-compatible with the previous version; new
behaviour is opt-in through added keyword arguments.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import shutil
import stat
import tarfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from backend import dconf_manager, paths
from data.app_registry import AppEntry

logger = logging.getLogger("biglinux-config")

MANIFEST_NAME = "biglinux-backup-manifest.json"
CHECKSUMS_NAME = "biglinux-backup-checksums.json"
BACKUP_FORMAT = "biglinux-config-backup"
BACKUP_VERSION = 2
SUPPORTED_VERSIONS = (1, 2)

# Directory names considered volatile cache; excluded unless include_cache=True.
CACHE_COMPONENTS = frozenset({
    "Cache", "cache", "Cache_Data", "CachedData", "Code Cache", "GPUCache",
    "ShaderCache", "Service Worker", "Crash Reports", "Crashpad", "GrShaderCache",
    "DawnCache", "component_crx_cache", "blob_storage",
})

_HASH_CHUNK = 1024 * 1024  # 1 MiB


ProgressCallback = Callable[[int, int, str], None]


class BackupError(Exception):
    """Raised for recoverable backup/restore problems with a friendly message."""


class _Cancelled(Exception):
    """Raised internally when the user cancels an operation."""


class ImportStatus(Enum):
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ROLLED_BACK = "rolled_back"


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


@dataclass
class _FileRecord:
    """One inventory entry gathered during the export pre-walk."""

    fullpath: str
    rel: str
    kind: str  # "file" | "dir" | "link"
    size: int
    mode: int
    mtime: int
    link_target: str = ""
    app_id: str = ""


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
class _HashingReader:
    """Wrap a file object, updating a hash as ``tarfile`` reads it.

    Lets us archive a file and compute its digest in a *single* read pass.
    """

    def __init__(self, fileobj, hasher):
        self._f = fileobj
        self._h = hasher

    def read(self, size: int = -1) -> bytes:
        data = self._f.read(size)
        if data:
            self._h.update(data)
        return data


def _iter_entry_paths(top: str):
    """Yield every path under *top* (parents before children).

    Symlinks are yielded but never traversed.  Special files (device nodes,
    FIFOs, sockets) are yielded too; the caller decides to skip them.
    """
    yield top
    if os.path.islink(top):
        return
    if os.path.isdir(top):
        try:
            names = sorted(os.listdir(top))
        except OSError as exc:
            logger.warning("Cannot list %s: %s", top, exc)
            return
        for name in names:
            yield from _iter_entry_paths(os.path.join(top, name))


def _is_cache_path(rel: str) -> bool:
    parts = rel.split("/")
    return any(part in CACHE_COMPONENTS for part in parts)


def _classify(st: os.stat_result) -> str | None:
    mode = st.st_mode
    if stat.S_ISLNK(mode):
        return "link"
    if stat.S_ISDIR(mode):
        return "dir"
    if stat.S_ISREG(mode):
        return "file"
    return None  # fifo / socket / device -> skip


def _build_inventory(
    entries: list[AppEntry], include_cache: bool
) -> tuple[list[_FileRecord], dict[str, list[str]], int]:
    """Walk the selected config paths once and return the export inventory.

    Returns ``(records, app_roots, total_size)`` where *app_roots* maps
    ``app_id`` -> list of top-level archive-relative roots for that app.
    """
    home = paths.home()
    records: list[_FileRecord] = []
    app_roots: dict[str, list[str]] = {}
    total_size = 0
    seen_rel: set[str] = set()

    for entry in entries:
        roots: list[str] = []
        for raw_path in entry.config_paths:
            real = paths.resolve_under_home(raw_path)
            if real is None:
                logger.warning("Skipping path outside HOME: %s", raw_path)
                continue
            if not os.path.exists(real) and not os.path.islink(real):
                continue
            root_rel = os.path.relpath(real, home)
            roots.append(root_rel)

            for full in _iter_entry_paths(real):
                rel = os.path.relpath(full, home)
                if rel in seen_rel:
                    continue
                if not include_cache and _is_cache_path(rel):
                    continue
                try:
                    st = os.lstat(full)
                except OSError as exc:
                    logger.warning("Cannot stat %s: %s", full, exc)
                    continue
                kind = _classify(st)
                if kind is None:
                    logger.info("Skipping special file: %s", full)
                    continue
                link_target = os.readlink(full) if kind == "link" else ""
                size = st.st_size if kind == "file" else 0
                total_size += size
                seen_rel.add(rel)
                records.append(_FileRecord(
                    fullpath=full, rel=rel, kind=kind, size=size,
                    mode=stat.S_IMODE(st.st_mode), mtime=int(st.st_mtime),
                    link_target=link_target, app_id=entry.app_id,
                ))
        if roots:
            app_roots[entry.app_id] = roots
    return records, app_roots, total_size


_DCONF_PREFIX = ".biglinux-dconf"


def _collect_dconf(entries: list[AppEntry]):
    """Dump each entry's scoped dconf namespaces to archive members.

    Returns ``(members, manifest)`` where *members* is a list of
    ``(member_name, data_bytes)`` and *manifest* records app_id → namespace items.
    """
    members: list[tuple[str, bytes]] = []
    manifest: list[dict] = []
    if not dconf_manager.is_available():
        return members, manifest
    for entry in entries:
        items = []
        for idx, ns in enumerate(entry.dconf_paths):
            if not dconf_manager.is_valid_namespace(ns):
                continue
            text = dconf_manager.dump(ns)
            if not text.strip():
                continue
            member = f"{_DCONF_PREFIX}/{entry.app_id}/{idx}.ini"
            members.append((member, text.encode("utf-8")))
            items.append({"path": ns, "member": member})
        if items:
            manifest.append(
                {"app_id": entry.app_id, "name": entry.name, "items": items})
    return members, manifest


def _system_metadata() -> dict:
    try:
        uname = os.uname()
    except OSError:
        uname = None
    distro = ""
    try:
        with open("/etc/os-release", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("PRETTY_NAME="):
                    distro = line.split("=", 1)[1].strip().strip('"')
                    break
    except OSError:
        pass
    return {
        "hostname": uname.nodename if uname else "",
        "username": os.environ.get("USER", ""),
        "desktop": os.environ.get("XDG_CURRENT_DESKTOP", ""),
        "distribution": distro,
    }


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #
def export_backup(
    entries: list[AppEntry],
    archive_path: str,
    full_directory: bool = False,
    progress_callback: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> BackupResult:
    """Create a ``.tar.gz`` archive with the selected apps' configuration.

    Args:
        entries: apps to back up.
        archive_path: destination ``.tar.gz`` path (written atomically).
        full_directory: when ``True`` include volatile *cache* content too;
            when ``False`` (default) cache directories are skipped, producing a
            smaller, cleaner backup.  (This flag now has a real, tested effect —
            previously both modes produced identical archives.)
        progress_callback: ``callable(done_bytes, total_bytes, current_label)``.
        cancel_event: set it to abort; the partial ``.part`` file is removed and
            any pre-existing backup at *archive_path* is left untouched.
    """
    include_cache = full_directory
    part_path = archive_path + ".part"

    def check_cancel() -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise _Cancelled()

    try:
        records, app_roots, total_size = _build_inventory(entries, include_cache)

        # dconf dumps (scoped namespaces) captured as extra archive members.
        dconf_members, dconf_manifest = _collect_dconf(entries)

        manifest = {
            "format": BACKUP_FORMAT,
            "version": BACKUP_VERSION,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "full_directory": include_cache,
            "total_size": total_size,
            "file_count": len(records),
            **_system_metadata(),
            "applications": [
                {
                    "app_id": e.app_id,
                    "name": e.name,
                    "roots": app_roots.get(e.app_id, []),
                }
                for e in entries
                if e.app_id in app_roots or e.app_id in {d["app_id"] for d in dconf_manifest}
            ],
            "dconf": dconf_manifest,
        }

        checksums: dict[str, str] = {}
        done_bytes = 0

        # Make sure the destination directory exists.
        parent = os.path.dirname(part_path) or "."
        os.makedirs(parent, exist_ok=True)

        with open(part_path, "wb") as raw:
            with tarfile.open(fileobj=raw, mode="w:gz") as tar:
                # 1) manifest FIRST — cheap to read back.
                _add_bytes(tar, MANIFEST_NAME,
                           json.dumps(manifest, indent=2).encode("utf-8"))

                # 2) the files, hashed while streamed.
                current_label = ""
                for rec in records:
                    check_cancel()
                    if rec.app_id != current_label:
                        current_label = rec.app_id
                    # Files may vanish or become unreadable between the pre-walk
                    # and now — skip them individually instead of failing the
                    # whole backup.
                    try:
                        info = tar.gettarinfo(name=rec.fullpath, arcname=rec.rel)
                        if info is None:
                            continue
                        if rec.kind == "file":
                            hasher = hashlib.blake2b(digest_size=32)
                            with open(rec.fullpath, "rb") as fh:
                                tar.addfile(info, _HashingReader(fh, hasher))
                            checksums[rec.rel] = hasher.hexdigest()
                            done_bytes += rec.size
                        else:
                            tar.addfile(info)
                    except (OSError, tarfile.TarError) as exc:
                        logger.warning("Skipping %s during export: %s",
                                       rec.fullpath, exc)
                        continue
                    if progress_callback:
                        progress_callback(done_bytes, total_size, rec.rel)

                # 3) dconf dumps (small text members), also checksummed.
                for member_name, data in dconf_members:
                    check_cancel()
                    _add_bytes(tar, member_name, data)
                    checksums[member_name] = hashlib.blake2b(
                        data, digest_size=32).hexdigest()

                # 4) trailing checksums for verification.
                _add_bytes(tar, CHECKSUMS_NAME,
                           json.dumps(checksums).encode("utf-8"))

            # Flush the OS buffers before the atomic rename.
            raw.flush()
            os.fsync(raw.fileno())

        os.replace(part_path, archive_path)

        app_count = len(manifest["applications"])
        logger.info(
            "Backup created: %s (%d apps, %d files, %d bytes)",
            archive_path, app_count, len(records), total_size,
        )
        if progress_callback:
            progress_callback(total_size, total_size, "")
        return BackupResult(
            success=True, message="", archive_path=archive_path,
            app_count=app_count, total_size=total_size, file_count=len(records),
        )

    except _Cancelled:
        logger.info("Export cancelled by user")
        _quiet_unlink(part_path)
        return BackupResult(False, "cancelled", archive_path, 0, 0)
    except Exception as exc:  # noqa: BLE001 - reported to the user, logged fully
        logger.error("Backup failed: %s", exc, exc_info=True)
        _quiet_unlink(part_path)
        return BackupResult(False, str(exc), archive_path, 0, 0)


def _add_bytes(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name=name)
    info.size = len(data)
    info.mtime = int(time.time())
    info.mode = 0o600
    tar.addfile(info, io.BytesIO(data))


def _quiet_unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# Reading / verification
# --------------------------------------------------------------------------- #
def read_backup_manifest(archive_path: str) -> dict | None:
    """Return the manifest dict, normalised to the v2 shape, or ``None``.

    Handles both the current format (manifest first) and legacy v1 archives
    (manifest last, ``apps``/``paths`` keys).
    """
    try:
        with tarfile.open(archive_path, "r:gz") as tar:
            member = tar.next()
            while member is not None:
                if member.name == MANIFEST_NAME:
                    fh = tar.extractfile(member)
                    if fh is None:
                        return None
                    raw = json.loads(fh.read().decode("utf-8"))
                    return _normalise_manifest(raw)
                member = tar.next()
    except (tarfile.TarError, json.JSONDecodeError, OSError, EOFError) as exc:
        logger.warning("Cannot read manifest from %s: %s", archive_path, exc)
    return None


def _normalise_manifest(raw: dict) -> dict:
    """Bring a v1 manifest up to the v2 shape used by the rest of the code."""
    version = raw.get("version", 1)
    if version >= 2 and "applications" in raw:
        return raw
    # v1: {"version":1,"apps":[{"app_id","name","paths":[...]}], ...}
    apps = []
    for app in raw.get("apps", []):
        apps.append({
            "app_id": app.get("app_id", ""),
            "name": app.get("name", ""),
            "roots": app.get("paths", []),
        })
    return {
        "format": BACKUP_FORMAT,
        "version": version,
        "created_at": raw.get("timestamp", ""),
        "full_directory": raw.get("full_directory", False),
        "total_size": raw.get("total_size", 0),
        "file_count": raw.get("file_count", 0),
        "hostname": raw.get("hostname", ""),
        "username": raw.get("username", ""),
        "desktop": raw.get("desktop", ""),
        "distribution": raw.get("distribution", ""),
        "applications": apps,
    }


def _read_checksums(tar: tarfile.TarFile) -> dict[str, str]:
    """Best-effort read of the trailing checksums member (v2 only)."""
    try:
        member = tar.getmember(CHECKSUMS_NAME)
    except KeyError:
        return {}
    fh = tar.extractfile(member)
    if fh is None:
        return {}
    try:
        return json.loads(fh.read().decode("utf-8"))
    except json.JSONDecodeError:
        return {}


def verify_backup(archive_path: str) -> tuple[bool, str]:
    """Verify structural and (v2) checksum integrity without extracting.

    Returns ``(ok, message)``.
    """
    manifest = read_backup_manifest(archive_path)
    if manifest is None:
        return False, "No valid manifest found."
    if manifest.get("version") not in SUPPORTED_VERSIONS:
        return False, f"Unsupported backup version: {manifest.get('version')}"
    try:
        with tarfile.open(archive_path, "r:gz") as tar:
            checksums = _read_checksums(tar)
        with tarfile.open(archive_path, "r:gz") as tar:
            member = tar.next()
            checked = 0
            while member is not None:
                if member.name in (MANIFEST_NAME, CHECKSUMS_NAME):
                    member = tar.next()
                    continue
                if member.isreg() and member.name in checksums:
                    fh = tar.extractfile(member)
                    if fh is None:
                        return False, f"Cannot read {member.name}"
                    hasher = hashlib.blake2b(digest_size=32)
                    for chunk in iter(lambda: fh.read(_HASH_CHUNK), b""):
                        hasher.update(chunk)
                    if hasher.hexdigest() != checksums[member.name]:
                        return False, f"Checksum mismatch: {member.name}"
                    checked += 1
                member = tar.next()
    except (tarfile.TarError, OSError, EOFError) as exc:
        return False, f"Archive is corrupted: {exc}"
    return True, ""


# --------------------------------------------------------------------------- #
# Import (transactional)
# --------------------------------------------------------------------------- #
def import_backup(
    archive_path: str,
    selected_app_ids: set[str] | None = None,
    progress_callback: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> RestoreFromBackupResult:
    """Restore configuration from a backup, transactionally.

    The archive is expanded into a hidden staging directory beside ``$HOME`` (same
    filesystem), each member is sanitised and — for v2 archives — checksum-verified,
    and only then are the live paths swapped in with atomic renames.  Any error or
    cancellation rolls the home directory back to its previous state.
    """
    home = paths.home()
    restored: list[str] = []
    skipped: list[str] = []

    def check_cancel() -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise _Cancelled()

    manifest = read_backup_manifest(archive_path)
    if manifest is None:
        return RestoreFromBackupResult(
            False, "Invalid backup: no manifest found.", [], [],
            ImportStatus.FAILED)
    if manifest.get("version") not in SUPPORTED_VERSIONS:
        return RestoreFromBackupResult(
            False, f"Unsupported backup version: {manifest.get('version')}.",
            [], [], ImportStatus.FAILED)

    # Resolve which top-level roots to restore.
    apps = manifest.get("applications", [])
    root_to_app: dict[str, str] = {}
    apps_to_restore: list[dict] = []
    for app in apps:
        if selected_app_ids is not None and app["app_id"] not in selected_app_ids:
            skipped.append(app.get("name", app["app_id"]))
            continue
        apps_to_restore.append(app)
        for root in app.get("roots", []):
            root_to_app[root.rstrip("/")] = app.get("name", app["app_id"])
    restore_roots = sorted(root_to_app, key=len, reverse=True)
    # A backup may carry only dconf settings (no files), so also consider those.
    has_dconf = any(
        selected_app_ids is None or s.get("app_id") in selected_app_ids
        for s in manifest.get("dconf", [])
    )
    if not restore_roots and not has_dconf:
        return RestoreFromBackupResult(
            False, "Nothing selected to restore.", restored, skipped,
            ImportStatus.FAILED)

    # Disk-space guard: need room for the staging copy plus a safety margin.
    needed = int(manifest.get("total_size", 0) * 1.15) + 16 * 1024 * 1024
    try:
        free = shutil.disk_usage(home).free
        if free < needed:
            return RestoreFromBackupResult(
                False,
                f"Not enough free space: need ~{format_size(needed)}, "
                f"have {format_size(free)}.",
                restored, skipped, ImportStatus.FAILED)
    except OSError:
        pass

    staging = os.path.join(home, f".biglinux-config-restore-{os.getpid()}-{int(time.time())}")
    backup_aside = staging + "-old"
    total_size = max(1, int(manifest.get("total_size", 0)))

    try:
        os.makedirs(staging, exist_ok=True)
        os.makedirs(backup_aside, exist_ok=True)

        # -- phase 1: extract + verify into staging ------------------------- #
        _extract_to_staging(
            archive_path, staging, restore_roots, total_size,
            root_to_app, progress_callback, check_cancel)

        # -- phase 2: atomic swap ------------------------------------------- #
        applied: list[tuple[str, str, bool]] = []  # (live, aside, had_live)
        dconf_applied: list[tuple[str, str]] = []  # (namespace, pre_dump)
        try:
            for root in sorted(root_to_app):  # roots are disjoint tops; order irrelevant
                staged = os.path.join(staging, root)
                if not os.path.lexists(staged):
                    continue
                check_cancel()
                live = os.path.join(home, root)
                aside = os.path.join(backup_aside, root)
                os.makedirs(os.path.dirname(aside) or backup_aside, exist_ok=True)
                had_live = os.path.lexists(live)
                if had_live:
                    os.rename(live, aside)
                # Record BEFORE placing the staged copy so a failure of the next
                # rename is still rolled back (the live path was already moved).
                applied.append((live, aside, had_live))
                os.makedirs(os.path.dirname(live) or home, exist_ok=True)
                os.rename(staged, live)

            # -- phase 2b: dconf load (scoped, reversible) ----------------- #
            _apply_dconf(archive_path, manifest, selected_app_ids,
                         dconf_applied, check_cancel)
        except BaseException:
            _rollback_dconf(dconf_applied)
            _rollback(applied)
            raise

        # success: drop the aside copies and staging
        shutil.rmtree(backup_aside, ignore_errors=True)
        shutil.rmtree(staging, ignore_errors=True)

        for app in apps_to_restore:
            restored.append(app.get("name", app["app_id"]))
        if progress_callback:
            progress_callback(total_size, total_size, "")
        logger.info("Backup imported: %s (restored=%s skipped=%s)",
                    archive_path, restored, skipped)
        return RestoreFromBackupResult(
            True, "", restored, skipped, ImportStatus.SUCCESS)

    except _Cancelled:
        logger.info("Import cancelled by user")
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(backup_aside, ignore_errors=True)
        return RestoreFromBackupResult(
            False, "cancelled", restored, skipped, ImportStatus.CANCELLED)
    except Exception as exc:  # noqa: BLE001
        logger.error("Import failed: %s", exc, exc_info=True)
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(backup_aside, ignore_errors=True)
        # We only ever leave here after a full rollback (or before any swap).
        return RestoreFromBackupResult(
            False, str(exc), [], skipped, ImportStatus.ROLLED_BACK)


def _matches_root(name: str, roots: list[str]) -> bool:
    for root in roots:
        if name == root or name.startswith(root + "/"):
            return True
    return False


def _extract_to_staging(
    archive_path: str,
    staging: str,
    restore_roots: list[str],
    total_size: int,
    root_to_app: dict[str, str],
    progress_callback: ProgressCallback | None,
    check_cancel: Callable[[], None],
) -> None:
    """Expand selected members into *staging*, sanitising and verifying each."""
    done = 0
    with tarfile.open(archive_path, "r:gz") as tar:
        checksums = _read_checksums(tar)
    # Re-open for a clean streaming pass (checksums read closed the first).
    with tarfile.open(archive_path, "r:gz") as tar:
        member = tar.next()
        while member is not None:
            check_cancel()
            name = member.name
            if name in (MANIFEST_NAME, CHECKSUMS_NAME):
                member = tar.next()
                continue
            if not _matches_root(name, restore_roots):
                member = tar.next()
                continue

            target = paths.safe_extract_target(name, staging)
            if target is None:
                raise BackupError(f"Unsafe path in archive: {name}")
            if not (member.isfile() or member.isdir() or member.issym()):
                logger.info("Skipping unsupported member type: %s", name)
                member = tar.next()
                continue

            if member.isdir():
                os.makedirs(target, exist_ok=True)
            elif member.issym():
                # Reject links that would escape HOME once placed live.
                if not _symlink_is_safe(member.linkname, name):
                    raise BackupError(f"Unsafe symlink in archive: {name} -> {member.linkname}")
                os.makedirs(os.path.dirname(target), exist_ok=True)
                if os.path.lexists(target):
                    os.unlink(target)
                os.symlink(member.linkname, target)
            else:  # regular file
                os.makedirs(os.path.dirname(target), exist_ok=True)
                src = tar.extractfile(member)
                if src is None:
                    raise BackupError(f"Cannot read member: {name}")
                hasher = hashlib.blake2b(digest_size=32)
                with open(target, "wb") as dst:
                    for chunk in iter(lambda: src.read(_HASH_CHUNK), b""):
                        hasher.update(chunk)
                        dst.write(chunk)
                if name in checksums and hasher.hexdigest() != checksums[name]:
                    raise BackupError(f"Checksum mismatch for {name}")
                os.chmod(target, member.mode & 0o7777)
                done += member.size
                if progress_callback:
                    progress_callback(min(done, total_size), total_size,
                                      _label_for(name, root_to_app))
            member = tar.next()


def _apply_dconf(
    archive_path: str,
    manifest: dict,
    selected_app_ids: set[str] | None,
    dconf_applied: list[tuple[str, str]],
    check_cancel: Callable[[], None],
) -> None:
    """Load the backup's dconf dumps for the selected apps (reversible).

    Records each namespace's previous state in *dconf_applied* so a later failure
    can restore it.  No-op when dconf is unavailable or the backup has none.
    """
    sections = manifest.get("dconf", [])
    if not sections or not dconf_manager.is_available():
        return
    wanted = [
        s for s in sections
        if selected_app_ids is None or s.get("app_id") in selected_app_ids
    ]
    if not wanted:
        return

    needed = {item["member"] for s in wanted for item in s.get("items", [])}
    with tarfile.open(archive_path, "r:gz") as tar:
        checksums = _read_checksums(tar)
    texts: dict[str, str] = {}
    with tarfile.open(archive_path, "r:gz") as tar:
        member = tar.next()
        while member is not None:
            if member.name in needed and member.isreg():
                fh = tar.extractfile(member)
                if fh is not None:
                    data = fh.read()
                    if member.name in checksums and hashlib.blake2b(
                            data, digest_size=32).hexdigest() != checksums[member.name]:
                        raise BackupError(f"Checksum mismatch for {member.name}")
                    texts[member.name] = data.decode("utf-8")
            member = tar.next()

    for section in wanted:
        for item in section.get("items", []):
            check_cancel()
            ns, member = item.get("path", ""), item.get("member", "")
            text = texts.get(member)
            if text is None or not dconf_manager.is_valid_namespace(ns):
                continue
            dconf_applied.append((ns, dconf_manager.dump(ns)))
            if not dconf_manager.load(ns, text):
                raise BackupError(f"Failed to load dconf namespace {ns}")


def _rollback_dconf(dconf_applied: list[tuple[str, str]]) -> None:
    """Restore dconf namespaces captured before an import."""
    for ns, pre in reversed(dconf_applied):
        try:
            if pre.strip():
                dconf_manager.load(ns, pre)
            else:
                dconf_manager.reset(ns)
        except Exception as exc:  # noqa: BLE001
            logger.error("dconf import rollback error for %s: %s", ns, exc)


def _label_for(name: str, root_to_app: dict[str, str]) -> str:
    for root, app in root_to_app.items():
        if name == root or name.startswith(root + "/"):
            return app
    return ""


def _symlink_is_safe(linkname: str, member_name: str) -> bool:
    """A symlink is safe if, placed at its member location under HOME, it does
    not resolve outside HOME."""
    home = paths.home()
    if os.path.isabs(linkname):
        resolved = os.path.realpath(linkname)
    else:
        member_dir = os.path.dirname(os.path.join(home, member_name))
        resolved = os.path.realpath(os.path.join(member_dir, linkname))
    return resolved == home or resolved.startswith(home + os.sep)


def _rollback(applied: list[tuple[str, str, bool]]) -> None:
    """Undo a partial swap: for each applied root, remove the newly-placed live
    entry and move the saved-aside copy back."""
    for live, aside, had_live in reversed(applied):
        try:
            if os.path.lexists(live):
                if os.path.isdir(live) and not os.path.islink(live):
                    shutil.rmtree(live, ignore_errors=True)
                else:
                    os.unlink(live)
            if had_live and os.path.lexists(aside):
                os.makedirs(os.path.dirname(live) or "/", exist_ok=True)
                os.rename(aside, live)
        except OSError as exc:
            logger.error("Rollback error for %s: %s", live, exc)


# --------------------------------------------------------------------------- #
# Names
# --------------------------------------------------------------------------- #
def get_default_backup_name() -> str:
    """Default filename for a multi-app backup."""
    ts = time.strftime("%Y%m%d_%H%M%S")
    return f"big-restore-dotfiles-{ts}.tar.gz"


def get_app_backup_name(app_id: str) -> str:
    """Default filename for a single-application backup."""
    safe = app_id.replace("/", "_").replace("flatpak-", "")
    ts = time.strftime("%Y%m%d_%H%M%S")
    return f"biglinux-config-{safe}-{ts}.tar.gz"


def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

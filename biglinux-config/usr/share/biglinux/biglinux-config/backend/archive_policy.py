"""Strict, bounded metadata and member policy for portable configuration backups.

Checksums detect accidental corruption, NOT authenticity: import only backups
from trusted sources. Limits apply to content/metadata, not a guarantee against
all gzip/tar parser resource attacks; keep Python security updates installed.
"""
from __future__ import annotations

import json
import re
import tarfile
from dataclasses import dataclass

from backend import dconf_manager, paths

MANIFEST_NAME = "biglinux-backup-manifest.json"
CHECKSUMS_NAME = "biglinux-backup-checksums.json"
BACKUP_FORMAT = "biglinux-config-backup"
DCONF_PREFIX = ".biglinux-dconf"


class BackupError(Exception):
    """Invalid backup or operation that must not be partially applied."""


@dataclass(frozen=True)
class ArchiveLimits:
    max_members: int = 100_000
    max_total_size: int = 16 * 1024**3
    max_file_size: int = 4 * 1024**3
    max_metadata_size: int = 16 * 1024**2
    max_dconf_size: int = 4 * 1024**2
    max_path_depth: int = 64


DEFAULT_LIMITS = ArchiveLimits()
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]{0,254}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise BackupError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(tar, member, limit: int):
    if not member.isreg() or not 0 <= member.size <= limit:
        raise BackupError(f"Invalid or oversized metadata: {member.name}")
    with tar.extractfile(member) as src:
        data = src.read(limit + 1)
    if len(data) != member.size or len(data) > limit:
        raise BackupError(f"Truncated or oversized metadata: {member.name}")
    return json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object)


def normalise_manifest(raw) -> dict:
    if not isinstance(raw, dict):
        raise BackupError("Manifest must be an object.")
    version = raw.get("version", 1)
    if type(version) is not int or version not in (1, 2):
        raise BackupError("Unsupported backup version.")
    if version == 2 and raw.get("format") != BACKUP_FORMAT:
        raise BackupError("Invalid backup format.")
    if version == 1 and raw.get("format", BACKUP_FORMAT) != BACKUP_FORMAT:
        raise BackupError("Invalid legacy backup format.")
    source = raw.get("applications" if version == 2 else "apps")
    if not isinstance(source, list) or not source or len(source) > 4096:
        raise BackupError("Manifest must contain a bounded, non-empty application list.")
    apps, ids = [], set()
    for app in source:
        if not isinstance(app, dict):
            raise BackupError("Invalid application record.")
        app_id = app.get("app_id")
        if not isinstance(app_id, str) or not _ID.fullmatch(app_id) or app_id in ids:
            raise BackupError("Invalid or duplicate application ID.")
        ids.add(app_id)
        name = app.get("name", app_id)
        roots = app.get("roots" if version == 2 else "paths", [])
        if not isinstance(name, str) or len(name) > 1024:
            raise BackupError("Invalid application name.")
        if not isinstance(roots, list) or len(roots) > 4096:
            raise BackupError("Invalid application roots.")
        checked = []
        for root in roots:
            normal = paths.archive_root(root)
            if normal is None:
                raise BackupError(f"Unsafe or structural backup root: {root!r}")
            if normal not in checked:
                checked.append(normal)
        apps.append({"app_id": app_id, "name": name, "roots": checked})
    result = dict(raw)
    result.update(format=BACKUP_FORMAT, version=version, applications=apps)
    result["created_at"] = raw.get("created_at", raw.get("timestamp", ""))
    for key in ("created_at", "hostname", "username", "desktop", "distribution"):
        if not isinstance(result.get(key, ""), str) or len(result.get(key, "")) > 4096:
            raise BackupError(f"Invalid metadata field: {key}")
    for key in ("file_count", "total_size"):
        value = raw.get(key, 0)
        if type(value) is not int or value < 0:
            raise BackupError(f"Invalid metadata field: {key}")
        result[key] = value
    if type(raw.get("full_directory", False)) is not bool:
        raise BackupError("Invalid full_directory flag.")
    sections = raw.get("dconf", [])
    if not isinstance(sections, list) or len(sections) > 4096:
        raise BackupError("Invalid dconf sections.")
    seen_members, seen_namespaces, seen_apps = set(), set(), set()
    for section in sections:
        if not isinstance(section, dict) or section.get("app_id") not in ids:
            raise BackupError("Orphan dconf section.")
        app_id = section["app_id"]
        if app_id in seen_apps:
            raise BackupError("Duplicate dconf application.")
        seen_apps.add(app_id)
        items = section.get("items")
        if not isinstance(items, list) or not items or len(items) > 4096:
            raise BackupError("Invalid dconf items.")
        for item in items:
            if not isinstance(item, dict):
                raise BackupError("Invalid dconf item.")
            ns, member = item.get("path"), item.get("member")
            if not dconf_manager.is_valid_namespace(ns):
                raise BackupError("Invalid dconf namespace.")
            if (paths.archive_name(member) != member or not isinstance(member, str)
                    or not member.startswith(f"{DCONF_PREFIX}/{app_id}/")
                    or not member.endswith(".ini") or member in seen_members):
                raise BackupError("Invalid or duplicate dconf member.")
            # Shared namespaces are allowed across apps, but contradictory dumps
            # of the same namespace are rejected by the importer before mutation.
            seen_members.add(member)
            seen_namespaces.add(ns)
    for app in apps:
        if not app["roots"] and app["app_id"] not in seen_apps:
            raise BackupError(f"Application contains no restorable data: {app['app_id']}")
    result["dconf"] = sections
    return result


def validate_checksums(raw) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise BackupError("Checksums must be an object.")
    for name, digest in raw.items():
        if (paths.archive_name(name) != name or name in (MANIFEST_NAME, CHECKSUMS_NAME)
                or not isinstance(digest, str) or not _DIGEST.fullmatch(digest)):
            raise BackupError("Invalid checksum record.")
    return raw


class MemberPolicy:
    """Reject duplicate/aliased members, links as parents, and oversized input."""

    def __init__(self, limits: ArchiveLimits = DEFAULT_LIMITS):
        self.limits = limits
        self.names: dict[str, str] = {}
        self.parents: set[str] = set()
        self.total_size = 0

    def check(self, member: tarfile.TarInfo) -> str:
        name = paths.archive_name(member.name)
        if name is None or name in self.names:
            raise BackupError(f"Unsafe or duplicate archive member: {member.name!r}")
        parts = name.split("/")
        if len(parts) > self.limits.max_path_depth:
            raise BackupError("Archive path is too deep.")
        for i in range(1, len(parts)):
            parent = "/".join(parts[:i])
            if self.names.get(parent) not in (None, "dir"):
                raise BackupError(f"Non-directory archive parent: {parent}")
            self.parents.add(parent)
        if not (member.isreg() or member.isdir() or member.issym()):
            raise BackupError(f"Unsupported archive member type: {name}")
        if member.sparse is not None:
            raise BackupError(f"Sparse files are not supported: {name}")
        if name in self.parents and not member.isdir():
            raise BackupError(f"Archive member shadows a directory: {name}")
        if member.issym() and not paths.safe_link(member.linkname, name):
            raise BackupError(f"Unsafe symlink: {name}")
        if (member.size < 0 or member.size > self.limits.max_file_size
                or (not member.isreg() and member.size != 0)):
            raise BackupError(f"Invalid/oversized member: {name}")
        self.names[name] = "dir" if member.isdir() else "file"
        self.total_size += member.size
        if len(self.names) > self.limits.max_members or self.total_size > self.limits.max_total_size:
            raise BackupError("Archive resource limit exceeded.")
        return name

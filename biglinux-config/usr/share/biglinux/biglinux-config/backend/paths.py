"""Centralised, exhaustively-tested path safety helpers.

Every module that reads, writes, removes or extracts files under the user's
home directory must route its path validation through here.  The rules are:

* ``~`` and ``~user`` are expanded.
* the *real* path (symlinks resolved) must stay inside the real ``$HOME``.
* a small set of "structural" directories (``~``, ``~/.config`` …) may never be
  the direct target of a destructive operation — deleting or overwriting them
  wholesale would take unrelated applications down with it.

The functions never raise for an invalid path; they return ``None`` (or a bool)
so callers can skip-and-log instead of crashing a batch operation.
"""

from __future__ import annotations

import glob
import os
import posixpath


def xdg_home(variable: str, fallback: str) -> str:
    """Ignore empty/relative XDG values, as required by the Base Directory spec."""
    value = os.environ.get(variable, "")
    return value if os.path.isabs(value) else os.path.join(home(), fallback)


def home() -> str:
    """The user's home directory (honours a patched ``$HOME`` in tests)."""
    return os.path.realpath(os.path.expanduser("~"))


# Directories that must never be removed or replaced as a single unit.
def _structural_dirs() -> set[str]:
    h = home()
    return {
        *(os.path.realpath(xdg_home(var, default)) for var, default in (
            ("XDG_CONFIG_HOME", ".config"), ("XDG_DATA_HOME", ".local/share"),
            ("XDG_STATE_HOME", ".local/state"), ("XDG_CACHE_HOME", ".cache"),
        )),
        h,
        os.path.join(h, ".config"),
        os.path.join(h, ".local"),
        os.path.join(h, ".local", "share"),
        os.path.join(h, ".local", "state"),
        os.path.join(h, ".cache"),
        os.path.join(h, ".var"),
        os.path.join(h, ".var", "app"),
    }


def is_within(base: str, target: str) -> bool:
    """True if *target* is *base* itself or lives underneath it."""
    base = os.path.realpath(base)
    target = os.path.realpath(target)
    return target == base or target.startswith(base + os.sep)


def resolve_under_home(raw_path: str) -> str | None:
    """Expand *raw_path* and return its real path iff it stays inside ``$HOME``.

    Returns ``None`` when the path escapes home (directly or via a symlink).
    The path need not exist.
    """
    expanded = os.path.expanduser(raw_path)
    # Resolve symlinks on the parts that exist; keep the rest literal.
    real = os.path.realpath(expanded)
    h = home()
    if real == h or real.startswith(h + os.sep):
        return real
    return None


def is_structural(path: str) -> bool:
    """True if *path* resolves to a protected structural directory."""
    return os.path.realpath(os.path.expanduser(path)) in _structural_dirs()


def safe_removable(raw_path: str) -> str | None:
    """Return a lexical HOME path, never the target of a leaf symlink.

    Symlinked parents are conservatively refused, even when they currently point
    inside HOME. This does not protect against a hostile process of the same UID
    racing filesystem changes; callers must revalidate immediately before writes.
    """
    if not isinstance(raw_path, str) or not raw_path or "\0" in raw_path:
        return None
    expanded = os.path.expanduser(raw_path)
    if not os.path.isabs(expanded):
        return None
    target = os.path.abspath(expanded)
    h = home()
    if not target.startswith(h + os.sep) or target in _structural_dirs():
        return None
    relative = os.path.relpath(target, h)
    if relative.split(os.sep)[0].startswith(".biglinux-config-"):
        return None  # never include transaction/recovery state in a reset
    # The binary dconf database covers unrelated apps; use scoped dconf APIs.
    for dconf_dir in {os.path.join(h, ".config", "dconf"),
                      os.path.join(xdg_home("XDG_CONFIG_HOME", ".config"), "dconf")}:
        if target == dconf_dir or target.startswith(dconf_dir + os.sep):
            return None
    parent = os.path.dirname(target)
    while parent != h:
        if os.path.islink(parent):
            return None
        parent = os.path.dirname(parent)
    return target


def safe_destination(raw_path: str) -> str | None:
    """Same safety boundary as removal; replacement never follows a leaf link."""
    return safe_removable(raw_path)


def expand_targets(raw_paths: list[str]) -> list[str]:
    """Expand globs deterministically and deduplicate overlapping existing roots."""
    found = set()
    for raw in raw_paths:
        expanded = os.path.expanduser(raw)
        candidates = glob.glob(expanded) if glob.has_magic(expanded) else [expanded]
        for candidate in candidates:
            if os.path.lexists(candidate):
                found.add(os.path.abspath(candidate))
    roots: list[str] = []
    for candidate in sorted(found, key=lambda p: (len(p), p)):
        if not any(candidate.startswith(root + os.sep) for root in roots):
            roots.append(candidate)
    return roots


def archive_name(name: str) -> str | None:
    """Accept canonical relative POSIX names, without control characters."""
    if not isinstance(name, str) or not name or len(name) > 4096:
        return None
    if name.startswith("/") or "\\" in name or any(ord(c) < 32 or ord(c) == 127 for c in name):
        return None
    # Tar directory names can have a single trailing slash, but no aliases.
    name = name.removesuffix("/")
    if not name or any(p in ("", ".", "..") for p in name.split("/")):
        return None
    return name


def archive_root(name: str) -> str | None:
    normal = archive_name(name)
    if normal in ("biglinux-backup-manifest.json", "biglinux-backup-checksums.json", ".biglinux-dconf"):
        return None
    if normal is None or safe_destination(os.path.join(home(), normal)) is None:
        return None
    return normal


def safe_link(link: str, member: str) -> bool:
    """Only portable relative links that stay lexically inside the archive."""
    if not isinstance(link, str) or not link or len(link) > 4096:
        return False
    if link.startswith("/") or "\\" in link or any(ord(c) < 32 for c in link):
        return False
    target = posixpath.normpath(posixpath.join(posixpath.dirname(member), link))
    return target not in (".", "..") and not target.startswith("../")


def safe_extract_target(member_name: str, dest_root: str) -> str | None:
    """Validate an archive member name for extraction under *dest_root*.

    Rejects absolute paths, ``..`` traversal and anything that would resolve
    outside *dest_root* (e.g. through a symlinked parent).
    """
    name = archive_name(member_name)
    if name is None:
        return None
    target = os.path.join(os.path.abspath(dest_root), name)
    root = os.path.abspath(dest_root)
    # Do not follow even an in-tree symlink when writing subsequent members.
    parent = target
    while parent != root:
        if os.path.islink(parent):
            return None
        parent = os.path.dirname(parent)
    return target

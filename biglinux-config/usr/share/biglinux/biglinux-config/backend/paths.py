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

import os
from pathlib import Path


def home() -> str:
    """The user's home directory (honours a patched ``$HOME`` in tests)."""
    return os.path.realpath(os.path.expanduser("~"))


# Directories that must never be removed or replaced as a single unit.
def _structural_dirs() -> set[str]:
    h = home()
    return {
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
    """Return the real path if it is safe to *remove*, else ``None``.

    Safe means: inside ``$HOME`` and not a structural directory.
    """
    real = resolve_under_home(raw_path)
    if real is None:
        return None
    if real in _structural_dirs():
        return None
    return real


def safe_destination(raw_path: str) -> str | None:
    """Return the real path if it is safe to *write/replace*, else ``None``.

    Same rules as :func:`safe_removable`; kept as a separate name for intent.
    """
    return safe_removable(raw_path)


def safe_extract_target(member_name: str, dest_root: str) -> str | None:
    """Validate an archive member name for extraction under *dest_root*.

    Rejects absolute paths, ``..`` traversal and anything that would resolve
    outside *dest_root* (e.g. through a symlinked parent).
    """
    if member_name.startswith(("/", os.sep)):
        return None
    # Reject any parent-traversal component up-front.
    parts = Path(member_name).parts
    if ".." in parts:
        return None
    target = os.path.realpath(os.path.join(dest_root, member_name))
    root = os.path.realpath(dest_root)
    if target == root or target.startswith(root + os.sep):
        return target
    return None

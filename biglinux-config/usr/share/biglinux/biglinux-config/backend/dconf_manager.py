"""Safe, namespace-scoped dconf (GSettings) support.

dconf stores settings in a per-user database, not in dotfiles, so it needs a
dedicated path.  Everything here operates on **specific namespaces** only
(e.g. ``/org/gnome/desktop/interface/``); a full-database dump/reset is never
performed — that would wipe unrelated GNOME settings.
"""

from __future__ import annotations

import logging
import shutil
import subprocess

logger = logging.getLogger("biglinux-config")

_TIMEOUT = 15


def is_available() -> bool:
    """True if the ``dconf`` CLI is present."""
    return shutil.which("dconf") is not None


def is_valid_namespace(path: str) -> bool:
    """A safe dconf namespace: absolute, ends with '/', at least two segments.

    Rejects ``/`` and single-segment roots so a reset can never wipe the whole
    database or a broad top-level tree.
    """
    if not path.startswith("/") or not path.endswith("/"):
        return False
    segments = [s for s in path.split("/") if s]
    return len(segments) >= 2


def dump(path: str) -> str:
    """Return the INI dump of *path*'s subtree, or '' on error/empty."""
    if not is_valid_namespace(path):
        logger.warning("Refusing dconf dump of unsafe namespace: %s", path)
        return ""
    try:
        result = subprocess.run(
            ["dconf", "dump", path],
            capture_output=True, text=True, timeout=_TIMEOUT,
        )
        if result.returncode == 0:
            return result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.warning("dconf dump failed for %s: %s", path, exc)
    return ""


def load(path: str, text: str) -> bool:
    """Load INI *text* into the *path* subtree. Returns success."""
    if not is_valid_namespace(path):
        logger.warning("Refusing dconf load into unsafe namespace: %s", path)
        return False
    try:
        result = subprocess.run(
            ["dconf", "load", path],
            input=text, text=True, capture_output=True, timeout=_TIMEOUT,
        )
        if result.returncode == 0:
            return True
        logger.error("dconf load failed for %s: %s", path, result.stderr.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.error("dconf load error for %s: %s", path, exc)
    return False


def reset(path: str) -> bool:
    """Reset (remove) the *path* subtree to schema defaults. Returns success."""
    if not is_valid_namespace(path):
        logger.warning("Refusing dconf reset of unsafe namespace: %s", path)
        return False
    try:
        result = subprocess.run(
            ["dconf", "reset", "-f", path],
            capture_output=True, text=True, timeout=_TIMEOUT,
        )
        if result.returncode == 0:
            return True
        logger.error("dconf reset failed for %s: %s", path, result.stderr.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.error("dconf reset error for %s: %s", path, exc)
    return False


def has_content(paths: list[str]) -> bool:
    """True if any of the namespaces currently holds user values."""
    return any(dump(p).strip() for p in paths if is_valid_namespace(p))

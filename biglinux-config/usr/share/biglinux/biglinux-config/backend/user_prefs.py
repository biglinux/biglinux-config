"""Validated, atomic preferences shared by Favorites and the welcome dialog."""
from __future__ import annotations

import fcntl
import json
import logging
import os
import threading
from pathlib import Path

from backend import paths
from backend.transactions import atomic_json

_ADDED_KEY = "favorites-added"
_REMOVED_KEY = "favorites-removed"
_MAX_BYTES = 1024 * 1024
_gate = threading.RLock()
logger = logging.getLogger("biglinux-config")


def _path() -> Path:
    return Path(paths.xdg_home("XDG_CONFIG_HOME", ".config")) / "restore-settings/settings.json"


def _load() -> dict:
    try:
        with _path().open("rb") as source:
            raw = source.read(_MAX_BYTES + 1)
        if len(raw) > _MAX_BYTES:
            raise ValueError("Settings file exceeds its size limit.")
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (ValueError, UnicodeError, OSError) as exc:
        logger.warning("Cannot read preferences: %s", exc)
        return {}


def _save(data: dict) -> None:
    # Errors propagate: a UI must not claim a failed preference change persisted.
    atomic_json(_path(), data)


def _ids(data: dict, key: str) -> set[str]:
    values = data.get(key, [])
    if not isinstance(values, list) or len(values) > 4096:
        return set()
    return {value for value in values if isinstance(value, str) and 0 < len(value) <= 256}


def _update(change) -> None:
    """Serialize the whole read-modify-write, including independent processes."""
    with _gate:
        directory = _path().parent
        directory.mkdir(parents=True, mode=0o700, exist_ok=True)
        fd = os.open(directory / "settings.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            data = _load()
            change(data)
            _save(data)
        finally:
            os.close(fd)


def get_added() -> set[str]:
    return _ids(_load(), _ADDED_KEY)


def get_removed() -> set[str]:
    return _ids(_load(), _REMOVED_KEY)


def _edit_favorite(app_id: str, add: bool) -> None:
    if not isinstance(app_id, str) or not 0 < len(app_id) <= 256:
        raise ValueError("Invalid favorite application ID.")
    def change(data):
        added, removed = _ids(data, _ADDED_KEY), _ids(data, _REMOVED_KEY)
        (added if add else removed).add(app_id)
        (removed if add else added).discard(app_id)
        data[_ADDED_KEY], data[_REMOVED_KEY] = sorted(added), sorted(removed)
    _update(change)


def add_favorite(app_id: str) -> None:
    _edit_favorite(app_id, True)


def remove_favorite(app_id: str) -> None:
    _edit_favorite(app_id, False)


def resolve_favorite_ids(auto_ids: set[str]) -> set[str]:
    data = _load()
    return (auto_ids | _ids(data, _ADDED_KEY)) - _ids(data, _REMOVED_KEY)


def get_show_welcome() -> bool:
    return _load().get("show-welcome") is not False


def set_show_welcome(show: bool) -> None:
    _update(lambda data: data.update({"show-welcome": bool(show)}))

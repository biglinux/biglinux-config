"""Small persistent user-preferences store.

Backs the editable Favorites (apps the user pinned or unpinned) on top of the
auto-detected favorites.  Uses the same ``settings.json`` as the welcome dialog,
with careful read-modify-write so unrelated keys (e.g. ``show-welcome``) survive.
"""

from __future__ import annotations

import json
import os
import pathlib

_CONFIG_DIR = pathlib.Path(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
) / "restore-settings"
_CONFIG_FILE = _CONFIG_DIR / "settings.json"

_ADDED_KEY = "favorites-added"
_REMOVED_KEY = "favorites-removed"


def _load() -> dict:
    try:
        if _CONFIG_FILE.is_file():
            return json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _save(data: dict) -> None:
    try:
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        _CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


def get_added() -> set[str]:
    return set(_load().get(_ADDED_KEY, []))


def get_removed() -> set[str]:
    return set(_load().get(_REMOVED_KEY, []))


def _write_sets(added: set[str], removed: set[str]) -> None:
    data = _load()
    data[_ADDED_KEY] = sorted(added)
    data[_REMOVED_KEY] = sorted(removed)
    _save(data)


def add_favorite(app_id: str) -> None:
    """Pin *app_id* to favorites (overrides a previous removal)."""
    added, removed = get_added(), get_removed()
    added.add(app_id)
    removed.discard(app_id)
    _write_sets(added, removed)


def remove_favorite(app_id: str) -> None:
    """Unpin *app_id* from favorites (also hides an auto-detected favorite)."""
    added, removed = get_added(), get_removed()
    added.discard(app_id)
    removed.add(app_id)
    _write_sets(added, removed)


def resolve_favorite_ids(auto_ids: set[str]) -> set[str]:
    """Final favorite id set: (auto ∪ user-added) − user-removed."""
    return (auto_ids | get_added()) - get_removed()

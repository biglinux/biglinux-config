import json
import os
import threading

import pytest
from backend import user_prefs as prefs


@pytest.mark.parametrize("payload", ["[]", "null", "true", '"string"', "{broken", "42", '{"favorites-added": [[], {}, 1]}', '{"favorites-added": "letters"}'])
def test_invalid_preferences_do_not_crash(fake_home, payload):
    prefs._path().parent.mkdir(parents=True)
    prefs._path().write_text(payload)
    assert prefs.get_added() == set()
    assert prefs.get_show_welcome()


def test_invalid_encoding_is_safe(fake_home):
    prefs._path().parent.mkdir(parents=True)
    prefs._path().write_bytes(b"\xff\xfe")
    assert prefs.get_removed() == set()


def test_unrelated_keys_and_welcome_survive_favorite_edits(fake_home):
    prefs._save({"custom-key": "keep", "show-welcome": False})
    prefs.add_favorite("first")
    prefs.remove_favorite("second")
    data = prefs._load()
    assert data["custom-key"] == "keep" and data["show-welcome"] is False
    assert prefs.resolve_favorite_ids({"second"}) == {"first"}
    prefs.set_show_welcome(True)
    assert prefs.get_added() == {"first"}
    assert prefs._path().stat().st_mode & 0o777 == 0o600


def test_failed_write_preserves_previous_preferences(fake_home, monkeypatch):
    prefs.add_favorite("first")
    def fail(*args):
        raise OSError("disk full")
    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError):
        prefs.add_favorite("second")
    assert prefs.get_added() == {"first"}
    assert not list(prefs._path().parent.glob(".settings-*"))


@pytest.mark.parametrize("xdg", ["", "relative/path"])
def test_empty_and_relative_xdg_fall_back_to_home(fake_home, monkeypatch, xdg):
    monkeypatch.setenv("XDG_CONFIG_HOME", xdg)
    prefs.add_favorite("test")
    assert prefs._path() == fake_home / ".config/restore-settings/settings.json"


def test_threaded_updates_do_not_lose_keys(fake_home):
    errors = []
    def pin(index):
        try:
            prefs.add_favorite(f"app-{index}")
        except Exception as exc:
            errors.append(exc)
    threads = [threading.Thread(target=pin, args=(index,)) for index in range(12)]
    for thread in threads: thread.start()
    for thread in threads: thread.join(timeout=3)
    assert not errors
    assert prefs.get_added() == {f"app-{index}" for index in range(12)}

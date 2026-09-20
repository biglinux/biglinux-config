"""Tests for the editable-favorites persistence store."""

from __future__ import annotations

import json

import backend.user_prefs as up


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(up, "_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(up, "_CONFIG_FILE", tmp_path / "settings.json")


def test_add_and_resolve(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    assert up.get_added() == set()
    up.add_favorite("firefox")
    assert "firefox" in up.get_added()
    assert up.resolve_favorite_ids(set()) == {"firefox"}


def test_remove_hides_auto_favorite(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    up.remove_favorite("dolphin")
    assert "dolphin" in up.get_removed()
    # An auto-detected favorite is hidden once removed.
    assert up.resolve_favorite_ids({"dolphin"}) == set()


def test_readd_clears_removed(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    up.remove_favorite("vlc")
    up.add_favorite("vlc")
    assert "vlc" not in up.get_removed()
    assert up.resolve_favorite_ids({"vlc"}) == {"vlc"}


def test_preserves_unrelated_keys(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    (tmp_path / "settings.json").write_text(json.dumps({"show-welcome": False}))
    up.add_favorite("gimp")
    data = json.loads((tmp_path / "settings.json").read_text())
    assert data["show-welcome"] is False  # untouched
    assert "gimp" in data["favorites-added"]


def test_resolve_union_minus_removed(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    up.add_favorite("kate")
    up.remove_favorite("steam")
    result = up.resolve_favorite_ids({"steam", "konsole"})
    assert result == {"kate", "konsole"}

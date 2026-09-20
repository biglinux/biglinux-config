"""Static integrity checks for the application registry."""

from __future__ import annotations

import os

import pytest

from data.app_registry import (
    APP_REGISTRY, CATEGORIES, CATEGORY_IDS, STATIC_FAVORITE_IDS,
)
from backend import paths


def test_categories_unique_and_referenced():
    ids = [c["id"] for c in CATEGORIES]
    assert len(ids) == len(set(ids))
    for c in CATEGORIES:
        assert c["id"] and c["label"] and c["icon"]


def test_app_ids_unique():
    ids = [e.app_id for e in APP_REGISTRY]
    assert len(ids) == len(set(ids)), "duplicate app_id in registry"


def test_every_entry_is_well_formed():
    for e in APP_REGISTRY:
        assert e.app_id, "empty app_id"
        assert e.name, f"{e.app_id}: empty name"
        assert e.binary, f"{e.app_id}: empty binary"
        assert e.category in CATEGORY_IDS, f"{e.app_id}: bad category {e.category}"
        assert isinstance(e.config_paths, list)


def test_config_paths_are_home_relative():
    for e in APP_REGISTRY:
        for p in e.config_paths:
            assert p.startswith("~"), f"{e.app_id}: config path not under ~: {p}"
            # No traversal in registered paths.
            assert ".." not in p.split("/"), f"{e.app_id}: traversal in {p}"


def test_skel_paths_are_under_skel_and_never_structural():
    """Guards against the catastrophic ~/.config / ~/.local wipe."""
    forbidden = {".config", ".local", ".local/share", ".cache", ".", ""}
    for e in APP_REGISTRY:
        for p in e.skel_paths:
            assert p.startswith("/etc/skel"), f"{e.app_id}: skel not under /etc/skel: {p}"
            rel = os.path.relpath(p, "/etc/skel")
            assert rel not in forbidden, (
                f"{e.app_id}: skel maps to structural dir ~/{rel} — would wipe "
                f"unrelated app configs"
            )


def test_no_entry_with_empty_config_and_no_skel():
    """An entry that can neither reset nor restore anything is dead weight."""
    dead = [e.app_id for e in APP_REGISTRY if not e.config_paths and not e.skel_paths]
    assert dead == [], f"entries with nothing to act on: {dead}"


def test_favorites_reference_real_ids():
    all_ids = {e.app_id for e in APP_REGISTRY}
    for fid in STATIC_FAVORITE_IDS:
        assert fid in all_ids, f"favorite {fid} not in registry"

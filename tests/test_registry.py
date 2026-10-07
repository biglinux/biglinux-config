"""Static integrity checks for the application registry."""

from __future__ import annotations

import os

from data.app_registry import (
    APP_REGISTRY,
    CATEGORIES,
    CATEGORY_IDS,
    STATIC_FAVORITE_IDS,
    SENSITIVE_CATEGORIES,
    is_sensitive,
)


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
            assert p.startswith("/etc/skel"), (
                f"{e.app_id}: skel not under /etc/skel: {p}"
            )
            rel = os.path.relpath(p, "/etc/skel")
            assert rel not in forbidden, (
                f"{e.app_id}: skel maps to structural dir ~/{rel} — would wipe "
                f"unrelated app configs"
            )


def test_no_entry_with_nothing_to_act_on():
    """An entry that can neither reset nor restore anything is dead weight."""
    dead = [
        e.app_id
        for e in APP_REGISTRY
        if not e.config_paths and not e.skel_paths and not e.dconf_paths
    ]
    assert dead == [], f"entries with nothing to act on: {dead}"


def test_dconf_paths_are_valid_namespaces():
    for e in APP_REGISTRY:
        for ns in e.dconf_paths:
            assert ns.startswith("/") and ns.endswith("/"), (
                f"{e.app_id}: bad dconf namespace {ns}"
            )
            segments = [s for s in ns.split("/") if s]
            assert len(segments) >= 2, f"{e.app_id}: dconf namespace too broad {ns}"


def test_favorites_reference_real_ids():
    all_ids = {e.app_id for e in APP_REGISTRY}
    for fid in STATIC_FAVORITE_IDS:
        assert fid in all_ids, f"favorite {fid} not in registry"


def test_sensitive_flag_is_bool():
    for e in APP_REGISTRY:
        assert isinstance(e.sensitive, bool), f"{e.app_id}: sensitive not bool"


def test_sensitive_categories_are_flagged():
    for e in APP_REGISTRY:
        if e.category in SENSITIVE_CATEGORIES:
            assert is_sensitive(e), f"{e.app_id} in sensitive category but not flagged"


def test_known_secret_apps_are_sensitive():
    by_id = {e.app_id: e for e in APP_REGISTRY}
    for app_id in (
        "bash",
        "zsh",
        "keepassxc",
        "bitwarden",
        "rclone",
        "firefox",
        "discord",
    ):
        if app_id in by_id:
            assert is_sensitive(by_id[app_id]), f"{app_id} should be sensitive"


def test_non_sensitive_stays_non_sensitive():
    by_id = {e.app_id: e for e in APP_REGISTRY}
    # A plain media player config is not secret.
    for app_id in ("vlc", "mpv", "htop"):
        if app_id in by_id:
            assert not is_sensitive(by_id[app_id]), f"{app_id} wrongly sensitive"


def test_names_unique_and_binaries_absolute():
    names = [e.name for e in APP_REGISTRY]
    assert len(names) == len(set(names)), "duplicate display name in registry"
    for e in APP_REGISTRY:
        assert os.path.isabs(e.binary), f"{e.app_id}: binary must be an absolute path"


def test_reset_paths_are_covered_by_the_safety_backup():
    """Back up first exports config_paths; anything reset must be inside them."""
    from data.app_registry import get_reset_paths
    for e in APP_REGISTRY:
        for reset in get_reset_paths(e):
            assert any(reset == p or reset.startswith(p + "/") for p in e.config_paths), (
                f"{e.app_id}: {reset} would be reset without being backed up")


def test_reset_never_removes_shared_or_personal_data():
    shared = {"~/.config/gtk-3.0", "~/.config/gtk-4.0", "~/.config/autostart",
              "~/.local/share/applications", "~/.local/share/icons", "~/.local/share/fonts",
              "~/.ssh", "~/.gnupg", "~/.local/bin", "~/.local/share/Trash",
              "~/.local/share/Steam", "~/.local/share/gnome-boxes"}
    from data.app_registry import get_reset_paths
    for e in APP_REGISTRY:
        for reset in get_reset_paths(e):
            assert reset not in shared, f"{e.app_id}: resets shared folder {reset}"
            assert "history" not in reset, f"{e.app_id}: resets history {reset}"


def test_registry_paths_are_canonical():
    for e in APP_REGISTRY:
        for p in [*e.config_paths, *(e.reset_paths or [])]:
            assert p == os.path.normpath(p) and not p.endswith("/"), f"{e.app_id}: {p}"
            assert p.startswith("~/"), f"{e.app_id}: {p}"
        assert len(e.config_paths) == len(set(e.config_paths)), e.app_id


def test_icon_names_are_plain():
    for e in APP_REGISTRY:
        assert e.icon and "/" not in e.icon and " " not in e.icon, e.app_id

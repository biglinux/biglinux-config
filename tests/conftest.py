"""Shared pytest fixtures.

Every test runs with HOME and the XDG directories inside its own temporary
directory, and without the user's session bus, so neither the real
configuration nor the real dconf database can be touched, even when pytest is
started directly instead of through tools/check.sh.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Assertions compare English messages: pin the locale before i18n is imported.
os.environ["LC_ALL"] = "C.UTF-8"
os.environ.pop("LANGUAGE", None)

# Make the application package importable (backend/, data/, ...).
APP_ROOT = (
    Path(__file__).resolve().parent.parent
    / "biglinux-config" / "usr" / "share" / "biglinux" / "biglinux-config"
)
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))


_XDG = (("XDG_CONFIG_HOME", ".config"), ("XDG_DATA_HOME", ".local/share"),
        ("XDG_STATE_HOME", ".local/state"), ("XDG_CACHE_HOME", ".cache"))


@pytest.fixture(autouse=True)
def isolated_environment(tmp_path_factory, monkeypatch):
    sandbox = os.environ.get("BIGLINUX_TEST_DCONF")
    if sandbox:
        # tools/check-dconf.sh isolated HOME before starting a private bus;
        # dconf-service keeps that HOME, so it must not change per test.
        home = os.path.realpath(os.environ["HOME"])
        if not os.path.isabs(sandbox) or not home.startswith(os.path.realpath(sandbox) + os.sep):
            pytest.exit("dconf tests run only through tools/check-dconf.sh", returncode=2)
        return Path(home)
    home = tmp_path_factory.mktemp("isolated-home")
    monkeypatch.setenv("HOME", str(home))
    for name, suffix in _XDG:
        monkeypatch.setenv(name, str(home / suffix))
    monkeypatch.delenv("DBUS_SESSION_BUS_ADDRESS", raising=False)
    monkeypatch.delenv("DCONF_PROFILE", raising=False)
    return home


@pytest.fixture(autouse=True)
def test_registry(monkeypatch):
    """Per-test copy of the app registry; ``register`` adds synthetic apps
    so imports accept their roots like those of real registered apps."""
    from backend import backup_manager
    from data.app_registry import APP_REGISTRY, AppEntry

    registry = list(APP_REGISTRY) + [AppEntry(
        app_id="app", name="App", icon="", binary="/bin/true",
        category="system", config_paths=["~/.config/app"])]
    monkeypatch.setattr(backup_manager, "APP_REGISTRY", registry, raising=False)
    return registry


def register(entry):
    from backend import backup_manager
    backup_manager.APP_REGISTRY.insert(0, entry)
    return entry


@pytest.fixture()
def fake_home(tmp_path, monkeypatch):
    """Provide an isolated $HOME and chdir-safe environment.

    Patches HOME and os.path.expanduser so any code using ``~`` resolves
    inside the sandbox.
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    for name, suffix in _XDG:
        monkeypatch.setenv(name, str(home / suffix))
    # os.path.expanduser honours $HOME on POSIX, but be explicit and robust.
    real_expanduser = os.path.expanduser

    def _expand(path: str) -> str:
        if path == "~":
            return str(home)
        if path.startswith("~/"):
            return str(home / path[2:])
        return real_expanduser(path)

    monkeypatch.setattr(os.path, "expanduser", _expand)
    return home


@pytest.fixture()
def fake_skel(tmp_path):
    """An isolated /etc/skel replacement."""
    skel = tmp_path / "skel"
    skel.mkdir()
    return skel


def make_tree(root: Path, spec: dict) -> None:
    """Create files/dirs from a nested dict.

    Values that are str -> file contents; dict -> subdirectory.
    """
    root.mkdir(parents=True, exist_ok=True)
    for name, value in spec.items():
        target = root / name
        if isinstance(value, dict):
            make_tree(target, value)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(value, encoding="utf-8")

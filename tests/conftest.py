"""Shared pytest fixtures.

All tests run against an artificial HOME under a TemporaryDirectory so the
real user configuration is never touched.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Make the application package importable (backend/, data/, ...).
APP_ROOT = (
    Path(__file__).resolve().parent.parent
    / "biglinux-config" / "usr" / "share" / "biglinux" / "biglinux-config"
)
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))


@pytest.fixture()
def fake_home(tmp_path, monkeypatch):
    """Provide an isolated $HOME and chdir-safe environment.

    Patches HOME and os.path.expanduser so any code using ``~`` resolves
    inside the sandbox.
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
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
def fake_skel(tmp_path, monkeypatch):
    """An isolated /etc/skel replacement, wired into reset_manager."""
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

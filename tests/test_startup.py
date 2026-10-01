"""Headless tests for startup failures; these do not claim native GTK coverage."""
import builtins
import sys
from types import SimpleNamespace

import main


def test_old_python_fails_before_gi(monkeypatch, capsys):
    monkeypatch.setattr(sys, "version_info", (3, 11, 0))
    assert main.main() == 1
    assert "Python 3.12" in capsys.readouterr().err


def test_root_is_refused_before_ui_import(monkeypatch, capsys):
    monkeypatch.setattr(main.os, "geteuid", lambda: 0)
    assert main.main() == 1
    assert "sudo/root" in capsys.readouterr().err


def test_missing_gi_fails_with_actionable_message(monkeypatch, capsys):
    monkeypatch.setattr(main.os, "geteuid", lambda: 1000)
    original = builtins.__import__
    def missing(name, *args, **kwargs):
        if name == "gi":
            raise ImportError("test: no gi")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", missing)
    assert main.main() == 1
    assert "Install PyGObject" in capsys.readouterr().err


def test_version_tuple():
    module = SimpleNamespace(get_major_version=lambda: 4,
                             get_minor_version=lambda: 12,
                             get_micro_version=lambda: 5)
    assert main._version(module) == (4, 12, 5)

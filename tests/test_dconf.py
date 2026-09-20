"""dconf (GSettings) support — reset and backup round-trip.

Uses a throwaway scratch namespace so the real user database is never touched
beyond that namespace, which is reset before and after each test.
"""

from __future__ import annotations

import os

import pytest

import backend.dconf_manager as dc
import backend.reset_manager as rm
import backend.backup_manager as bm
from backend.backup_manager import ImportStatus
from data.app_registry import AppEntry

pytestmark = pytest.mark.skipif(
    not dc.is_available(), reason="dconf CLI not available")


@pytest.fixture()
def scratch_ns():
    ns = f"/org/biglinuxconfigtest{os.getpid()}/"
    dc.reset(ns)
    yield ns
    dc.reset(ns)


def _entry(ns, app_id="x"):
    return AppEntry(
        app_id=app_id, name=app_id.title(), icon="", binary="/bin/true",
        category="customization", config_paths=[], dconf_paths=[ns],
    )


# --------------------------------------------------------------------------- #
# Namespace validation (guards against wiping the whole database)
# --------------------------------------------------------------------------- #
def test_valid_namespace_rules():
    assert not dc.is_valid_namespace("/")          # whole DB
    assert not dc.is_valid_namespace("/org/")       # single segment
    assert not dc.is_valid_namespace("org/gnome/")  # not absolute
    assert not dc.is_valid_namespace("/org/gnome")  # no trailing slash
    assert dc.is_valid_namespace("/org/gnome/")


def test_dump_load_reset_roundtrip(scratch_ns):
    assert dc.load(scratch_ns, "[/]\nkey='value'\n")
    assert "value" in dc.dump(scratch_ns)
    assert dc.has_content([scratch_ns])
    assert dc.reset(scratch_ns)
    assert dc.dump(scratch_ns).strip() == ""


def test_reset_refuses_root():
    # Never allow resetting the entire database.
    assert dc.reset("/") is False


# --------------------------------------------------------------------------- #
# Reset integration
# --------------------------------------------------------------------------- #
def test_reset_app_clears_dconf(scratch_ns):
    dc.load(scratch_ns, "[/]\ncolor='blue'\n")
    res = rm.reset_app(_entry(scratch_ns), rm.ResetMode.PROGRAM_DEFAULT)
    assert res.status is rm.ResetStatus.SUCCESS
    assert dc.dump(scratch_ns).strip() == ""


def test_has_config_true_for_dconf_only(scratch_ns):
    dc.load(scratch_ns, "[/]\nx='1'\n")
    assert rm.has_config(_entry(scratch_ns)) is True


# --------------------------------------------------------------------------- #
# Backup round-trip
# --------------------------------------------------------------------------- #
def test_backup_roundtrip_dconf(tmp_path, scratch_ns):
    dc.load(scratch_ns, "[/]\nmode='A'\n")
    entry = _entry(scratch_ns)
    arc = tmp_path / "d.tar.gz"
    assert bm.export_backup([entry], str(arc)).success

    # mutate to B, then import the backup back
    dc.load(scratch_ns, "[/]\nmode='B'\n")
    assert "'B'" in dc.dump(scratch_ns)
    res = bm.import_backup(str(arc))
    assert res.status is ImportStatus.SUCCESS, res.message
    assert "'A'" in dc.dump(scratch_ns)


def test_dconf_recorded_in_manifest(tmp_path, scratch_ns):
    dc.load(scratch_ns, "[/]\nk='v'\n")
    arc = tmp_path / "d2.tar.gz"
    bm.export_backup([_entry(scratch_ns)], str(arc))
    man = bm.read_backup_manifest(str(arc))
    assert man.get("dconf"), "dconf section missing from manifest"
    assert man["dconf"][0]["app_id"] == "x"
    assert man["dconf"][0]["items"][0]["path"] == scratch_ns


def test_import_dconf_rollback_restores_previous(tmp_path, scratch_ns, monkeypatch):
    dc.load(scratch_ns, "[/]\nmode='A'\n")
    arc = tmp_path / "d3.tar.gz"
    bm.export_backup([_entry(scratch_ns)], str(arc))
    dc.load(scratch_ns, "[/]\nmode='CURRENT'\n")

    # Fail only the load of the imported value ('A'); let the rollback load
    # (of the captured 'CURRENT' dump) go through so restoration can be checked.
    real_load = dc.load

    def selective(ns, text):
        if "'A'" in text:
            return False
        return real_load(ns, text)

    monkeypatch.setattr(bm.dconf_manager, "load", selective)
    res = bm.import_backup(str(arc))
    assert res.success is False
    assert res.status is ImportStatus.ROLLED_BACK
    # The pre-import value was restored by the rollback.
    assert "'CURRENT'" in dc.dump(scratch_ns)

"""Positive regression tests for untrusted metadata and path policy."""
import tarfile

import pytest

from backend import paths, dconf_manager
from backend.archive_policy import (
    ArchiveLimits, BackupError, MemberPolicy, normalise_manifest, validate_checksums,
)


def manifest(roots=None):
    return {"format": "biglinux-config-backup", "version": 2,
            "applications": [{"app_id": "app", "name": "App",
                              "roots": [".config/app"] if roots is None else roots}]}


@pytest.mark.parametrize("root", [".", "", "/tmp/x", "../x", ".config", ".local",
    ".local/share", ".var/app", ".config/../x", ".config//app", ".config/dconf",
    ".config/dconf/user", ".biglinux-config-reset-old", "a\\b", ".biglinux-dconf"])
def test_unsafe_manifest_roots_are_rejected(fake_home, root):
    with pytest.raises(BackupError):
        normalise_manifest(manifest([root]))


@pytest.mark.parametrize("raw", [None, [], "x", 7, {"version": True},
    {"version": "2"}, {"version": 500}, {"format": "wrong", "version": 2}])
def test_invalid_manifest_types_are_rejected(fake_home, raw):
    with pytest.raises(BackupError):
        normalise_manifest(raw)


def test_valid_nested_roots_can_share_data(fake_home):
    data = manifest([".config/app", ".config/app/sub"])
    assert len(normalise_manifest(data)["applications"][0]["roots"]) == 2


def test_reset_removes_link_not_target(fake_home):
    target = fake_home / "target"
    target.mkdir()
    link = fake_home / "link"
    link.symlink_to(target)
    assert paths.safe_removable(str(link)) == str(link)


def test_symlinked_live_parent_is_rejected(fake_home, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (fake_home / ".config").symlink_to(outside)
    assert paths.safe_destination(str(fake_home / ".config/app")) is None


def test_expand_targets_deduplicates_parents(fake_home):
    d = fake_home / "app/sub"
    d.mkdir(parents=True)
    assert paths.expand_targets([str(d), str(d.parent), str(d)]) == [str(d.parent)]


@pytest.mark.parametrize("value", ["", "relative"])
def test_invalid_xdg_values_fall_back(fake_home, monkeypatch, value):
    monkeypatch.setenv("XDG_STATE_HOME", value)
    assert paths.xdg_home("XDG_STATE_HOME", ".local/state") == str(fake_home / ".local/state")


@pytest.mark.parametrize("ns", [None, 3, "/", "/org/", "/org//x/", "/org/../x/",
    "/org/./x/", "/org/a b/", "/org/gnome/\n"])
def test_invalid_dconf_namespaces(ns):
    assert not dconf_manager.is_valid_namespace(ns)


def test_duplicate_members_and_link_parents_rejected():
    policy = MemberPolicy()
    link = tarfile.TarInfo("app/link")
    link.type, link.linkname = tarfile.SYMTYPE, "target"
    policy.check(link)
    with pytest.raises(BackupError):
        policy.check(link)
    with pytest.raises(BackupError):
        policy.check(tarfile.TarInfo("app/link/child"))


def test_member_limits_are_enforced():
    policy = MemberPolicy(ArchiveLimits(max_total_size=4, max_file_size=4))
    member = tarfile.TarInfo("app/file")
    member.size = 5
    with pytest.raises(BackupError):
        policy.check(member)


@pytest.mark.parametrize("value", [None, [], {"x": "oops"}, {"../x": "a" * 64}])
def test_invalid_checksums(value):
    with pytest.raises(BackupError):
        validate_checksums(value)


@pytest.mark.parametrize("app_id", [[], {}, 1, None])
def test_dconf_section_ids_require_strings(fake_home, app_id):
    data = manifest()
    data["dconf"] = [{"app_id": app_id, "items": []}]
    with pytest.raises(BackupError):
        normalise_manifest(data)

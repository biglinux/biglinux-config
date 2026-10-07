"""Release consistency: version, URLs, desktop integration and catalogs."""

from __future__ import annotations

import configparser
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from data.app_registry import APP_REGISTRY
from ui.metadata import APP_ICON, APP_VERSION, APP_WEBSITE

ROOT = Path(__file__).resolve().parents[1]
TREE = ROOT / "biglinux-config"
APP_ID = "com.biglinux.config"


def _pkgbuild(field: str) -> str:
    match = re.search(rf"^{field}=(.+)$", (ROOT / "pkgbuild/PKGBUILD").read_text(), re.M)
    assert match, field
    return match.group(1).strip("'\"")


def _metainfo():
    return ET.parse(TREE / f"usr/share/metainfo/{APP_ID}.metainfo.xml").getroot()


def test_one_version_everywhere():
    assert re.fullmatch(r"\d+\.\d+\.\d+", APP_VERSION)
    assert _pkgbuild("pkgver") == APP_VERSION
    assert _pkgbuild("pkgrel").isdigit()
    assert _metainfo().find("releases/release").get("version") == APP_VERSION


def test_one_project_url_everywhere():
    assert _pkgbuild("url") == APP_WEBSITE
    assert _metainfo().find("url[@type='homepage']").text == APP_WEBSITE
    assert APP_WEBSITE in (ROOT / "README.md").read_text()


def test_desktop_entries_match_the_application():
    for name in (f"{APP_ID}.desktop", "biglinux-config.desktop"):
        parser = configparser.ConfigParser(interpolation=None, strict=False)
        parser.optionxform = str
        parser.read(TREE / "usr/share/applications" / name, encoding="utf-8")
        entry = parser["Desktop Entry"]
        assert entry["Exec"].split()[0] == "biglinux-config"
        assert entry["Icon"] == APP_ICON
    assert entry.get("NoDisplay") == "true"  # the Control Center copy stays out of menus
    assert _metainfo().find("launchable").text == f"{APP_ID}.desktop"
    assert (TREE / f"usr/share/icons/hicolor/scalable/apps/{APP_ICON}.svg").is_file()


def test_launchers():
    launcher = TREE / "usr/bin/biglinux-config"
    assert os.access(launcher, os.X_OK)
    assert "/usr/share/biglinux/biglinux-config/main.py" in launcher.read_text()
    alias = TREE / "usr/bin/big-config"
    assert alias.is_symlink() and os.readlink(alias) == "biglinux-config"


def test_readme_states_the_real_application_count():
    counts = set(re.findall(r"apps-(\d+)-", (ROOT / "README.md").read_text()))
    assert counts == {str(len(APP_REGISTRY))}


@pytest.mark.skipif(not all(shutil.which(t) for t in ("xgettext", "msgmerge", "msgfmt", "msgunfmt")),
                    reason="GNU gettext tools are not installed")
def test_translations_are_current_and_valid():
    result = subprocess.run(["bash", "tools/i18n.sh", "--check"], cwd=ROOT,
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr

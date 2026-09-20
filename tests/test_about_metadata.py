"""Tests for the user-facing application metadata."""

from ui.about_dialog import (
    APP_AUTHORS,
    APP_ISSUE_URL,
    APP_SUPPORT_URL,
    APP_WEBSITE,
)
from ui.welcome_dialog import WELCOME_FEATURES


def test_about_links_use_the_project_repository():
    assert APP_WEBSITE == "https://github.com/ruscher/biglinux-config"
    assert APP_ISSUE_URL == f"{APP_WEBSITE}/issues"
    assert APP_SUPPORT_URL.startswith(APP_WEBSITE)


def test_required_authors_are_present():
    assert "Bruno Gonçalves <bigbruno@gmail.com>" in APP_AUTHORS
    assert "Rafael Ruscher <rruscher@gmail.com>" in APP_AUTHORS


def test_welcome_covers_the_core_workflows():
    icons = {icon for icon, _title, _description in WELCOME_FEATURES}
    assert len(WELCOME_FEATURES) == 8
    assert {
        "restore-default-symbolic",
        "document-save-symbolic",
        "document-open-symbolic",
        "folder-flatpak",
        "system-search-symbolic",
        "preferences-system-symbolic",
    } <= icons

"""Read the rebuilt catalogs through Python's GNU gettext-compatible loader."""
import gettext
from pathlib import Path


def test_brazilian_safety_messages_and_english_header():
    root = Path(__file__).resolve().parents[1] / "biglinux-config/usr/share/locale"
    pt = gettext.translation("biglinux-config", localedir=root, languages=["pt_BR"])
    assert pt.gettext("Operation failed") == "A operação falhou"
    assert pt.gettext("Cancelling…") == "Cancelando…"
    assert "%s" in pt.gettext("Could not load applications: %s")
    en = gettext.translation("biglinux-config", localedir=root, languages=["en"])
    assert "INTEGER" not in en.info().get("plural-forms", "")

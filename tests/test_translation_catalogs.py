"""Read the compiled catalogs through Python's GNU gettext loader."""
import gettext
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "biglinux-config/usr/share/locale"


def test_brazilian_messages_and_english_header():
    pt = gettext.translation("biglinux-config", localedir=ROOT, languages=["pt_BR"])
    assert pt.gettext("Operation failed") == "A operação falhou"
    assert pt.gettext("Cancelling…") == "Cancelando…"
    assert "%s" in pt.gettext("Could not load applications: %s")
    en = gettext.translation("biglinux-config", localedir=ROOT, languages=["en"])
    assert "INTEGER" not in en.info().get("plural-forms", "")


def test_named_placeholders_survive_translation():
    pt = gettext.translation("biglinux-config", localedir=ROOT, languages=["pt_BR"])
    text = pt.ngettext("%(count)d application exported (%(size)s)",
                       "%(count)d applications exported (%(size)s)", 2)
    assert text % {"count": 2, "size": "1 MB"} == "2 aplicativos exportados (1 MB)"
    body = pt.gettext("An error occurred while restoring settings for %(app)s:\n%(error)s")
    assert "Firefox" in body % {"app": "Firefox", "error": "x"}

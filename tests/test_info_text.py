"""Every ⓘ a template uses has words, and every set of words is used somewhere."""
import re
from pathlib import Path

import pytest

from app import info_text

TEMPLATES = Path(__file__).parent.parent / "app" / "templates"
USED = re.compile(r"info\('([a-z_]+)'\)")


def _used():
    found = {}
    for f in TEMPLATES.rglob("*.html"):
        for key in USED.findall(f.read_text()):
            found.setdefault(key, []).append(f.name)
    return found


def test_every_key_a_template_uses_exists():
    missing = {k: v for k, v in _used().items() if k not in info_text.INFO}
    assert not missing, f"templates use ⓘ keys with no text in app/info_text.py: {missing}"


def test_every_text_is_used_and_short():
    unused = set(info_text.INFO) - set(_used())
    assert not unused, f"info_text.py has texts no template uses: {sorted(unused)}"
    for key, (title, text) in info_text.INFO.items():
        assert title and text and len(text) <= 260, key


def test_every_tile_and_filter_label_has_an_info_button():
    for name in ("_calendar_panel.html", "_risk_profile.html"):
        src = (TEMPLATES / "partials" / name).read_text()
        tiles = re.findall(r'<div class="tile">.*', src)
        assert tiles and all("info(" in t for t in tiles), name
    filters = (TEMPLATES / "partials" / "_finder_filters.html").read_text()
    labels = re.findall(r'<div class="label">.*', filters)
    assert len(labels) == 4 and all("info(" in l for l in labels)


def test_the_button_carries_title_and_text_and_escapes_them():
    html = str(info_text.info("delta"))
    assert 'class="info-btn"' in html and 'data-info-title="Delta"' in html and "aria-label=\"About Delta\"" in html
    assert "<" not in html.split(">", 1)[1].rsplit("<", 1)[0].replace("ⓘ", "")      # no raw markup inside the button text
    with pytest.raises(KeyError):
        info_text.info("no_such_key")

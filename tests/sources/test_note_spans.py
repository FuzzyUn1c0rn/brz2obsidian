import pytest

from brz2obsidian.contracts import MigrationRefused
from brz2obsidian.sources.thebrain import trace_note_references


def test_reference_spans_use_exact_authored_text_and_protect_code():
    text = "Intro\r\n> - [one](brain://abc/title) and [one](brain://abc/title)\r\n\r\n`[one](brain://abc/title)`\r\n\\[literal](brain://abc/title)\r\n```md\r\n![code](.data/md-images/x.png)\r\n```\r\n![alt](.data/md-images/x.png)\r\n"
    spans = trace_note_references(text)
    assert [(span.kind, span.expected_original) for span in spans] == [
        ("item", "[one](brain://abc/title)"),
        ("item", "[one](brain://abc/title)"),
        ("image", "![alt](.data/md-images/x.png)"),
    ]
    assert [text[span.start : span.end] for span in spans] == [
        span.expected_original for span in spans
    ]
    assert spans[0].start == 11
    assert spans[1].start == 40
    assert spans[2].start == 171
    assert [span.display_text for span in spans] == ["one", "one", "alt"]


def test_active_html_local_reference_is_explicitly_unsupported():
    with pytest.raises(MigrationRefused) as error:
        trace_note_references('<img src=".data/md-images/x.png">')
    assert error.value.issues[0].code == "unsupported_feature"

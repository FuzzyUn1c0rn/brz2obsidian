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


@pytest.mark.parametrize(
    "text",
    [
        "prefix\u2028[local](brain://abc/title)",
        "- paragraph\n\t[local](brain://abc/title)",
        "> - nested\r\n>   [local](brain://abc/title)\r\n",
    ],
)
def test_normalization_and_block_indentation_retain_exact_original_offsets(text):
    spans = trace_note_references(text)
    assert len(spans) == 1
    assert spans[0].expected_original == "[local](brain://abc/title)"
    assert text[spans[0].start : spans[0].end] == "[local](brain://abc/title)"


@pytest.mark.parametrize(
    "text",
    [
        "[local][ref]\n\n[ref]: brain://abc/title",
        "![local][ref]\n\n[ref]: .data/md-images/x.png",
        "<brain://abc/title>",
        "[local](../other.md)",
        "![local](other.png)",
        '<a href="brain://abc/title">local</a>',
        "[![alt](.data/md-images/a.png)](brain://abc/title)",
    ],
)
def test_unsupported_active_local_syntax_is_a_typed_actionable_refusal(text):
    with pytest.raises(MigrationRefused) as error:
        trace_note_references(text)
    assert error.value.issues[0].code == "unsupported_feature"
    assert error.value.issues[0].guidance


def test_local_examples_in_comments_code_and_escaped_literals_remain_untouched():
    text = "<!-- example brain://abc/title -->\n\n`<brain://abc/title>`\n\\[literal](brain://abc/title)\n\n    <brain://abc/title>\n\n[external](https://example.invalid/a)\n"
    assert trace_note_references(text) == ()


@pytest.mark.parametrize(
    "prefix,kind,target",
    [("", "item", "brain://abc/title"), ("!", "image", ".data/md-images/x.png")],
)
def test_entity_and_escaped_label_characters_keep_exact_reference_spans(
    prefix, kind, target
):
    phrase = f"{prefix}[**A &amp; B** [literal \\*star\\*] `&amp;`]({target})"
    text = f"α\r\n{phrase}\rTail\n"
    spans = trace_note_references(text)
    assert len(spans) == 1
    span = spans[0]
    assert (span.kind, span.target) == (kind, target)
    assert span.display_text == "A & B [literal *star*] &amp;"
    assert span.expected_original == phrase
    assert span.start == 3
    assert span.end == 3 + len(phrase)
    assert text[span.start : span.end] == phrase

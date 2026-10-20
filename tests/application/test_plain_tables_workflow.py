"""Plain table output remains editable through the real BRZ conversion boundary."""

import hashlib
import json

import pytest
from markdown_it import MarkdownIt

from brz2obsidian.application.wiring import default_workflow
from tests.application.test_links_workflow import COMPACT, links_archive
from tests.support.local_api_payloads import PNG
from tests.support.notes import note_body


@pytest.mark.parametrize("style", ["", ':(table="unfamiliar:value"):'])
def test_brz_plain_tables_publish_every_data_cell_and_preserve_original_evidence(
    tmp_path,
    style,
):
    original = f"""![First](.data/md-images/photo.png)![Second](.data/md-images/photo.png)
||{style}
|1{{nl}}2|`first|second`{{nl}}[Topic](brain://{COMPACT}/title)|
Following prose.

|**Before**|Select before recording.|
|**After**|Select after recording.|
"""
    source = links_archive(
        tmp_path / "source.brz",
        original,
        resources=[({"Type": 12, "Location": "photo.png"}, PNG)],
    )
    before = source.read_bytes()
    destination = tmp_path / "vault"
    result = default_workflow().convert(source, destination)
    assert result.outcome == "clean", result.issues
    assert result.issues == ()
    body = note_body(
        (destination / "Home \u2014 Entry thought.md").read_text(encoding="utf-8")
    )
    assert (
        "![First](Attachments/22222222/photo.png)![Second](Attachments/22222222/photo.png)\n\n| | |\n|---|---|\n|1<br>2|<code>first&#124;second</code><br>[[Notes/Topic.v2.md\\|Topic]]|"
        in body
    )
    assert (
        "| | |\n|---|---|\n|**Before**|Select before recording.|\n|**After**|Select after recording.|"
        in body
    )
    tokens = MarkdownIt("commonmark").enable("table").parse(body)
    assert sum(t.type == "table_open" for t in tokens) == 2
    last_open = max(i for i, t in enumerate(tokens) if t.type == "table_open")
    last_close = max(i for i, t in enumerate(tokens) if t.type == "table_close")
    assert [t.content for t in tokens[last_open:last_close] if t.type == "inline"] == [
        "",
        "",
        "**Before**",
        "Select before recording.",
        "**After**",
        "Select after recording.",
    ]
    assert "[[Notes/Topic.v2.md\\|Topic]]|\n\nFollowing prose." in body
    assert result.counts.actual_references == 3
    assert (
        destination / "Attachments/22222222/Notes.md.original"
    ).read_bytes() == original.encode()
    assert (destination / "Attachments/22222222/photo.png").read_bytes() == PNG
    assert source.read_bytes() == before
    record = json.loads((destination / "migration-record.json").read_bytes())
    edits = [
        a["text_edit"] for a in record["adaptations"] if a["text_edit"] is not None
    ]
    assert edits and all(
        e["source_digest"] == hashlib.sha256(original.encode()).hexdigest()
        for e in edits
    )
    report = (destination / "Migration report.md").read_text(encoding="utf-8")
    assert "exact text adaptations for Markdown display" in report
    assert "migration-record.json" in report


def test_table_normalization_keeps_unresolved_and_unrelated_warnings(tmp_path):
    original = """|First|Meaning|:(table="unfamiliar:value"):
|one|Expected table.|

|Broken|Table|
|one|two|three|

![First](.data/md-images/photo.png#$width=50p$)
![Second](.data/md-images/photo.png#$width=25p$)

> [!tip|icon:😂] Advice
> Keep this icon fallback warning.
"""
    source = links_archive(
        tmp_path / "mixed.brz",
        original,
        resources=[({"Type": 12, "Location": "photo.png"}, PNG)],
    )
    before = source.read_bytes()
    destination = tmp_path / "vault"
    result = default_workflow().convert(source, destination)
    assert result.outcome == "warnings", result.model_dump_json()
    assert sorted(issue.code for issue in result.issues) == [
        "formatting_loss",
        "formatting_loss",
        "image_presentation_normalized",
        "image_presentation_normalized",
    ]
    features = sorted(
        json.loads(issue.message.split("Observed: ", 1)[1])["feature"]
        for issue in result.issues
        if issue.code == "formatting_loss"
    )
    assert features == ["callout_icon", "table"]
    malformed = next(
        issue
        for issue in result.issues
        if "Malformed or ambiguous table" in issue.message
    )
    assert (
        json.loads(malformed.message.split("Observed: ", 1)[1])["declaration"]
        == "|Broken|Table|"
    )
    assert {
        declaration
        for declaration in ("#$width=50p$", "#$width=25p$")
        if any(
            declaration in issue.message
            for issue in result.issues
            if issue.code == "image_presentation_normalized"
        )
    } == {"#$width=50p$", "#$width=25p$"}
    body = note_body(
        (destination / "Home — Entry thought.md").read_text(encoding="utf-8")
    )
    assert "| | |\n|---|---|\n|First|Meaning|\n|one|Expected table.|" in body
    assert "|Broken|Table|\n|one|two|three|" in body
    assert (
        destination / "Attachments/22222222/Notes.md.original"
    ).read_bytes() == original.encode()
    assert (destination / "Attachments/22222222/photo.png").read_bytes() == PNG
    assert source.read_bytes() == before
    record = json.loads((destination / "migration-record.json").read_bytes())
    assert any(
        change["text_edit"]
        and change["text_edit"]["source_digest"]
        == hashlib.sha256(original.encode()).hexdigest()
        for change in record["adaptations"]
    )
    assert "exact text adaptations for Markdown display" in (
        destination / "Migration report.md"
    ).read_text(encoding="utf-8")

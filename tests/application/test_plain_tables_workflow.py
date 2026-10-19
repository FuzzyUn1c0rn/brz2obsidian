"""Plain table output remains editable through the real BRZ conversion boundary."""

import hashlib
import json

from markdown_it import MarkdownIt

from brz2obsidian.application.wiring import default_workflow
from tests.application.test_links_workflow import COMPACT, links_archive
from tests.support.local_api_payloads import PNG
from tests.support.notes import note_body


def test_brz_plain_tables_publish_every_data_cell_and_preserve_original_evidence(
    tmp_path,
):
    original = f"""![First](.data/md-images/photo.png)![Second](.data/md-images/photo.png)
||
|1{{nl}}2|`first|second`{{nl}}[Topic](brain://{COMPACT}/title)|

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
    assert result.outcome == "warnings", result.issues
    body = note_body(
        (destination / "Home \u2014 Entry thought.md").read_text(encoding="utf-8")
    )
    assert (
        "![First](Attachments/22222222/photo.png)![Second](Attachments/22222222/photo.png)\n\n|||\n|---|---|\n|1<br>2|<code>first&#124;second</code><br>[[Notes/Topic.v2.md\\|Topic]]|"
        in body
    )
    assert (
        "|||\n|---|---|\n|**Before**|Select before recording.|\n|**After**|Select after recording.|"
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
    assert "blank native headings preserve every source row" in report
    assert "both data cells are preserved" in report

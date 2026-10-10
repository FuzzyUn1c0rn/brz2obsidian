"""Accepted insert behavior through synthetic actual-BRZ public workflows."""

import json

import pytest

from brz2obsidian.application.wiring import default_workflow
from tests.application.test_literal_angles_workflow import literal_archive
from tests.support.notes import note_body

SAMPLE = """### ToC
[/toc/]

### Callouts
> [!note]
> Note
> [!abstract]
> Abstract
> [!quote]
> Quote
> [!tip|icon:😂]
> Custom Icon

### Table
|Col1|Col2|Col3|Col4|:(table="column-widths:-1,0,0,0,174;justification:default"):
|1|2|3|A longer text|

### Mathematical Expression
$$c = \\sqrt{a^2+b^2}$$
"""


def test_sample_inserts_preserve_content_and_disclose_only_lossy_adaptations(tmp_path):
    source = literal_archive(tmp_path / "source.brz", SAMPLE.encode())
    before = source.read_bytes()
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    assert inspected.outcome == "warnings", inspected.model_dump_json()
    converted = workflow.convert(source, tmp_path / "vault")
    assert converted.outcome == "warnings", converted.model_dump_json()
    assert inspected.issues == converted.issues
    body = note_body(
        (tmp_path / "vault/Home — Entry thought.md").read_text(encoding="utf-8")
    )
    assert "|Col1|Col2|Col3|Col4|\n|---|---|---|---|\n|1|2|3|A longer text|" in body
    assert (
        "> [!note]\n> Note\n\n> [!abstract]\n> Abstract\n\n> [!quote]\n> Quote\n\n> [!tip] 😂 Tip\n> Custom Icon"
        in body
    )
    assert "$$c = \\sqrt{a^2+b^2}$$" in body
    assert "[/toc/]" not in body
    assert "column-widths" not in body
    assert {i.code for i in inspected.issues} == {"formatting_loss"}
    assert len(inspected.issues) == 2
    assert (
        tmp_path / "vault/Attachments/22222222/Notes.md.original"
    ).read_bytes() == SAMPLE.encode()
    assert source.read_bytes() == before


def test_toc_links_target_distinct_authored_headings_and_protect_examples(tmp_path):
    text = """### ToC
[/toc/]

# Repeated
First target.
## Café & punctuation?! [alpha]
Unicode target.
# Repeated
Second target.

### Other ToC
[/toc/]

```md
[/toc/]
# Example heading
```
`[/toc/]`
\\[/toc/]
<!-- [/toc/] -->
"""
    source = literal_archive(tmp_path / "source.brz", text.encode())
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "clean", result.model_dump_json()
    body = note_body(
        (tmp_path / "vault/Home — Entry thought.md").read_text(encoding="utf-8")
    )
    expected = "- [Repeated](#^brz-toc-heading-1)\n  - [Café & punctuation?! \\[alpha\\]](#^brz-toc-heading-2)\n- [Repeated](#^brz-toc-heading-3)"
    assert body.count(expected) == 2
    assert "# Repeated ^brz-toc-heading-1\nFirst target." in body
    assert "# Repeated ^brz-toc-heading-3\nSecond target." in body
    assert "|ToC]]" not in body and "|Other ToC]]" not in body
    assert "|Entry thought]]" not in body and "|Categories]]" not in body
    assert (
        "```md\n[/toc/]\n# Example heading\n```\n`[/toc/]`\n\\[/toc/]\n<!-- [/toc/] -->"
        in body
    )


def test_toc_image_headings_keep_visible_labels_targets_and_exact_payloads(tmp_path):
    text = """### Contents
[/toc/]

# ![Authored image heading](.data/md-images/a.png)
IMAGE HEADING TARGET

## Mixed ![authored image](.data/md-images/a.png) heading
MIXED TARGET

## ![Café *emphasis* `code` [square] & punctuation?!](.data/md-images/a.png)
FORMATTED TARGET

## ![](.data/md-images/a.png)
EMPTY ALT TARGET

# Ordinary heading
ORDINARY TARGET
"""
    image = b"exact authored image bytes"
    source = literal_archive(
        tmp_path / "source.brz",
        text.encode(),
        resources=[({"Type": 12, "Location": "a.png"}, image)],
    )
    before = source.read_bytes()
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    converted = workflow.convert(source, tmp_path / "vault")
    assert inspected.outcome == converted.outcome == "clean", (
        converted.model_dump_json()
    )
    body = note_body(
        (tmp_path / "vault/Home — Entry thought.md").read_text(encoding="utf-8")
    )
    assert (
        "- [Authored image heading](#^brz-toc-heading-1)\n"
        "  - [Mixed authored image heading](#^brz-toc-heading-2)\n"
        "  - [Café emphasis code \\[square\\] & punctuation?!](#^brz-toc-heading-3)\n"
        "  - [Image](#^brz-toc-heading-4)\n"
        "- [Ordinary heading](#^brz-toc-heading-5)" in body
    )
    assert "- [](" not in body
    for index, marker in enumerate(
        ["IMAGE HEADING", "MIXED", "FORMATTED", "EMPTY ALT", "ORDINARY"], 1
    ):
        assert f" ^brz-toc-heading-{index}\n{marker} TARGET" in body
    assert "![Authored image heading](Attachments/22222222/a.png)" in body
    assert inspected.counts.source_references == converted.counts.actual_references == 4
    assert (tmp_path / "vault/Attachments/22222222/a.png").read_bytes() == image
    assert (
        tmp_path / "vault/Attachments/22222222/Notes.md.original"
    ).read_bytes() == text.encode()
    assert source.read_bytes() == before


def test_toc_carets_in_displayed_labels_are_distinct_from_authored_block_ids(tmp_path):
    text = """### Contents
[/toc/]

# ![Authored ^literal](.data/md-images/a.png)
IMAGE CARET TARGET

# `Code ^literal`
CODE CARET TARGET

# Mixed ![Image ^literal](.data/md-images/a.png) `Code ^literal` ^authored-mixed
MIXED ID TARGET

# Ordinary title ^authored-ordinary
ORDINARY ID TARGET
"""
    image = b"exact caret-heading image bytes"
    source = literal_archive(
        tmp_path / "source.brz",
        text.encode(),
        resources=[({"Type": 12, "Location": "a.png"}, image)],
    )
    before = source.read_bytes()
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    converted = workflow.convert(source, tmp_path / "vault")
    assert inspected.outcome == converted.outcome == "clean", (
        converted.model_dump_json()
    )
    body = note_body(
        (tmp_path / "vault/Home — Entry thought.md").read_text(encoding="utf-8")
    )
    assert (
        "- [Authored ^literal](#^brz-toc-heading-1)\n"
        "- [Code ^literal](#^brz-toc-heading-2)\n"
        "- [Mixed Image ^literal Code ^literal](#^authored-mixed)\n"
        "- [Ordinary title](#^authored-ordinary)" in body
    )
    assert (
        "![Authored ^literal](Attachments/22222222/a.png) ^brz-toc-heading-1\nIMAGE CARET TARGET"
        in body
    )
    assert "# `Code ^literal` ^brz-toc-heading-2\nCODE CARET TARGET" in body
    assert "`Code ^literal` ^authored-mixed\nMIXED ID TARGET" in body
    assert "# Ordinary title ^authored-ordinary\nORDINARY ID TARGET" in body
    assert inspected.counts.source_references == converted.counts.actual_references == 2
    assert (tmp_path / "vault/Attachments/22222222/a.png").read_bytes() == image
    assert (
        tmp_path / "vault/Attachments/22222222/Notes.md.original"
    ).read_bytes() == text.encode()
    assert source.read_bytes() == before


def test_toc_empty_labels_and_literal_caret_suffixes_keep_usable_destinations(tmp_path):
    text = """### Contents
[/toc/]

#
EMPTY TARGET

# ` `
WHITESPACE TARGET

# [](https://example.invalid)
EMPTY LINK TARGET

# ^metadata-only
METADATA TARGET

# Escaped \\^literal
ESCAPED TARGET

# Closed ^literal ###
CLOSED TARGET

Multi
line ^keep-multiline
===
MULTILINE ID TARGET
"""
    source = literal_archive(tmp_path / "source.brz", text.encode())
    before = source.read_bytes()
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "clean", result.model_dump_json()
    body = note_body(
        (tmp_path / "vault/Home — Entry thought.md").read_text(encoding="utf-8")
    )
    assert (
        "- [Heading](#^brz-toc-heading-1)\n"
        "- [Heading](#^brz-toc-heading-2)\n"
        "- [Heading](#^brz-toc-heading-3)\n"
        "- [Heading](#^metadata-only)\n"
        "- [Escaped ^literal](#^brz-toc-heading-5)\n"
        "- [Closed ^literal](#^brz-toc-heading-6)\n"
        "- [Multi line](#^keep-multiline)" in body
    )
    assert "- [](" not in body
    assert "# ^metadata-only\nMETADATA TARGET" in body
    assert "# Escaped \\^literal ^brz-toc-heading-5\nESCAPED TARGET" in body
    assert "# Closed ^literal ^brz-toc-heading-6\nCLOSED TARGET" in body
    assert "# Multi line ^keep-multiline\nMULTILINE ID TARGET" in body
    assert (
        tmp_path / "vault/Attachments/22222222/Notes.md.original"
    ).read_bytes() == text.encode()
    assert source.read_bytes() == before


def test_toc_duplicate_authored_ids_and_body_collisions_get_distinct_targets(tmp_path):
    text = """### Contents
[/toc/]

# First ^duplicate
FIRST TARGET

# Second ^duplicate
SECOND TARGET

Body anchor ^body-collision

# Third ^body-collision
THIRD TARGET

# Unique ^unique
UNIQUE TARGET

# Fifth ^body-after
FIFTH TARGET

Later body anchor ^body-after

See [First authored link](#^duplicate) and [Body authored link](#^body-collision).

Reserved generated identifier ^brz-toc-heading-2
"""
    source = literal_archive(tmp_path / "source.brz", text.encode())
    before = source.read_bytes()
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    converted = workflow.convert(source, tmp_path / "vault")
    assert inspected.outcome == converted.outcome == "warnings", (
        converted.model_dump_json()
    )
    assert inspected.issues == converted.issues
    assert len(converted.issues) == 3
    assert {i.code for i in converted.issues} == {"formatting_loss"}
    assert all(
        "block ID" in i.message and "distinct" in i.message for i in converted.issues
    )
    body = note_body(
        (tmp_path / "vault/Home — Entry thought.md").read_text(encoding="utf-8")
    )
    assert (
        "- [First](#^duplicate)\n"
        "- [Second](#^brz-toc-heading-2-generated)\n"
        "- [Third](#^brz-toc-heading-3)\n"
        "- [Unique](#^unique)\n"
        "- [Fifth](#^brz-toc-heading-5)" in body
    )
    assert "# First ^duplicate\nFIRST TARGET" in body
    assert "# Second ^brz-toc-heading-2-generated\nSECOND TARGET" in body
    assert "Body anchor ^body-collision" in body
    assert "# Third ^brz-toc-heading-3\nTHIRD TARGET" in body
    assert "# Unique ^unique\nUNIQUE TARGET" in body
    assert "# Fifth ^brz-toc-heading-5\nFIFTH TARGET" in body
    assert "Later body anchor ^body-after" in body
    assert (
        "See [First authored link](#^duplicate) and [Body authored link](#^body-collision)."
        in body
    )
    assert (
        tmp_path / "vault/Attachments/22222222/Notes.md.original"
    ).read_bytes() == text.encode()
    assert source.read_bytes() == before


def test_all_native_types_preserve_titles_folds_nesting_and_literal_controls(tmp_path):
    gallery = "\n".join(
        f"> [!{kind}]\n> {kind} body"
        for kind in [
            "note",
            "abstract",
            "info",
            "todo",
            "tip",
            "success",
            "question",
            "warning",
            "failure",
            "danger",
            "bug",
            "example",
            "quote",
        ]
    )
    controls = """

> [!note]+ Authored title
> Parent body
> > [!tip]- Child title
> > Child body
> > [!question] Another child
> > Other body
> Parent tail
> [!tip|icon:😂]- Authored custom title
> Custom body

> [!note] Already separate
> Kept body

> [!tip] Also separate
> Kept tip

> `[!warning]` code
> \\[!bug] escaped
> [bracket-like prose]
> ```md
> [!danger]
> ```
"""
    source = literal_archive(tmp_path / "source.brz", (gallery + controls).encode())
    inspected = default_workflow().inspect(source)
    assert len(inspected.issues) == 1
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "warnings", result.model_dump_json()
    body = note_body(
        (tmp_path / "vault/Home — Entry thought.md").read_text(encoding="utf-8")
    )
    for kind in [
        "note",
        "abstract",
        "info",
        "todo",
        "tip",
        "success",
        "question",
        "warning",
        "failure",
        "danger",
        "bug",
        "example",
        "quote",
    ]:
        assert f"> [!{kind}]\n> {kind} body" in body
    assert gallery.replace("\n> [!", "\n\n> [!") in body
    assert (
        "> [!note]+ Authored title\n> Parent body\n> > [!tip]- Child title\n> > Child body\n> \n> > [!question] Another child\n> > Other body\n> \n> Parent tail\n\n> [!tip]- 😂 Authored custom title\n> Custom body"
        in body
    )
    assert controls.split("> [!note] Already separate", 1)[1] in body
    assert not list((tmp_path / "vault").rglob("*.css"))
    assert not list((tmp_path / "vault").rglob("*.svg"))


@pytest.mark.parametrize(
    "declaration",
    [
        ':(table="column-widths:1,2;justification:default"):',
        ':(table="column-widths:--,0,0;justification:default"):',
        ':(table="unknown"):',
    ],
)
def test_ambiguous_tables_retain_source_and_actionable_loss_warning(
    tmp_path, declaration
):
    text = f"|One|Two|{declaration}\n|1|2|\n"
    source = literal_archive(tmp_path / "source.brz", text.encode())
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "warnings", result.model_dump_json()
    assert len(result.issues) == 1
    assert (
        json.loads(result.issues[0].message.split("Observed: ", 1)[1])["declaration"]
        == declaration
    )
    assert "matching header separator" in result.issues[0].message
    assert text in note_body(
        (tmp_path / "vault/Home — Entry thought.md").read_text(encoding="utf-8")
    )


def test_table_cells_keep_escapes_code_formatting_and_existing_valid_tables(tmp_path):
    text = """|**One**|Two|:(table="column-widths:-1,0,84;justification:default"):
|a\\|b|`x|y`|

|Valid|Table|
|:---|---:|
|*authored*|keep|
"""
    source = literal_archive(tmp_path / "source.brz", text.encode())
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "warnings", result.model_dump_json()
    body = note_body(
        (tmp_path / "vault/Home — Entry thought.md").read_text(encoding="utf-8")
    )
    assert "|**One**|Two|\n|---|---|\n|a\\|b|<code>x&#124;y</code>|" in body
    assert text.split("\n\n", 1)[1] in body
    record = json.loads(
        (tmp_path / "vault/migration-record.json").read_text(encoding="utf-8")
    )
    assert "column-widths:-1,0,84;justification:default" in json.dumps(record)


def test_inserts_compose_with_thought_image_and_literal_text_adaptations(tmp_path):
    from tests.application.test_links_workflow import COMPACT, links_archive

    body = f"""### ToC
[/toc/]

### Table <Value>
|Thought|Image|:(table="column-widths:-1,0,174;justification:default"):
|[Topic](brain://{COMPACT}/title)|![Alt](.data/md-images/photo.png#$width=50p$)|

> [!note]
> [Topic](brain://{COMPACT}/title)
> [!tip|icon:😂]
> Press <Enter>.
"""
    source = links_archive(
        tmp_path / "source.brz",
        body,
        resources=[({"Type": 12, "Location": "photo.png"}, b"asset bytes")],
    )
    inspected = default_workflow().inspect(source)
    assert inspected.outcome == "warnings", inspected.model_dump_json()
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "warnings", result.model_dump_json()
    actual = note_body(
        (tmp_path / "vault/Home — Entry thought.md").read_text(encoding="utf-8")
    )
    assert (
        "|[[Notes/Topic.v2.md\\|Topic]]|![Alt](Attachments/22222222/photo.png)|"
        in actual
    )
    assert (
        "> [!note]\n> [[Notes/Topic.v2.md|Topic]]\n\n> [!tip] 😂 Tip\n> Press \\<Enter>."
        in actual
    )
    assert "### Table \\<Value> ^brz-toc-heading-1" in actual
    assert (
        tmp_path / "vault/Attachments/22222222/photo.png"
    ).read_bytes() == b"asset bytes"
    assert (
        tmp_path / "vault/Attachments/22222222/Notes.md.original"
    ).read_bytes() == body.encode()
    assert inspected.counts.source_references == result.counts.actual_references == 3


def test_escaped_and_code_table_metadata_and_unsupported_icon_controls(tmp_path):
    literal = r"""|One|Two|\:(table="column-widths:-1,0,84;justification:default"):
|1|2|

|One|Two|`:(table="column-widths:-1,0,84;justification:default"):`
|3|4|

```md
> [!tip|icon:😂]
|One|Two|:(table="unknown"):
```
"""
    active = "> [!tip|icon:unknown]- Authored title\n> Body\n> [!note|icon:😂|extra:x]\n> Second body\n"
    source = literal_archive(tmp_path / "source.brz", (literal + active).encode())
    inspected = default_workflow().inspect(source)
    assert inspected.outcome == "warnings", inspected.model_dump_json()
    assert len(inspected.issues) == 2
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "warnings", result.model_dump_json()
    body = note_body(
        (tmp_path / "vault/Home — Entry thought.md").read_text(encoding="utf-8")
    )
    assert literal in body
    assert "> [!tip]- Authored title — |icon:unknown\n> Body" in body
    assert "> [!note] Note — |icon:😂|extra:x\n> Second body" in body


def test_toc_setext_headings_closing_hashes_and_existing_block_ids(tmp_path):
    text = """Contents
--------
[/toc/]

### Closed hashes ###
Body.

Multi
line heading
============
Text.

## Existing ^keep-anchor
Retained target.

Literal ID collision ^brz-toc-heading-1
"""
    source = literal_archive(tmp_path / "source.brz", text.encode())
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "clean", result.model_dump_json()
    body = note_body(
        (tmp_path / "vault/Home — Entry thought.md").read_text(encoding="utf-8")
    )
    assert "### Closed hashes ^brz-toc-heading-1-generated\n" in body
    assert "# Multi line heading ^brz-toc-heading-2\n" in body
    assert "[Multi line heading](#^brz-toc-heading-2)" in body
    assert "[Existing](#^keep-anchor)" in body
    assert "## Existing ^keep-anchor" in body
    assert "|Contents]]" not in body


def test_insert_warnings_surface_in_cli_and_reviewed_ui_authorization(tmp_path, capsys):
    from brz2obsidian.application.operations import Operations
    from brz2obsidian.cli import main

    source = literal_archive(tmp_path / "source.brz", SAMPLE.encode())
    assert main(["inspect", str(source), "--json"]) == 2
    envelope = json.loads(capsys.readouterr().out)
    assert len(envelope["issues"]) == 2
    assert {a["kind"] for a in envelope["inspection"]["adaptations"]} >= {
        "markdown_insert"
    }
    assert main(["inspect", str(source)]) == 2
    text = capsys.readouterr().out
    assert (
        "formatting_loss" in text and "callout_icon" in text and "column-widths" in text
    )
    assert "Text adaptations:" in text
    operation = Operations()
    inspected = operation.inspect(source)
    assert inspected.reviewed.outcome == "warnings"
    assert {f.code for f in inspected.findings} == {"formatting_loss"}
    assert all("Migration report" in f.message for f in inspected.findings)
    blocked = operation.convert_reviewed(
        source, tmp_path, "UI vault", inspected.reviewed
    )
    assert blocked.outcome == "refused"
    assert not (tmp_path / "UI vault").exists()
    converted = operation.convert_reviewed(
        source, tmp_path, "UI vault", inspected.reviewed, proceed_with_warnings=True
    )
    assert converted.outcome == "warnings"
    assert {f.code for f in converted.findings} == {"formatting_loss"}
    report = (tmp_path / "UI vault/MIGRATION REPORT.md").read_text(encoding="utf-8")
    assert "[[Home — Entry thought.md|Entry thought]]" in report
    assert "static" in report and "native icon remains" in report
    assert main(["convert", str(source), str(tmp_path / "CLI vault"), "--json"]) == 2
    converted_envelope = json.loads(capsys.readouterr().out)
    assert converted_envelope["issues"] == envelope["issues"]
    assert converted_envelope["receipt"]["verified"] is True


def test_insert_scope_determinism_and_destination_protection(tmp_path):
    from brz2obsidian.contracts import RunMetadata
    from tests.application.test_forgotten_workflow import forget, rewrite
    from tests.application.test_graph_workflow import graph_archive

    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", 2: "Private note"},
        notes={
            1: (b"### Contents\n[/toc/]\n\n# Kept\nBody.\n", 4),
            2: (b"> [!tip|icon:PRIVATE]\n> Secret body\n", 4),
        },
    )
    rewrite(source, lambda parts: forget(parts, 2))
    before = source.read_bytes()
    workflow = default_workflow()
    metadata = RunMetadata(
        converter_version="0.3.0",
        renderer_version="7",
        run_id="synthetic-inserts",
        run_time="2026-10-10T00:00:00+00:00",
        obsidian_version="1.14.4",
        bookmark_time=1,
    )
    workflow.metadata_factory = lambda: metadata
    inspected = workflow.inspect(source)
    assert inspected.outcome == "clean", inspected.model_dump_json()
    assert "PRIVATE" not in inspected.model_dump_json()
    inventories = []
    for name in ("one", "two"):
        destination = tmp_path / name
        result = workflow.convert(source, destination)
        assert result.outcome == "clean", result.model_dump_json()
        inventory = {
            p.relative_to(destination).as_posix(): p.read_bytes()
            for p in destination.rglob("*")
            if p.is_file()
        }
        assert not any(
            b"Private note" in data or b"Secret body" in data or b"PRIVATE" in data
            for data in inventory.values()
        )
        inventories.append(inventory)
    assert inventories[0] == inventories[1]
    refused = workflow.convert(source, tmp_path / "one")
    assert (
        refused.outcome == "refused"
        and refused.issues[0].code == "destination_not_empty"
    )
    assert {
        p.relative_to(tmp_path / "one").as_posix(): p.read_bytes()
        for p in (tmp_path / "one").rglob("*")
        if p.is_file()
    } == inventories[0]
    assert source.read_bytes() == before


def test_generated_code_cells_escape_markup_without_admitting_authored_html(tmp_path):
    text = '|Code|Other|:(table="column-widths:-1,0,84;justification:default"):\n|`<a>brain://literal|& text</a>`|value|\n'
    source = literal_archive(tmp_path / "source.brz", text.encode())
    inspected = default_workflow().inspect(source)
    assert inspected.outcome == "warnings", inspected.model_dump_json()
    assert inspected.counts.source_references == 0
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "warnings", result.model_dump_json()
    body = note_body(
        (tmp_path / "vault/Home — Entry thought.md").read_text(encoding="utf-8")
    )
    assert "<code>&lt;a&gt;brain://literal&#124;&amp; text&lt;/a&gt;</code>" in body
    unsafe = literal_archive(
        tmp_path / "unsafe.brz",
        b"|Code|Other|\n|---|---|\n|<code>authored</code>|value|\n",
    )
    refusal = default_workflow().convert(unsafe, tmp_path / "unsafe-vault")
    assert (
        refusal.outcome == "refused" and refusal.issues[0].code == "unsupported_feature"
    )
    assert not (tmp_path / "unsafe-vault").exists()


def test_standalone_toc_in_quote_keeps_container_and_literal_examples(tmp_path):
    text = "> ### Contents\n> [/toc/]\n\n> ## Quoted target\n> Body\n\n> `[/toc/]`\n> \\[/toc/]\n"
    source = literal_archive(tmp_path / "source.brz", text.encode())
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "clean", result.model_dump_json()
    body = note_body(
        (tmp_path / "vault/Home — Entry thought.md").read_text(encoding="utf-8")
    )
    assert "> - [Quoted target](#^brz-toc-heading-1)" in body
    assert "> ## Quoted target ^brz-toc-heading-1\n> Body" in body
    assert "> `[/toc/]`\n> \\[/toc/]" in body

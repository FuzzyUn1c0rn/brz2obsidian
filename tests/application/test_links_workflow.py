import json
from zipfile import ZipFile

import pytest

from brz2obsidian.application.wiring import default_workflow
from tests.application.test_resources_workflow import HOME, resource_archive, thought
from tests.support.notes import note_body

TARGET = "01234567-89ab-4cde-8f01-23456789abcd"
COMPACT = "Z0UjAauJ3kyPASNFZ4mrzQ"


def links_archive(path, body, *, resources=(), others=(), other_notes=()):
    resource_archive(path, resources, thoughts=(thought(TARGET, "Topic.v2"), *others))
    with ZipFile(path) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    files[HOME + "/Notes.md"] = body.encode("utf-8")
    records = [json.loads(line) for line in files["attachments.json"].splitlines()]
    records[0]["DataLength"] = len(files[HOME + "/Notes.md"])
    meta = json.loads(files["meta.json"])
    for owner, text in other_notes:
        key = "bbbbbbbb-0000-4000-8000-000000000001"
        data = text.encode("utf-8")
        records.append(
            {
                "Id": key,
                "BrainId": meta["BrainId"],
                "SourceId": owner,
                "SourceType": 2,
                "Type": 1,
                "NoteType": 4,
                "Location": "Notes.md",
                "DataLength": len(data),
            }
        )
        meta["AttachmentFileStates"][key] = 1
        files[owner + "/Notes.md"] = data
    files["meta.json"] = json.dumps(meta).encode()
    files["attachments.json"] = "\n".join(json.dumps(r) for r in records).encode()
    with ZipFile(path, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return path


def test_local_thought_and_image_links_convert_without_inventing_related_edges(
    tmp_path,
):
    body = f"Before\r\n[Topic](brain://{COMPACT}/informational-title)\r\n![photo](.data/md-images/photo.png)\r\nAfter\r"
    source = links_archive(
        tmp_path / "source.brz",
        body,
        resources=[({"Type": 12, "Location": "photo.png"}, b"image bytes")],
    )
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    assert inspected.outcome == "clean"
    vault = tmp_path / "vault"
    converted = workflow.convert(source, vault)
    assert converted.outcome == "clean"
    assert note_body((vault / "Home — Entry thought.md").read_bytes()) == (
        b"# Entry thought\n\nBefore\r\n[[Notes/Topic.v2.md|Topic]]\r\n"
        b"![photo](Attachments/22222222/photo.png)\r\nAfter\r\n"
        b"## Categories\n\n[[Categories.md|Browse categories]]\n"
    )
    assert not (vault / "Notes/Topic.v2.md").exists()
    assert (
        vault / "Attachments/22222222/Notes.md.original"
    ).read_bytes() == body.encode()
    assert (vault / "Attachments/22222222/photo.png").read_bytes() == b"image bytes"
    record = json.loads((vault / "migration-record.json").read_bytes())
    assert record["relationships"] == []
    assert (
        inspected.counts.source_references == inspected.counts.planned_references == 2
    )
    assert inspected.counts.actual_references is None
    assert converted.counts.actual_references == 2
    assert record["counts"]["actual_references"] == 2
    home_record = next(t for t in record["item_targets"] if t["item_key"] == HOME)
    references = home_record["documents"][0]["references"]
    assert [(r["kind"], r["target"]) for r in references] == [
        ("item", TARGET),
        ("image", "aaaaaaaa-0000-4000-8000-000000000001"),
    ]
    assert references[0]["display_text"] == "Topic"
    assert (
        references[0]["expected_original"]
        == f"[Topic](brain://{COMPACT}/informational-title)"
    )
    assert [
        a["kind"] for a in record["adaptations"] if a["kind"].endswith("reference")
    ] == ["item_reference", "image_reference"]
    assert (
        len(
            [
                e
                for e in record["source_accounting"]["entries"]
                if e["identity"].startswith("reference:")
            ]
        )
        == 2
    )


def test_image_paths_are_relative_encoded_and_preserve_alt_title_and_external_text(
    tmp_path,
):
    body = '![.data/md-images/A%20photo%20(%C3%A9).png](<.data/md-images/A photo (é).png> "Caption")\r\n![remote](https://example.invalid/x.png)\r'
    source = links_archive(
        tmp_path / "source.brz",
        body,
        resources=[
            ({"Type": 12, "Location": "A photo (é).png"}, b"first"),
            (
                {"SourceId": TARGET, "Type": 12, "Location": "A photo (é).png"},
                b"second",
            ),
            ({"Type": 12, "Location": "extra.png"}, b"additional"),
        ],
        other_notes=[(TARGET, body)],
    )
    vault = tmp_path / "vault"
    converted = default_workflow().convert(source, vault)
    assert converted.outcome == "clean"
    expected_alt = ".data/md-images/A%20photo%20(%C3%A9).png"
    home = (vault / "Home — Entry thought.md").read_bytes().decode()
    note = (vault / "Notes/Topic.v2.md").read_bytes().decode()
    assert note_body(home).startswith(
        f'# Entry thought\n\n![{expected_alt}](Attachments/22222222/A%20photo%20%28%C3%A9%29.png "Caption")\r\n![remote](https://example.invalid/x.png)\r'
    )
    assert (
        note_body(note)
        == f'# Topic.v2\n\n![{expected_alt}](../Attachments/01234567/A%20photo%20%28%C3%A9%29.png "Caption")\r\n![remote](https://example.invalid/x.png)\r'
    )
    assert "[[Attachments/22222222/extra.png|extra.png]]" in home
    assert "[[Attachments/22222222/A photo (é).png" not in home


def test_complete_workflow_span_gate_preserves_all_nonadapted_text_and_newlines(
    tmp_path,
):
    local = f"brain://{COMPACT}/information"
    body = (
        f"prefix\u2028[one]({local})\r\n"
        f"> - [two **bold**]({local}) and [escaped \\] end]({local})\r"
        f"- paragraph\n\t[one]({local})\n\n"
        f"`[one]({local})`\r\n\\[literal]({local})\r\n"
        f"```md\r\n[one]({local})\r\n```\r\n"
        f"<!-- example {local} -->\r\n"
        "[external](https://example.invalid/path)\r\n"
    )
    source = links_archive(tmp_path / "source.brz", body)
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "clean"
    assert note_body((vault / "Home — Entry thought.md").read_bytes().decode()) == (
        "# Entry thought\n\nprefix\u2028[[Notes/Topic.v2.md|one]]\r\n"
        "> - [[Notes/Topic.v2.md|two bold]] and [[Notes/Topic.v2.md|escaped end]]\r"
        "- paragraph\n\t[[Notes/Topic.v2.md|one]]\n\n"
        f"`[one]({local})`\r\n\\[literal]({local})\r\n"
        f"```md\r\n[one]({local})\r\n```\r\n"
        f"<!-- example {local} -->\r\n"
        "[external](https://example.invalid/path)\r\n\n"
        "## Categories\n\n[[Categories.md|Browse categories]]\n"
    )
    assert result.counts.actual_references == 4


@pytest.mark.parametrize(
    "label,display,alias",
    [
        ("A &amp; B", "A & B", "A & B"),
        (r"literal \*star\*", "literal *star*", "literal *star*"),
        (
            "**bold** *emphasis* `&amp;` plain",
            "bold emphasis &amp; plain",
            "bold emphasis &amp; plain",
        ),
        (
            r"[nested &amp; \*star\*] **bold**",
            "[nested & *star*] bold",
            "nested & *star* bold",
        ),
        ("caf&#233; &#x2603; &quot;yes&quot;", 'café ☃ "yes"', 'café ☃ "yes"'),
        (r"pipe \| \[x\]", "pipe | [x]", "pipe x"),
        ("first\r\nsecond", "first\nsecond", "first second"),
    ],
)
def test_included_entity_label_preserves_display_and_exact_source_record(
    tmp_path, label, display, alias
):
    phrase = f"[{label}](brain://{COMPACT}/title)"
    body = f"Before\r\n{phrase}\rAfter\n"
    source = links_archive(tmp_path / "source.brz", body)
    source_bytes = source.read_bytes()
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    vault = tmp_path / "vault"
    result = workflow.convert(source, vault)
    assert inspected.outcome == result.outcome == "clean"
    assert (
        note_body((vault / "Home — Entry thought.md").read_bytes())
        == (
            f"# Entry thought\n\nBefore\r\n[[Notes/Topic.v2.md|{alias}]]\rAfter\n\n"
            "## Categories\n\n[[Categories.md|Browse categories]]\n"
        ).encode()
    )
    assert (
        vault / "Attachments/22222222/Notes.md.original"
    ).read_bytes() == body.encode()
    record = json.loads((vault / "migration-record.json").read_bytes())
    home = next(t for t in record["item_targets"] if t["item_key"] == HOME)
    reference = home["documents"][0]["references"][0]
    assert reference["display_text"] == display
    assert reference["target"] == TARGET
    assert reference["source_target"] == f"brain://{COMPACT}/title"
    assert reference["expected_original"] == phrase
    assert body[reference["start"] : reference["end"]] == phrase
    assert (
        inspected.counts.source_references == inspected.counts.planned_references == 1
    )
    assert result.counts.actual_references == record["counts"]["actual_references"] == 1
    assert source.read_bytes() == source_bytes


def test_image_entity_and_escape_labels_preserve_authored_alt_and_record_display(
    tmp_path,
):
    phrase = r'![A &amp; B \*star\* [nested]](.data/md-images/photo.png "Caption")'
    body = f"α\r\n{phrase}\rTail\n"
    source = links_archive(
        tmp_path / "source.brz",
        body,
        resources=[({"Type": 12, "Location": "photo.png"}, b"image bytes")],
    )
    source_bytes = source.read_bytes()
    vault = tmp_path / "vault"
    workflow = default_workflow()
    inspection = workflow.inspect(source)
    result = workflow.convert(source, vault)
    assert inspection.outcome == result.outcome == "clean"
    assert (
        note_body((vault / "Home — Entry thought.md").read_bytes())
        == (
            '# Entry thought\n\nα\r\n![A &amp; B \\*star\\* [nested]](Attachments/22222222/photo.png "Caption")\rTail\n\n'
            "## Categories\n\n[[Categories.md|Browse categories]]\n"
        ).encode()
    )
    assert (
        vault / "Attachments/22222222/Notes.md.original"
    ).read_bytes() == body.encode()
    assert (vault / "Attachments/22222222/photo.png").read_bytes() == b"image bytes"
    record = json.loads((vault / "migration-record.json").read_bytes())
    home = next(t for t in record["item_targets"] if t["item_key"] == HOME)
    reference = home["documents"][0]["references"][0]
    assert reference["kind"] == "image"
    assert reference["target"] == "aaaaaaaa-0000-4000-8000-000000000001"
    assert reference["source_target"] == ".data/md-images/photo.png"
    assert reference["display_text"] == "A & B *star* [nested]"
    assert reference["expected_original"] == phrase
    assert body[reference["start"] : reference["end"]] == phrase
    assert (
        inspection.counts.source_references == inspection.counts.planned_references == 1
    )
    assert result.counts.actual_references == record["counts"]["actual_references"] == 1
    assert source.read_bytes() == source_bytes


def test_included_labels_survive_whole_forgotten_phrase_removal(tmp_path):
    private = thought("00000000-0000-0000-0000-000000000000", "Private subject")
    private["ForgottenDateTime"] = "2026-10-01T12:00:00Z"
    body = (
        f"α\r\n[A &amp; B \\*star\\*](brain://{COMPACT}/title)\r"
        "[Private &amp; \\*secret\\*](brain://AAAAAAAAAAAAAAAAAAAAAA/private) after\n"
    )
    source = links_archive(tmp_path / "source.brz", body, others=[private])
    source_bytes = source.read_bytes()
    vault = tmp_path / "vault"
    workflow = default_workflow()
    inspection = workflow.inspect(source)
    result = workflow.convert(source, vault)
    assert inspection.outcome == result.outcome == "clean"
    assert (
        note_body((vault / "Home — Entry thought.md").read_bytes())
        == (
            "# Entry thought\n\nα\r\n[[Notes/Topic.v2.md|A & B *star*]]\r after\n\n"
            "## Categories\n\n[[Categories.md|Browse categories]]\n"
        ).encode()
    )
    assert not any(p.name.endswith(".original") for p in vault.rglob("*"))
    output = b"\n".join(p.read_bytes() for p in vault.rglob("*") if p.is_file())
    for secret in (
        b"Private",
        b"secret",
        b"AAAAAAAAAAAAAAAAAAAAAA",
        private["Id"].encode(),
    ):
        assert secret not in output
        assert secret.decode() not in inspection.model_dump_json()
    record = json.loads((vault / "migration-record.json").read_bytes())
    home = next(t for t in record["item_targets"] if t["item_key"] == HOME)
    assert len(home["documents"][0]["references"]) == 1
    assert home["documents"][0]["references"][0]["display_text"] == "A & B *star*"
    assert (
        inspection.counts.source_references == inspection.counts.planned_references == 1
    )
    assert result.counts.actual_references == record["counts"]["actual_references"] == 1
    assert source.read_bytes() == source_bytes


@pytest.mark.parametrize(
    "syntax,code",
    [
        ("[x](brain://invalid/title)", "invalid_reference"),
        ("[x](brain://AAAAAAAAAAAAAAAAAAAAAA/title)", "invalid_reference"),
        ("[x](brain://api.thebrain.com/brain/thought)", "unsupported_feature"),
        ("![missing](.data/md-images/missing.png)", "invalid_reference"),
        ("![unsafe](.data/md-images/../image.png)", "invalid_reference"),
        (f"[x][ref]\n\n[ref]: brain://{COMPACT}/title", "unsupported_feature"),
        (f"<brain://{COMPACT}/title>", "unsupported_feature"),
        (f'<a href="brain://{COMPACT}/title">x</a>', "unsupported_feature"),
        (
            f"[![x](.data/md-images/photo.png)](brain://{COMPACT}/title)",
            "unsupported_feature",
        ),
    ],
)
def test_inspect_and_convert_refuse_invalid_or_unsupported_active_references(
    tmp_path, syntax, code
):
    source = links_archive(tmp_path / "source.brz", syntax)
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    converted = workflow.convert(source, tmp_path / "vault")
    assert inspected.outcome == converted.outcome == "refused"
    assert inspected.issues == converted.issues
    assert converted.issues[0].code == code
    assert converted.issues[0].guidance
    assert converted.receipt is None
    assert not (tmp_path / "vault").exists()


def test_dotted_collision_target_uses_assigned_path_and_safe_original_alias(tmp_path):
    body = f"[pipe | [x]](brain://{COMPACT}/ignored-title)"
    source = links_archive(
        tmp_path / "source.brz",
        body,
        others=[thought("fedcba98-7654-4321-8765-abcdef012345", "topic.v2")],
    )
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "clean"
    assert note_body((vault / "Home — Entry thought.md").read_bytes().decode()) == (
        "# Entry thought\n\n[[Notes/Topic.v2 — 01234567.md|pipe x]]\n\n"
        "## Categories\n\n[[Categories.md|Browse categories]]\n"
    )
    record = json.loads((vault / "migration-record.json").read_bytes())
    home_record = next(t for t in record["item_targets"] if t["item_key"] == HOME)
    assert home_record["documents"][0]["references"][0]["display_text"] == "pipe | [x]"
    assert home_record["documents"][0]["references"][0]["expected_original"] == body


def test_terminal_and_json_results_report_actual_reference_conversions(
    tmp_path, capsys
):
    from brz2obsidian.cli import main

    source = links_archive(tmp_path / "source.brz", f"[Topic](brain://{COMPACT}/title)")
    assert main(["inspect", str(source)]) == 0
    captured = capsys.readouterr()
    assert "Local references: 1; planned conversions: 1" in captured.out
    assert "Converted local references" not in captured.out
    assert captured.err == ""
    assert main(["convert", str(source), str(tmp_path / "vault"), "--json"]) == 0
    captured = capsys.readouterr()
    envelope = json.loads(captured.out)
    assert (
        envelope["counts"]["source_references"]
        == envelope["counts"]["planned_references"]
        == envelope["counts"]["actual_references"]
        == 1
    )
    assert envelope["receipt"]["counts"]["actual_references"] == 1
    assert captured.err == ""

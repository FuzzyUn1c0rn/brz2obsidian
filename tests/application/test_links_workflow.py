import json
from zipfile import ZipFile

import pytest

from brz2obsidian.application.wiring import default_workflow
from tests.application.test_resources_workflow import HOME, resource_archive, thought

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
            dict(
                Id=key,
                BrainId=meta["BrainId"],
                SourceId=owner,
                SourceType=2,
                Type=1,
                NoteType=4,
                Location="Notes.md",
                DataLength=len(data),
            )
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
    assert (vault / "Home — Entry thought.md").read_bytes() == (
        b"# Entry thought\n\nBefore\r\n[[Notes/Topic.v2.md|Topic]]\r\n"
        b"![photo](Attachments/22222222/photo.png)\r\nAfter\r"
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
    references = record["documents"][0]["references"]
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
    assert home.startswith(
        f'# Entry thought\n\n![{expected_alt}](Attachments/22222222/A%20photo%20%28%C3%A9%29.png "Caption")\r\n![remote](https://example.invalid/x.png)\r'
    )
    assert (
        note
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
    assert (vault / "Home — Entry thought.md").read_bytes().decode() == (
        "# Entry thought\n\nprefix\u2028[[Notes/Topic.v2.md|one]]\r\n"
        "> - [[Notes/Topic.v2.md|two bold]] and [[Notes/Topic.v2.md|escaped end]]\r"
        "- paragraph\n\t[[Notes/Topic.v2.md|one]]\n\n"
        f"`[one]({local})`\r\n\\[literal]({local})\r\n"
        f"```md\r\n[one]({local})\r\n```\r\n"
        f"<!-- example {local} -->\r\n"
        "[external](https://example.invalid/path)\r\n"
    )
    assert result.counts.actual_references == 4


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

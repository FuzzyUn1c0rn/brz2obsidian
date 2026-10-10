"""Legacy image presentation is audited through actual ZIP Workflow and CLI."""

import json
from hashlib import sha256
from io import BytesIO

import pytest
from PIL import Image

from brz2obsidian.application.wiring import default_workflow
from tests.application.test_literal_angles_workflow import literal_archive
from tests.support.notes import note_body


def images():
    result = []
    for color, size in (("red", (4, 2)), ("blue", (3, 5))):
        stream = BytesIO()
        Image.new("RGB", size, color).save(stream, format="PNG")
        result.append(stream.getvalue())
    return result


@pytest.mark.parametrize("widths", [(75, 90), (1, 100)])
def test_sized_images_bind_intact_payloads_and_only_replace_destinations(
    tmp_path, widths
):
    a, b = images()
    first, second = widths
    body = f'Before é\r\n![one](.data/md-images/a.png#$width={first}p$ "caption") next\r![two](.data/md-images/b.png#$width={second}p$)\nAfter\n'.encode()
    source = literal_archive(
        tmp_path / "source.brz",
        body,
        resources=[
            ({"Type": 12, "Location": "a.png"}, a),
            ({"Type": 12, "Location": "b.png"}, b),
        ],
    )
    original = source.read_bytes()
    operation = default_workflow()
    inspected = operation.inspect(source)
    assert inspected.outcome == "warnings", inspected.model_dump_json()
    result = operation.convert(source, tmp_path / "vault")
    assert result.outcome == "warnings"
    assert note_body((tmp_path / "vault/Home — Entry thought.md").read_bytes()) == (
        '# Entry thought\n\nBefore é\r\n![one](Attachments/22222222/a.png "caption") next\r![two](Attachments/22222222/b.png)\nAfter\n\n## Categories\n\n[[Categories.md|Browse categories]]\n'.encode()
    )
    for name, data in (("a.png", a), ("b.png", b)):
        copied = tmp_path / "vault/Attachments/22222222" / name
        assert copied.read_bytes() == data
        entry = next(
            f for f in result.receipt.manifest if f.relative_path.endswith("/" + name)
        )
        assert entry.length == len(data) and entry.sha256 == sha256(data).hexdigest()
    assert (
        tmp_path / "vault/Attachments/22222222/Notes.md.original"
    ).read_bytes() == body
    assert result.counts.actual_references == inspected.counts.source_references == 2
    assert result.counts.actual_assets == 3
    assert result.counts.source_gaps == result.counts.actual_generated_embeds == 0
    assert source.read_bytes() == original


@pytest.mark.parametrize(
    "fields",
    [
        {"SourceType": 1},
        {"SourceType": True},
        {"Type": True},
        {"Type": 12},
        {"NoteType": True},
        {"NoteType": 4.0},
        {"NoteType": "4"},
    ],
)
def test_duplicate_diagnostic_does_not_infer_documents_from_invalid_role_scalars(
    tmp_path, fields
):
    from tests.application.test_forgotten_workflow import rewrite
    from tests.application.test_resources_workflow import HOME

    source = literal_archive(
        tmp_path / "source.brz",
        b"authored bytes",
        resources=[
            ({"Type": 12, "Location": "a.png"}, images()[0]),
            ({"Type": 12, "Location": "a.png"}, images()[1]),
        ],
    )

    def malformed(parts):
        rows = [json.loads(line) for line in parts["attachments.json"].splitlines()]
        rows[0].update(Location="Authored.md", **fields)
        parts[HOME + "/Authored.md"] = parts.pop(HOME + "/Notes.md")
        parts["attachments.json"] = "\n".join(json.dumps(r) for r in rows).encode()

    rewrite(source, malformed)
    result = default_workflow().inspect(source)
    assert result.outcome == "refused"
    assert "33333333-3333-4333-8333-333333333333" not in result.issues[0].affected
    assert "attachments.json:0" not in result.issues[0].evidence


def test_cli_marked_note_duplicate_diagnostic_exposes_document_and_evidence(
    tmp_path, capsys
):
    from brz2obsidian.cli import main
    from tests.application.test_forgotten_workflow import rewrite
    from tests.application.test_resources_workflow import HOME

    source = literal_archive(
        tmp_path / "source.brz",
        b"![one](.data/md-images/a.png#$width=75p$)",
        resources=[
            ({"Type": 12, "Location": "a.png"}, images()[0]),
            ({"Type": 12, "Location": "a.png"}, images()[1]),
        ],
    )

    def marked(parts):
        rows = [json.loads(line) for line in parts["attachments.json"].splitlines()]
        rows[0]["Location"] = "Authored.md"
        parts[HOME + "/Authored.md"] = parts.pop(HOME + "/Notes.md")
        parts["attachments.json"] = "\n".join(json.dumps(r) for r in rows).encode()

    rewrite(source, marked)
    assert main(["inspect", str(source)]) == 1
    output = capsys.readouterr().out
    assert (
        "33333333-3333-4333-8333-333333333333" in output
        and "attachments.json:0" in output
    )
    assert main(["convert", str(source), str(tmp_path / "vault"), "--json"]) == 1
    issue = json.loads(capsys.readouterr().out)["issues"][0]
    assert "33333333-3333-4333-8333-333333333333" in issue["affected"]
    assert "attachments.json:0" in issue["evidence"]
    assert not (tmp_path / "vault").exists()


def test_private_duplicate_group_still_refuses_without_marked_document_disclosure(
    tmp_path,
):
    from tests.application.test_forgotten_workflow import forget, rewrite
    from tests.application.test_graph_workflow import graph_archive, identity
    from tests.application.test_verified_coverage import add_attachment

    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", 2: "Private"},
        notes={2: (b"private authored bytes", 4)},
    )

    def duplicate(parts):
        forget(parts, 2)
        rows = [json.loads(line) for line in parts["attachments.json"].splitlines()]
        rows[0]["Location"] = "Authored.md"
        parts[identity(2) + "/Authored.md"] = parts.pop(identity(2) + "/Notes.md")
        parts["attachments.json"] = "\n".join(json.dumps(r) for r in rows).encode()
        add_attachment(parts, identity(91), 12, "a.png", images()[0], owner=identity(2))
        add_attachment(parts, identity(92), 12, "a.png", images()[1], owner=identity(2))

    rewrite(source, duplicate)
    before = source.read_bytes()
    operation = default_workflow()
    for result in (
        operation.inspect(source),
        operation.convert(source, tmp_path / "vault"),
    ):
        assert result.outcome == "refused"
        assert result.issues[0].affected == result.issues[0].evidence == ()
        for private in (
            identity(2),
            identity(91),
            identity(92),
            "Authored.md",
            "Private",
        ):
            assert private not in result.model_dump_json()
    assert not (tmp_path / "vault").exists() and source.read_bytes() == before


@pytest.mark.parametrize(
    "destination,location",
    [
        ("a.png?", "a.png"),
        ("a.png?#$width=75p$", "a.png"),
        ("a.png?x=1#$width=75p$", "a.png"),
        ("a.png#", "a.png"),
        ("a.png#$width=0p$", "a.png"),
        ("a.png#$width=101p$", "a.png"),
        ("a.png#$width=075p$", "a.png"),
        ("a.png#$width=+75p$", "a.png"),
        ("a.png#$width=75.0p$", "a.png"),
        ("a.png#$width=75P$", "a.png"),
        ("a.png#$width=75p", "a.png"),
        ("a.png#$height=75p$", "a.png"),
        ("a.png#$width=75p$#$width=90p$", "a.png"),
        ("a.png#$width=75p$&other", "a.png"),
        ("a.png#%24width=75p%24", "a.png"),
        ("a.png#&#36;width=75p&#36;", "a.png"),
        (r"a.png#\$width=75p\$", "a.png"),
        ("%2e%2e/a.png#$width=75p$", "a.png"),
        ("sub%2Fa.png#$width=75p$", "sub/a.png"),
        ("a%GG.png#$width=75p$", "a%GG.png"),
        ("a%FF.png#$width=75p$", "a�.png"),
        ("a%2520.png#$width=75p$", "a%20.png"),
    ],
)
def test_sizing_does_not_relax_strict_destinations_or_raw_declarations(
    tmp_path, destination, location
):
    source = literal_archive(
        tmp_path / "source.brz",
        f"![alt](.data/md-images/{destination})".encode(),
        resources=[({"Type": 12, "Location": location}, images()[0])],
    )
    before = source.read_bytes()
    operation = default_workflow()
    for result in (
        operation.inspect(source),
        operation.convert(source, tmp_path / "vault"),
    ):
        assert result.outcome == "refused", result.model_dump_json()
        assert result.issues[0].code == "invalid_reference"
        assert "22222222-2222-4222-8222-222222222222" in result.issues[0].affected
        assert "33333333-3333-4333-8333-333333333333" in result.issues[0].affected
        assert result.issues[0].evidence == ("attachments.json:0",)
        assert (
            "references" in result.issues[0].guidance
            and "Home" not in result.issues[0].guidance
        )
    assert not (tmp_path / "vault").exists()
    assert source.read_bytes() == before


def test_sizing_warnings_and_scoped_evidence_agree_across_cli_and_report(
    tmp_path, capsys
):
    from brz2obsidian.cli import main

    body = b'![one](.data/md-images/a.png#$width=75p$ "caption")'
    source = literal_archive(
        tmp_path / "source.brz",
        body,
        resources=[({"Type": 12, "Location": "a.png"}, images()[0])],
    )
    operation = default_workflow()
    inspected = operation.inspect(source)
    assert inspected.counts.image_presentation_normalizations == 1
    issue = inspected.issues[0]
    assert issue.code == "image_presentation_normalized" and issue.severity == "warning"
    assert "#$width=75p$" in issue.message and "responsive" in issue.message
    assert "Review image placement" in issue.guidance
    assert issue.affected[:2] == (
        "22222222-2222-4222-8222-222222222222",
        "33333333-3333-4333-8333-333333333333",
    )
    assert issue.evidence == ("attachments.json:0",)
    reference = inspected.inspection.documents[0].references[0]
    normalization = reference.presentation_normalization
    assert (normalization.declaration, normalization.start, normalization.end) == (
        "#$width=75p$",
        28,
        40,
    )
    assert normalization.basis == "document.text/unicode_codepoints"
    assert (
        normalization.document_digest
        == reference.document_digest
        == sha256(body).hexdigest()
    )
    assert reference.source_target == ".data/md-images/a.png#$width=75p$"
    assert reference.expected_original == body.decode()
    assert main(["inspect", str(source), "--json"]) == 2
    assert json.loads(capsys.readouterr().out) == json.loads(
        inspected.model_dump_json(by_alias=True)
    )
    assert main(["inspect", str(source)]) == 2
    output = capsys.readouterr().out
    assert "Image presentation normalizations: 1" in output
    assert "#$width=75p$" in output and "attachments.json:0" in output
    assert main(["convert", str(source), str(tmp_path / "vault"), "--json"]) == 2
    converted = json.loads(capsys.readouterr().out)
    assert converted["counts"]["image_presentation_normalizations"] == 1
    assert converted["issues"] == json.loads(inspected.model_dump_json())["issues"]
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    assert record["issues"] == converted["issues"]
    assert record["counts"]["image_presentation_normalizations"] == 1
    assert (
        len([a for a in record["adaptations"] if a["kind"] == "image_presentation"])
        == 1
    )
    report = (tmp_path / "vault/MIGRATION REPORT.md").read_text(encoding="utf-8")
    assert main(["convert", str(source), str(tmp_path / "vault-text")]) == 2
    output = capsys.readouterr().out
    assert "Image presentation normalizations: 1" in output and "#$width=75p$" in output
    assert "Verified vault published:" in output
    assert "> [!warning] Image sizing normalized" in report
    assert "[[Home — Entry thought.md|Entry thought]]" in report
    assert "`#$width=75p$`" in report
    assert (
        "responsive inline Markdown" in report
        and "exact percentage sizing is not reproduced" in report
    )


@pytest.mark.parametrize(
    "path,filename,expected",
    [
        ("A%20%C3%A9%20%23.png", "A é #.png", "A%20%C3%A9.png"),
        ("rate%25.png", "rate%.png", "rate.png"),
    ],
)
def test_once_encoded_names_bind_uniquely_with_sizing_and_literal_composition(
    tmp_path, path, filename, expected
):
    body = f'<Enter>![<Value>](.data/md-images/{path}#$width=75p$ "<captionword>")<Tail>\r\n'.encode()
    source = literal_archive(
        tmp_path / "source.brz",
        body,
        resources=[({"Type": 12, "Location": filename}, images()[0])],
    )
    operation = default_workflow()
    inspected = operation.inspect(source)
    assert inspected.outcome == "warnings", [
        (i.code, i.message) for i in inspected.issues
    ]
    result = operation.convert(source, tmp_path / "vault")
    assert result.outcome == "warnings"
    assert note_body(
        (tmp_path / "vault/Home — Entry thought.md").read_bytes()
    ).startswith(
        f'# Entry thought\n\n\\<Enter>![\\<Value>](Attachments/22222222/{expected} "<captionword>")\\<Tail>\r\n'.encode()
    )
    doc = inspected.inspection.documents[0]
    adapted = f'\\<Enter>![\\<Value>](.data/md-images/{path}#$width=75p$ "<captionword>")\\<Tail>\r\n'
    reference = doc.references[0]
    edit = reference.presentation_normalization
    assert adapted[reference.start : reference.end] == reference.expected_original
    assert adapted[edit.start : edit.end] == "#$width=75p$"
    assert edit.document_digest == sha256(adapted.encode()).hexdigest()
    assert (
        tmp_path / "vault/Attachments/22222222/Notes.md.original"
    ).read_bytes() == body


def test_distinct_owners_bind_same_filename_to_their_own_intact_image(tmp_path):
    from tests.application.test_links_workflow import TARGET, links_archive
    from tests.application.test_resources_workflow import HOME

    a, b = images()
    first = "![one](.data/md-images/shared.png#$width=75p$)"
    second = "![two](.data/md-images/shared.png#$width=90p$)"
    source = links_archive(
        tmp_path / "source.brz",
        first,
        resources=[
            ({"Type": 12, "Location": "shared.png"}, a),
            ({"Type": 12, "Location": "shared.png", "SourceId": TARGET}, b),
        ],
        other_notes=[(TARGET, second)],
    )
    operation = default_workflow()
    inspected = operation.inspect(source)
    assert inspected.outcome == "warnings"
    assert {i.affected[0] for i in inspected.issues} == {HOME, TARGET}
    result = operation.convert(source, tmp_path / "vault")
    assert result.outcome == "warnings"
    assert (tmp_path / "vault/Attachments/22222222/shared.png").read_bytes() == a
    assert (tmp_path / "vault/Attachments/01234567/shared.png").read_bytes() == b
    assert b"![two](../Attachments/01234567/shared.png)" in note_body(
        (tmp_path / "vault/Notes/Topic.v2.md").read_bytes()
    )
    assert (
        result.counts.actual_references
        == result.counts.image_presentation_normalizations
        == 2
    )


@pytest.mark.parametrize("kind", ["missing", "foreign", "file", "duplicate"])
def test_sizing_never_substitutes_missing_foreign_or_ambiguous_images(tmp_path, kind):
    from tests.application.test_links_workflow import TARGET
    from tests.application.test_resources_workflow import thought

    resources = (
        []
        if kind == "missing"
        else [
            (
                {
                    "Type": 1 if kind == "file" else 12,
                    "Location": "a.png",
                    **({"SourceId": TARGET} if kind == "foreign" else {}),
                },
                images()[0],
            )
        ]
    )
    if kind == "duplicate":
        resources.append(({"Type": 12, "Location": "a.png"}, images()[1]))
    source = literal_archive(
        tmp_path / "source.brz",
        b"![one](.data/md-images/a.png#$width=75p$)",
        resources=resources,
        thoughts=[thought(TARGET, "Foreign")],
    )
    before = source.read_bytes()
    operation = default_workflow()
    for result in (
        operation.inspect(source),
        operation.convert(source, tmp_path / "vault"),
    ):
        assert result.outcome == "refused"
        assert result.issues[0].code in {"invalid_reference", "invalid_source"}
        assert "22222222-2222-4222-8222-222222222222" in result.issues[0].affected
        assert result.issues[0].evidence
        assert "Home" not in result.issues[0].guidance
    assert not (tmp_path / "vault").exists() and source.read_bytes() == before


def test_scope_omission_rebuilds_sizing_and_literal_spans_without_private_evidence(
    tmp_path,
):
    import base64
    from uuid import UUID

    from tests.application.test_forgotten_workflow import forget, rewrite
    from tests.application.test_graph_workflow import graph_archive, identity
    from tests.application.test_verified_coverage import add_attachment

    compact = base64.urlsafe_b64encode(UUID(identity(2)).bytes_le).decode().rstrip("=")
    body = f"[secret <Private>](brain://{compact}/private-title) <Enter>![<Value>](.data/md-images/a.png#$width=90p$)"
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", 2: "Private"},
        notes={
            1: (body.encode(), 4),
            2: (b"![secret](.data/md-images/missing.png#$width=75p$)", 4),
        },
    )

    def prepare(parts):
        forget(parts, 2)
        add_attachment(parts, identity(91), 12, "a.png", images()[0], owner=identity(1))

    rewrite(source, prepare)
    operation = default_workflow()
    inspected = operation.inspect(source)
    assert inspected.outcome == "warnings"
    assert len(inspected.issues) == 1
    doc = inspected.inspection.documents[0]
    assert doc.original_copy_omitted
    scoped = " \\<Enter>![\\<Value>](.data/md-images/a.png#$width=90p$)"
    reference = doc.references[0]
    normalization = reference.presentation_normalization
    assert scoped[normalization.start : normalization.end] == "#$width=90p$"
    assert normalization.document_digest == sha256(scoped.encode()).hexdigest()
    result = operation.convert(source, tmp_path / "vault")
    assert result.outcome == "warnings"
    output = b"\n".join(
        p.read_bytes() for p in (tmp_path / "vault").rglob("*") if p.is_file()
    )
    for private in (
        "secret",
        "Private",
        "private-title",
        compact,
        identity(2),
        "#$width=75p$",
    ):
        assert (
            private.encode() not in output
            and private not in inspected.model_dump_json()
        )
    assert not any(
        p.name.endswith(".original") for p in (tmp_path / "vault").rglob("*")
    )


@pytest.mark.parametrize("corrupt", [False, True])
def test_opaque_image_presentation_facts_share_validation_warning_and_rendering(
    tmp_path, corrupt
):
    from tests.application.test_alternate_source import workflow
    from tests.support.folio_source import FOLIO_POLICY, FolioSourceModule
    from tests.support.paired_sources import paired_sources

    _, source = paired_sources(tmp_path)
    data = json.loads(source.read_bytes())
    document = data["documents"][0]
    image = document["references"][1]
    body = (source.parent / "payload-101").read_bytes()
    (source.parent / "payload-103").write_bytes(images()[0])
    image["presentation_normalization"] = {
        "declaration": "folio:map",
        "start": image["destination_start"],
        "end": image["destination_end"],
        "document_digest": sha256(body).hexdigest() if not corrupt else "0" * 64,
    }
    source.write_text(json.dumps(data), encoding="utf-8")
    operation = workflow(FolioSourceModule(), FOLIO_POLICY)
    result = operation.convert(source, tmp_path / "vault")
    assert result.outcome == ("refused" if corrupt else "warnings")
    if corrupt:
        assert (
            result.issues[0].code == "invalid_reference"
            and not (tmp_path / "vault").exists()
        )
    else:
        assert result.counts.image_presentation_normalizations == 1
        assert result.issues[0].code == "image_presentation_normalized"
        assert b"![Map](Attachments/00000001/map.png)" in note_body(
            (tmp_path / "vault/Home — Opening.md").read_bytes()
        )


def test_protected_and_external_images_keep_declarations_without_local_adaptation(
    tmp_path,
):
    body = b"`![code](.data/md-images/missing.png#$width=75p$)`\r\n```\n![fenced](.data/md-images/missing.png#$width=90p$)\n```\n![remote](https://example.invalid/image.png#$width=75p$)\n"
    source = literal_archive(tmp_path / "source.brz", body)
    operation = default_workflow()
    inspected = operation.inspect(source)
    assert (
        inspected.outcome == "clean"
        and inspected.counts.image_presentation_normalizations == 0
    )
    result = operation.convert(source, tmp_path / "vault")
    assert result.outcome == "clean" and result.counts.actual_references == 0
    assert note_body(
        (tmp_path / "vault/Home — Entry thought.md").read_bytes()
    ).startswith(b"# Entry thought\n\n" + body)


def test_repeated_sizing_references_have_distinct_obligations_without_extra_copy(
    tmp_path,
):
    body = b"![first](.data/md-images/a.png#$width=75p$)\n![second](.data/md-images/a.png#$width=75p$)\n"
    source = literal_archive(
        tmp_path / "source.brz",
        body,
        resources=[({"Type": 12, "Location": "a.png"}, images()[0])],
    )
    operation = default_workflow()
    inspected = operation.inspect(source)
    assert inspected.outcome == "warnings"
    assert len({i.affected[-1] for i in inspected.issues}) == 2
    assert (
        inspected.counts.image_presentation_normalizations
        == inspected.counts.source_references
        == 2
    )
    result = operation.convert(source, tmp_path / "vault")
    assert result.outcome == "warnings" and result.counts.actual_assets == 2
    assert result.counts.actual_references == 2 and result.counts.source_gaps == 0


@pytest.mark.parametrize("document_case", ["marked", "absent", "competing"])
@pytest.mark.parametrize("duplicate", [False, True])
def test_duplicate_image_diagnostics_include_all_reviewed_document_declarations(
    tmp_path, capsys, document_case, duplicate
):
    from brz2obsidian.cli import main
    from tests.application.test_forgotten_workflow import rewrite
    from tests.application.test_resources_workflow import HOME

    resources = [({"Type": 12, "Location": "a.png"}, images()[0])]
    if duplicate:
        resources.append(({"Type": 12, "Location": "a.png"}, images()[1]))
    body = b"![one](.data/md-images/a.png#$width=75p$)"
    source = literal_archive(tmp_path / "source.brz", body, resources=resources)
    competing = "bbbbbbbb-0000-4000-8000-000000000001"

    def document(parts):
        rows = [json.loads(line) for line in parts["attachments.json"].splitlines()]
        meta = json.loads(parts["meta.json"])
        if document_case != "absent":
            rows[0]["Location"] = "Authored.md"
            parts[HOME + "/Authored.md"] = parts.pop(HOME + "/Notes.md")
        else:
            parts.pop(HOME + "/Notes.md")
            meta["AttachmentFileStates"][rows[0]["Id"]] = 3
        if document_case == "competing":
            rows.append(rows[0] | {"Id": competing, "Location": "Second.md"})
            parts[HOME + "/Second.md"] = body
            meta["AttachmentFileStates"][competing] = 1
        parts["attachments.json"] = "\n".join(json.dumps(r) for r in rows).encode()
        parts["meta.json"] = json.dumps(meta).encode()

    rewrite(source, document)
    original = source.read_bytes()
    operation = default_workflow()
    inspected = operation.inspect(source)
    converted = operation.convert(source, tmp_path / "vault")
    if duplicate:
        for result in (inspected, converted):
            assert result.outcome == "refused"
            issue = result.issues[0]
            assert issue.code == "invalid_source"
            assert HOME in issue.affected
            assert "33333333-3333-4333-8333-333333333333" in issue.affected
            assert {
                "attachments.json:0",
                "attachments.json:1",
                "attachments.json:2",
            } <= set(issue.evidence)
            if document_case == "competing":
                assert (
                    competing in issue.affected
                    and "attachments.json:3" in issue.evidence
                )
        assert not (tmp_path / "vault").exists()
        assert main(["inspect", str(source)]) == 1
        output = capsys.readouterr().out
        assert (
            "33333333-3333-4333-8333-333333333333" in output
            and "attachments.json:0" in output
        )
        assert "Home" not in inspected.issues[0].guidance
        assert (
            main(["convert", str(source), str(tmp_path / "cli-vault"), "--json"]) == 1
        )
        assert (
            json.loads(capsys.readouterr().out)["issues"]
            == json.loads(inspected.model_dump_json())["issues"]
        )
        assert not (tmp_path / "cli-vault").exists()
    elif document_case == "competing":
        assert inspected.outcome == converted.outcome == "refused"
        assert not (tmp_path / "vault").exists()
    else:
        assert inspected.outcome == converted.outcome == "warnings"
    assert source.read_bytes() == original

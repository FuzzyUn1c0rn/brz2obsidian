"""Literal prose is preserved through actual BRZ Workflow and CLI routes."""

import json
from hashlib import sha256

import pytest

from brz2obsidian.application.wiring import default_workflow
from tests.application.test_forgotten_workflow import rewrite
from tests.application.test_links_workflow import COMPACT, links_archive
from tests.application.test_resources_workflow import HOME, resource_archive
from tests.support.notes import note_body


def literal_archive(path, body, *, resources=(), thoughts=()):
    source = resource_archive(path, resources, thoughts=thoughts)

    def note(parts):
        rows = [json.loads(line) for line in parts["attachments.json"].splitlines()]
        rows[0]["DataLength"] = len(body)
        parts["attachments.json"] = "\n".join(json.dumps(row) for row in rows).encode()
        parts[HOME + "/Notes.md"] = body

    rewrite(source, note)
    return source


def test_literal_angle_words_receive_only_necessary_escaping_and_exact_originals(
    tmp_path,
):
    body = b"Press <Enter>: <type>/<subtype>, <username> <IP-Adress>; <Password> <Value> <Enter> <Custom42>.\r\n"
    expected = b"Press \\<Enter>: \\<type>/\\<subtype>, \\<username> \\<IP-Adress>; \\<Password> \\<Value> \\<Enter> \\<Custom42>.\r\n"
    source = literal_archive(tmp_path / "source.brz", body)
    before = source.read_bytes()
    operation = default_workflow()
    inspected = operation.inspect(source)
    assert inspected.outcome == "clean", inspected.model_dump_json()
    converted = operation.convert(source, tmp_path / "vault")
    assert converted.outcome == "clean"
    actual = note_body((tmp_path / "vault/Home — Entry thought.md").read_bytes())
    assert actual.startswith(b"# Entry thought\n\n" + expected)
    assert (
        tmp_path / "vault/Attachments/22222222/Notes.md.original"
    ).read_bytes() == body
    assert inspected.counts.source_references == converted.counts.actual_references == 0
    assert inspected.counts.text_adaptations == converted.counts.text_adaptations == 9
    adaptations = [
        a for a in inspected.inspection.adaptations if a.kind == "literal_text"
    ]
    assert len(adaptations) == 9
    first = adaptations[0]
    assert (
        first.owner == HOME
        and first.document_key == "33333333-3333-4333-8333-333333333333"
    )
    assert first.evidence == ("attachments.json:0",)
    assert (
        first.text_edit.start,
        first.text_edit.end,
        first.text_edit.before,
        first.text_edit.after,
    ) == (6, 13, "<Enter>", "\\<Enter>")
    assert (first.text_edit.adapted_start, first.text_edit.adapted_end) == (6, 14)
    assert first.text_edit.source_basis == "scoped_source_text/unicode_codepoints"
    assert first.text_edit.adapted_basis == "document.text/unicode_codepoints"
    assert source.read_bytes() == before


@pytest.mark.parametrize("newline", ["\n", "\r", "\r\n"])
def test_active_labels_and_adjacent_references_keep_exact_coordinates(
    tmp_path, newline
):
    body = newline.join(
        [
            f"é <Value>[<Enter>](brain://{COMPACT}/title)<Tail>![<Alt>](.data/md-images/photo.png)",
            f"[<username>](brain://{COMPACT}/title)",
            "",
        ]
    )
    source = links_archive(
        tmp_path / "source.brz",
        body,
        resources=[({"Type": 12, "Location": "photo.png"}, b"photo")],
    )
    operation = default_workflow()
    inspected = operation.inspect(source)
    assert inspected.outcome == "clean", inspected.model_dump_json()
    assert inspected.counts.text_adaptations == 5
    converted = operation.convert(source, tmp_path / "vault")
    assert converted.outcome == "clean"
    actual = note_body(
        (tmp_path / "vault/Home — Entry thought.md").read_bytes()
    ).decode()
    assert (
        f"é \\<Value>[[Notes/Topic.v2.md|\\<Enter>]]\\<Tail>![\\<Alt>](Attachments/22222222/photo.png){newline}"
        in actual
    )
    assert "[[Notes/Topic.v2.md|\\<username>]]" in actual
    doc = inspected.inspection.documents[0]
    adapted = body.replace("<", "\\<")
    assert doc.text_digest == sha256(adapted.encode()).hexdigest()
    assert all(adapted[r.start : r.end] == r.expected_original for r in doc.references)
    assert all(
        body[e.start : e.end] == e.before
        and e.source_digest == sha256(body.encode()).hexdigest()
        for e in doc.text_adaptations
    )


@pytest.mark.parametrize(
    "body",
    [
        r"\<Enter> `<Value>` <https://example.invalid> <person@example.invalid>",
        "```\n<Enter></Enter>\n```\n<br> <!-- <Value> -->",
        "<Enter>\n\n```\n</Enter>\n```\n<Value>",
        "    <Enter></Enter>\n\n<Value>",
    ],
)
def test_protected_parser_regions_are_unchanged(tmp_path, body):
    source = literal_archive(tmp_path / "source.brz", body.encode())
    operation = default_workflow()
    inspected = operation.inspect(source)
    assert inspected.outcome == "clean", inspected.model_dump_json()
    converted = operation.convert(source, tmp_path / "vault")
    assert converted.outcome == "clean"
    expected = body
    if body.startswith("<Enter>"):
        expected = body.replace("<Enter>", "\\<Enter>", 1).replace(
            "<Value>", "\\<Value>"
        )
    elif body.startswith("    "):
        expected = body.replace("<Value>", "\\<Value>")
    assert note_body(
        (tmp_path / "vault/Home — Entry thought.md").read_bytes()
    ).startswith(("# Entry thought\n\n" + expected).encode())


@pytest.mark.parametrize(
    "body",
    [
        "<Enter>paired</Enter>",
        "<Enter>\n\npaired\n\n</Enter>",
        "<Enter>\n</Enter>",
        "</Enter>",
        '<Enter title="x">',
        "<Enter/>",
        "<!DOCTYPE html>",
        "<?xml version='1.0'?>",
        "<script>",
        "<style>",
        "<template>",
        "<textarea>",
        "<select>",
        "<selectedcontent>",
        "<search>",
        "<applet>",
        "<marquee>",
        "<xmp>",
        "<svg>",
        "<math>",
        "<IMAGE>",
    ],
)
def test_real_html_and_unreviewed_syntax_refuse_with_content_context(tmp_path, body):
    source = literal_archive(tmp_path / "source.brz", body.encode())
    before = source.read_bytes()
    operation = default_workflow()
    for result in (
        operation.inspect(source),
        operation.convert(source, tmp_path / "vault"),
    ):
        assert result.outcome == "refused"
        issue = result.issues[0]
        assert issue.code == "unsupported_feature"
        assert (
            HOME in issue.affected
            and "33333333-3333-4333-8333-333333333333" in issue.affected
        )
        assert "attachments.json:0" in issue.evidence
        assert "Markdown" in issue.guidance and "Home" not in issue.guidance
    assert not (tmp_path / "vault").exists()
    assert source.read_bytes() == before


def test_scope_removal_precedes_literal_evidence_coordinates(tmp_path):
    import base64
    from uuid import UUID

    from tests.application.test_forgotten_workflow import forget
    from tests.application.test_graph_workflow import graph_archive, identity

    compact = base64.urlsafe_b64encode(UUID(identity(2)).bytes_le).decode().rstrip("=")
    body = f"<Enter>[<PrivateToken> secret](brain://{compact}/private-title) é <Value>"
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", 2: "Private"},
        notes={1: (body.encode(), 4)},
    )
    rewrite(source, lambda p: forget(p, 2))
    operation = default_workflow()
    inspected = operation.inspect(source)
    assert inspected.outcome == "clean"
    assert inspected.counts.text_adaptations == 2
    doc = inspected.inspection.documents[0]
    assert doc.original_copy_omitted
    scoped = "<Enter> é <Value>"
    assert [(e.start, e.end) for e in doc.text_adaptations] == [(0, 7), (10, 17)]
    assert all(
        e.source_digest == sha256(scoped.encode()).hexdigest()
        for e in doc.text_adaptations
    )
    result = operation.convert(source, tmp_path / "vault")
    assert result.outcome == "clean"
    output = b"\n".join(
        p.read_bytes() for p in (tmp_path / "vault").rglob("*") if p.is_file()
    )
    for private in ("PrivateToken", "secret", compact, "private-title", identity(2)):
        assert (
            private not in inspected.model_dump_json()
            and private.encode() not in output
        )
    assert not any(
        p.name.endswith(".original") for p in (tmp_path / "vault").rglob("*")
    )


def test_cli_reports_literal_counts_and_context_in_both_output_formats(
    tmp_path, capsys
):
    from brz2obsidian.cli import main

    source = literal_archive(tmp_path / "source.brz", b"<Enter> <Value>")
    assert main(["inspect", str(source), "--json"]) == 0
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["counts"]["text_adaptations"] == 2
    assert (
        len(
            [
                a
                for a in envelope["inspection"]["adaptations"]
                if a["kind"] == "literal_text"
            ]
        )
        == 2
    )
    assert main(["convert", str(source), str(tmp_path / "vault")]) == 0
    assert "Literal text adaptations: 2" in capsys.readouterr().out
    bad = literal_archive(tmp_path / "bad.brz", b"<Enter></Enter>")
    assert main(["inspect", str(bad)]) == 1
    text = capsys.readouterr().out
    assert HOME in text and "attachments.json:0" in text and "Markdown" in text


@pytest.mark.parametrize("corrupt", [False, True])
def test_opaque_source_declares_generic_text_edits_without_brain_syntax(
    tmp_path, corrupt
):
    from tests.application.test_alternate_source import workflow
    from tests.support.folio_source import FOLIO_POLICY, FolioSourceModule
    from tests.support.paired_sources import paired_sources

    _, source = paired_sources(tmp_path)
    data = json.loads(source.read_bytes())
    original = "é [[literal]] prose"
    adapted = "é escaped prose"
    doc = data["documents"][0]
    asset = next(a for a in data["assets"] if a["key"] == doc["original"])
    (source.parent / asset["file"]).write_bytes(original.encode())
    doc.update(
        text=adapted,
        references=[],
        text_adaptations=[
            {
                "start": 2,
                "end": 13,
                "before": "[[literal]]",
                "after": "escaped",
                "adapted_start": 2,
                "adapted_end": 9,
                "source_digest": sha256(original.encode()).hexdigest()
                if not corrupt
                else "0" * 64,
            }
        ],
    )
    source.write_text(json.dumps(data), encoding="utf-8")
    operation = workflow(FolioSourceModule(), FOLIO_POLICY)
    result = operation.convert(source, tmp_path / "vault")
    assert result.outcome == ("refused" if corrupt else "clean")
    if corrupt:
        assert result.issues[0].code == "invalid_reference"
        assert not (tmp_path / "vault").exists()
    else:
        assert result.counts.text_adaptations == 1
        assert adapted.encode() in note_body(
            (tmp_path / "vault/Home — Opening.md").read_bytes()
        )
        assert (
            tmp_path / "vault/Attachments/00000001/Notes.md.original"
        ).read_bytes() == original.encode()


@pytest.mark.parametrize(
    "body,expected",
    [
        (b"\xef\xbb\xbf> <Enter>\r\n> <Value>\r", b"> \\<Enter>\r\n> \\<Value>\r"),
        (
            b"- <Enter>\n  continuation <Value>\n",
            b"- \\<Enter>\n  continuation \\<Value>\n",
        ),
    ],
)
def test_bom_and_transformed_block_coordinates_preserve_original_bytes(
    tmp_path, body, expected
):
    source = literal_archive(tmp_path / "source.brz", body)
    operation = default_workflow()
    inspected = operation.inspect(source)
    assert inspected.outcome == "clean"
    result = operation.convert(source, tmp_path / "vault")
    assert result.outcome == "clean"
    assert note_body(
        (tmp_path / "vault/Home — Entry thought.md").read_bytes()
    ).startswith(b"# Entry thought\n\n" + expected)
    assert (
        tmp_path / "vault/Attachments/22222222/Notes.md.original"
    ).read_bytes() == body
    original = body.decode("utf-8-sig")
    for edit in inspected.inspection.documents[0].text_adaptations:
        assert original[edit.start : edit.end] == edit.before
        assert edit.source_digest == sha256(original.encode()).hexdigest()


@pytest.mark.parametrize("version", [1, 2, 3, 4, 5, 7])
def test_result_consumers_reject_old_and_future_closed_versions(tmp_path, version):
    from pydantic import ValidationError

    from brz2obsidian.contracts import RunResult

    source = literal_archive(tmp_path / "source.brz", b"<Enter>")
    result = default_workflow().inspect(source)
    data = json.loads(result.model_dump_json(by_alias=True))
    assert RunResult.model_validate_json(json.dumps(data)) == result
    data["schema_version"] = version
    with pytest.raises(ValidationError):
        RunResult.model_validate_json(json.dumps(data))

"""Active declaration blocks refuse at actual ZIP Workflow and CLI boundaries."""

import json
from hashlib import sha256

import pytest

from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.cli import main
from tests.application.test_literal_angles_workflow import literal_archive
from tests.application.test_resources_workflow import HOME

# CommonMark 0.31.2 section 4.6 type 4: <! + ASCII letter at the
# owning container's content start. EOF cases contain no accidental later >.
DECLARATIONS = [
    " " * spaces + "<!" + letter
    for spaces in range(4)
    for letter in ("A", "a", "Z", "z")
] + [
    "<!a>",
    "   <!A> trailing",
    "<!a\n\ncontinued\nend >\n<Value>",
    "<!A\n<Value>",  # later literal-looking text closes the owned block
    "Prose\n<!a\ncontinued",
    "Prose\n   <!a\ncontinued",
    "> <!a\n> continued",
    ">   <!A\n>\n> continued",
    "> <!a\n\noutside container",
    "- <!a\n  continued",
    "1. <!z\n   continued",
    "-   <!A\n\n    continued",
    "- <!a\n\noutside container",
    "> - <!a\n>   continued",
    "- > <!a\n  > continued",
    "[label](https://example.invalid)\n<!a",
    "-\t<!a",
    "- \t<!a",
    "-\t <!a",
    "1.\t<!A",
    "1.\t  <!a",
    "10.\t<!a",
    "123.\t<!a",
    "- ordinary\n\n     <!a",
    "1.    ordinary\n\n         <!a",
    "- ordinary\n\n\t <!a",
    "> -\t<!a",
    "Paragraph\n1. <!a",
    "- > paragraph\n  <!a",
    "> - paragraph\n>\n>     <!a",
    "Paragraph\n> 10. <!a",
    "> Paragraph\n> > 10. <!a",
    "- Paragraph\n  > 10. <!a",
    "Paragraph\n\n10. <!a",
    # Conservative reviewed route: a missing old owner prefix starts a new
    # ordered container in the pinned source parser. No general lazy admission.
    "> Paragraph\n10. <!a",
    "- Paragraph\n10. <!a",
]


@pytest.mark.parametrize("newline", ["\n", "\r", "\r\n"])
@pytest.mark.parametrize("authored", DECLARATIONS)
def test_active_declaration_blocks_refuse_with_included_document_context(
    tmp_path, capsys, authored, newline
):
    body = authored.replace("\n", newline).encode()
    source = literal_archive(tmp_path / "source.brz", body)
    before = source.read_bytes()
    for observed in (
        default_workflow().inspect(source),
        default_workflow().convert(source, tmp_path / "vault"),
    ):
        assert observed.outcome == "refused", observed.model_dump_json()
        assert observed.receipt is None and observed.inspection is None
        assert observed.counts is None
        issue = observed.issues[0]
        assert issue.code == "unsupported_feature"
        assert issue.affected == (HOME, "33333333-3333-4333-8333-333333333333")
        assert issue.evidence == ("attachments.json:0", "payload:" + HOME + "/Notes.md")
        assert "Markdown" in issue.guidance and "Home" not in issue.guidance
    for arguments in (
        ["inspect", str(source), "--json"],
        ["convert", str(source), str(tmp_path / "cli-vault"), "--json"],
    ):
        assert main(arguments) == 1
        observed = json.loads(capsys.readouterr().out)
        assert observed["outcome"] == "refused" and observed["receipt"] is None
        assert observed["counts"] is None
        assert observed["issues"][0]["code"] == "unsupported_feature"
        assert observed["issues"][0]["affected"] == [
            HOME,
            "33333333-3333-4333-8333-333333333333",
        ]
    assert not (tmp_path / "vault").exists()
    assert not (tmp_path / "cli-vault").exists()
    assert source.read_bytes() == before


@pytest.mark.parametrize("newline", ["\n", "\r", "\r\n"])
def test_marked_alternate_document_retains_declaration_refusal_context(
    tmp_path, capsys, newline
):
    from tests.application.test_forgotten_workflow import rewrite

    source = literal_archive(
        tmp_path / "source.brz", ("   <!a" + newline + "body").encode()
    )

    def rename(parts):
        rows = [json.loads(line) for line in parts["attachments.json"].splitlines()]
        rows[0].update(Location="Authored.md", Name="Authored.md")
        parts[HOME + "/Authored.md"] = parts.pop(HOME + "/Notes.md")
        parts["attachments.json"] = b"\n".join(json.dumps(row).encode() for row in rows)

    rewrite(source, rename)
    before = source.read_bytes()
    inspection = default_workflow().inspect(source)
    assert (
        inspection.outcome == "refused"
        and inspection.issues[0].code == "unsupported_feature"
    )
    assert inspection.issues[0].evidence == (
        "attachments.json:0",
        "payload:" + HOME + "/Authored.md",
    )
    assert main(["convert", str(source), str(tmp_path / "vault"), "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["issues"][0]["evidence"] == [
        "attachments.json:0",
        "payload:" + HOME + "/Authored.md",
    ]
    assert not (tmp_path / "vault").exists() and source.read_bytes() == before


def test_incomplete_inline_reference_label_keeps_its_established_nonblock_meaning(
    tmp_path, capsys
):
    from tests.application.test_links_workflow import COMPACT, links_archive
    from tests.local_acceptance.checker import check_run_result, check_vault
    from tests.support.notes import note_body

    body = f"[<!a](brain://{COMPACT}/ignored)"
    source = links_archive(tmp_path / "source.brz", body)
    before = source.read_bytes()
    inspection = default_workflow().inspect(source)
    assert inspection.outcome == "clean"
    assert (
        inspection.counts.text_adaptations == 0
        and inspection.counts.source_references == 1
    )
    assert inspection.inspection.documents[0].references[0].display_text == "<!a"
    vault = tmp_path / "vault"
    assert main(["convert", str(source), str(vault), "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert note_body((vault / "Home — Entry thought.md").read_bytes()) == (
        b"# Entry thought\n\n[[Notes/Topic.v2.md|<!a]]\n\n"
        b"## Categories\n\n[[Categories.md|Browse categories]]\n"
    )
    check_run_result(result, vault, check_vault(source, vault))
    assert source.read_bytes() == before


def test_complete_declaration_in_excluded_reference_label_still_refuses_privately(
    tmp_path, capsys
):
    from tests.application.test_forgotten_workflow import forget, rewrite
    from tests.application.test_graph_workflow import graph_archive, identity
    from tests.support.combined_collection import compact

    body = f"[<!a>](brain://{compact(2)}/private-title)"
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", 2: "Private owner"},
        notes={1: (body.encode(), 4)},
    )
    rewrite(source, lambda parts: forget(parts, 2))
    before = source.read_bytes()
    observed = default_workflow().inspect(source)
    assert (
        observed.outcome == "refused"
        and observed.issues[0].code == "unsupported_feature"
    )
    assert main(["convert", str(source), str(tmp_path / "vault"), "--json"]) == 1
    cli = capsys.readouterr().out
    for private in (compact(2), identity(2), "private-title", "Private owner"):
        assert private not in cli and private not in observed.model_dump_json()
    assert not (tmp_path / "vault").exists() and source.read_bytes() == before


@pytest.mark.parametrize(
    "label", ["<!a", "   <!A", "> <!a", "- <!a", "- > <!a", "prose\n<!a", "-\t<!a"]
)
@pytest.mark.parametrize("newline", ["\n", "\r", "\r\n"])
def test_included_own_label_declarations_refuse_with_raw_field_context(
    tmp_path, capsys, label, newline
):
    from tests.application.test_graph_workflow import graph_archive, identity

    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", 2: "Probe"},
        notes={2: (b"safe body", 4)},
        labels={2: label.replace("\n", newline)},
    )
    before = source.read_bytes()
    for observed in (
        default_workflow().inspect(source),
        default_workflow().convert(source, tmp_path / "vault"),
    ):
        assert observed.outcome == "refused", observed.model_dump_json()
        assert observed.receipt is None and observed.counts is None
        issue = observed.issues[0]
        assert issue.code == "unsupported_feature"
        assert issue.affected == (identity(2),)
        assert issue.evidence == ("thoughts.json:1.Label",)
        assert "label" in issue.guidance.lower() and "Home" not in issue.guidance
    for arguments in (
        ["inspect", str(source), "--json"],
        ["convert", str(source), str(tmp_path / "cli-vault"), "--json"],
    ):
        assert main(arguments) == 1
        result = json.loads(capsys.readouterr().out)
        assert result["issues"][0]["affected"] == [identity(2)]
        assert result["issues"][0]["evidence"] == ["thoughts.json:1.Label"]
    assert not (tmp_path / "vault").exists() and not (tmp_path / "cli-vault").exists()
    assert source.read_bytes() == before


@pytest.mark.parametrize(
    "label",
    [
        "`<!a>`",
        r"\<!a>",
        "<!1> <!é>",
        "text <!a",
        "    <!a",
        "```\n<!a\n```",
        "<!-- <!a -->",
        "> ```\n> <!a\n> ```",
        "-     <!a",
        "Paragraph\n10. <!a",
        "-\t\t<!a",
    ],
)
@pytest.mark.parametrize("newline", ["\n", "\r", "\r\n"])
def test_protected_own_labels_remain_exact_opaque_strings_without_document_credit(
    tmp_path, capsys, label, newline
):
    from tests.application.test_graph_workflow import graph_archive, identity
    from tests.local_acceptance.checker import check_run_result, check_vault
    from tests.support.notes import note_body

    label = label.replace("\n", newline)
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", 2: "Probe"},
        notes={2: (b"<Value>", 4)},
        labels={2: label},
    )
    before = source.read_bytes()
    inspected = default_workflow().inspect(source)
    assert inspected.outcome == "clean", inspected.model_dump_json()
    assert len(inspected.inspection.documents) == inspected.counts.text_adaptations == 1
    document = inspected.inspection.documents[0]
    assert document.text_adaptations[0].start == 0
    assert document.text_adaptations[0].source_digest == sha256(b"<Value>").hexdigest()
    assert document.references == () and inspected.counts.source_references == 0
    vault = tmp_path / "vault"
    assert main(["convert", str(source), str(vault), "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    record = json.loads((vault / "migration-record.json").read_bytes())
    thoughts = next(
        e["records"] for e in record["original_evidence"] if e["key"] == "thoughts.json"
    )
    assert next(row for row in thoughts if row["Id"] == identity(2))["Label"] == label
    assert (
        note_body((vault / "Notes/Probe.md").read_bytes())
        == ("# Probe\n\n" + label + "\n\n\\<Value>").encode()
    )
    assert (
        vault / "Attachments/00000000000000000000000000000002/Notes.md.original"
    ).read_bytes() == b"<Value>"
    check_run_result(result, vault, check_vault(source, vault))
    assert source.read_bytes() == before


def test_omission_precedes_own_label_qualification_and_context_uses_retained_index(
    tmp_path, capsys
):
    from tests.application.test_forgotten_workflow import forget, rewrite
    from tests.application.test_graph_workflow import graph_archive, identity

    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", 2: "Hidden", 3: "Included"},
        labels={2: "<!a private label", 3: "<!a"},
    )
    rewrite(source, lambda parts: forget(parts, 2))
    before = source.read_bytes()
    result = default_workflow().inspect(source)
    assert result.outcome == "refused" and result.issues[0].affected == (identity(3),)
    # Public pointers address retained safe root rows, not original raw ordinal2.
    assert result.issues[0].evidence == ("thoughts.json:1.Label",)
    assert main(["convert", str(source), str(tmp_path / "vault"), "--json"]) == 1
    cli = capsys.readouterr().out
    for private in (identity(2), "Hidden", "private label"):
        assert private not in cli and private not in result.model_dump_json()
    assert not (tmp_path / "vault").exists() and source.read_bytes() == before
    assert sha256(source.read_bytes()).digest() == sha256(before).digest()


PROTECTED_NEIGHBORS = [
    "`<!a>`",
    "`<!a`",
    r"\<!a>",
    r"\<!A",
    "<!é> <!1> <!_>",
    "Prose <!a\ncontinued",
    "Prose\n    <!a\ncontinued",  # paragraph lazy continuation, not a new block
    "    <!a\n    > > literal code",
    "\t<!a",
    "```\n<!a\n> > literal code\n- literal code\n```",
    "~~~~\n   <!A\n> literal code\n~~~~",
    "<!--\n<!a\n> > comment data\n- comment data\n-->",
    "> ```\n> <!a\n> ```",
    "- ~~~\n  <!a\n  ~~~",
    "> ```\n> <!a",  # containing quote ends naturally before live paragraph
    "- ~~~\n  <!a",  # containing list ends naturally before live paragraph
    ">     <!a",
    "-     <!a",
    "- > ```\n  > <!a\n  > ```",
    "> - ~~~\n>   <!a\n>   ~~~",
    "- > ```\n  > <!a",  # nested container exit is not a top-level guard
    "> - <!--\n>   <!a\n>   -->",
    "-\t  <!a",
    "-\t\t<!a",
    "1.\t   <!a",
    "10. \t<!a",
    "123.\t <!a",
    "- ordinary\n\n      <!a",
    "1.    ordinary\n\n          <!a",
    "- ordinary\n\n\t\t<!a",
    "> - \t<!a",
    "Paragraph\n10. <!a",
    "> Paragraph\n> 10. <!a",
    "- Paragraph\n  10. <!a",
    "- >     <!a\n  >     code",
    "> -     <!a\n>       code",
]


@pytest.mark.parametrize("newline", ["\n", "\r", "\r\n"])
@pytest.mark.parametrize("prefix", PROTECTED_NEIGHBORS)
def test_protected_neighbors_keep_exact_live_facts_and_complete_raw_audits(
    tmp_path, capsys, prefix, newline
):
    from tests.application.test_links_workflow import COMPACT, links_archive
    from tests.application.test_sized_images_workflow import images
    from tests.local_acceptance.checker import check_run_result, check_vault
    from tests.support.notes import note_body

    phrase = f"[Live](brain://{COMPACT}/ignored)"
    image_phrase = '![photo](.data/md-images/a.png "caption")'
    body = (prefix + "\n\n<Value> é " + phrase + " " + image_phrase).replace(
        "\n", newline
    )
    adapted = body.replace("<Value>", "\\<Value>")
    expected = adapted.replace(phrase, "[[Notes/Topic.v2.md|Live]]").replace(
        ".data/md-images/a.png", "Attachments/22222222/a.png"
    )
    image = images()[0]
    source = links_archive(
        tmp_path / "source.brz",
        body,
        resources=[({"Type": 12, "Location": "a.png"}, image)],
    )
    before = source.read_bytes()
    inspected = default_workflow().inspect(source)
    assert inspected.outcome == "clean", inspected.model_dump_json()
    assert inspected.receipt is None and inspected.issues == ()
    assert inspected.counts.text_adaptations == 1
    assert inspected.counts.source_references == 2
    assert inspected.counts.source_gaps == inspected.counts.generated_presentations == 0
    document = inspected.inspection.documents[0]
    edit = document.text_adaptations[0]
    start = body.index("<Value>")
    assert (edit.start, edit.end, edit.adapted_start, edit.adapted_end) == (
        start,
        start + 7,
        start,
        start + 8,
    )
    assert (edit.before, edit.after) == ("<Value>", "\\<Value>")
    assert edit.source_digest == sha256(body.encode()).hexdigest()
    assert edit.source_basis == "scoped_source_text/unicode_codepoints"
    assert edit.adapted_basis == "document.text/unicode_codepoints"
    assert document.text_digest == sha256(adapted.encode()).hexdigest()
    for reference, original in zip(
        document.references, (phrase, image_phrase), strict=True
    ):
        assert (reference.start, reference.end) == (
            adapted.index(original),
            adapted.index(original) + len(original),
        )
        assert reference.expected_original == original
    assert main(["inspect", str(source), "--json"]) == 0
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["receipt"] is None and envelope["counts"]["source_references"] == 2
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault).model_dump(mode="json")
    assert result["outcome"] == "clean" and result["counts"]["actual_references"] == 2
    assert (
        note_body((vault / "Home — Entry thought.md").read_bytes())
        == (
            "# Entry thought\n\n"
            + expected
            + "\n\n## Categories\n\n[[Categories.md|Browse categories]]\n"
        ).encode()
    )
    assert (
        vault / "Attachments/22222222/Notes.md.original"
    ).read_bytes() == body.encode()
    assert (vault / "Attachments/22222222/a.png").read_bytes() == image
    check_run_result(result, vault, check_vault(source, vault))
    cli_vault = tmp_path / "cli-vault"
    assert main(["convert", str(source), str(cli_vault), "--json"]) == 0
    cli_result = json.loads(capsys.readouterr().out)
    check_run_result(cli_result, cli_vault, check_vault(source, cli_vault))
    assert (cli_vault / "Home — Entry thought.md").read_bytes() == (
        vault / "Home — Entry thought.md"
    ).read_bytes()
    assert source.read_bytes() == before


@pytest.mark.parametrize("ownership", ["direct", "transitive", "opaque"])
def test_forgotten_declaration_content_and_evidence_stay_private(
    tmp_path, capsys, ownership
):
    from tests.application.test_forgotten_workflow import forget, rewrite
    from tests.application.test_graph_workflow import graph_archive, identity
    from tests.local_acceptance.checker import check_run_result, check_vault

    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", 2: "Hidden owner", 3: "Included"},
        labels={2: "<!a private label"},
        notes={2: (b"<!a\nprivate declaration body", 4), 3: (b"<Value>", 4)},
    )

    def edit(parts):
        forget(parts, 2)
        if ownership == "direct":
            return
        associated = {"Id": identity(8100), "ThoughtId": identity(2)}
        if ownership == "opaque":
            associated = {"Id": identity(8100), "Nested": json.dumps(associated)}
        parts["settings.json"] += b"\n" + json.dumps(associated).encode()
        parts["settings.json"] += (
            b"\n"
            + json.dumps(
                {
                    "Id": identity(8101),
                    "Nested": {"AttachmentId": identity(8100)},
                    "Value": "<!a\nprivate declaration body",
                }
            ).encode()
        )

    rewrite(source, edit)
    before = source.read_bytes()
    inspection = default_workflow().inspect(source)
    assert inspection.outcome == "clean", inspection.model_dump_json()
    assert (
        inspection.counts.source_items == 2 and inspection.counts.text_adaptations == 1
    )
    assert main(["inspect", str(source), "--json"]) == 0
    cli_inspection = capsys.readouterr().out
    vault = tmp_path / "vault"
    assert main(["convert", str(source), str(vault), "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    output = b"\n".join(p.read_bytes() for p in vault.rglob("*") if p.is_file())
    for secret in (
        "Hidden owner",
        "private declaration body",
        identity(2),
        identity(2002),
        identity(8100),
        identity(8101),
    ):
        assert secret not in inspection.model_dump_json()
        assert secret not in cli_inspection and secret not in json.dumps(result)
        assert secret.encode() not in output
    check_run_result(result, vault, check_vault(source, vault))
    assert source.read_bytes() == before

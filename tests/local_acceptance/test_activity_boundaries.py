"""Authored ZIP bytes establish independent code/comment and retained-state scope."""

import hashlib
import json
from zipfile import ZipFile

import pytest

from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.cli import main
from tests.application.test_combined_workflow import HOME_BODY
from tests.application.test_forgotten_workflow import forget, rewrite
from tests.application.test_graph_workflow import graph_archive, identity
from tests.application.test_verified_coverage import add_attachment
from tests.local_acceptance.checker import check_run_result, check_vault, load_json
from tests.local_acceptance.scope import scope
from tests.local_acceptance.test_checker_v2 import rewrite_record
from tests.local_acceptance.text import active_mask, literal_edits
from tests.support.combined_collection import combined_archive, compact
from tests.support.notes import note_body

CASES = [
    (
        "`<!--` <Value> <!-- harmless comment -->",
        "`<!--` \\<Value> <!-- harmless comment -->",
        ["<Value>"],
    ),
    ("<!-- unfinished comment <Hidden>", "<!-- unfinished comment <Hidden>", []),
    (
        "x <!-- ` --> <Value> ` <Tail>",
        "x <!-- ` --> \\<Value> ` \\<Tail>",
        ["<Value>", "<Tail>"],
    ),
    (
        "`<!--` <Value> <!-- ` --> <Tail> `<!--`",
        "`<!--` \\<Value> <!-- ` --> \\<Tail> `<!--`",
        ["<Value>", "<Tail>"],
    ),
    (
        "<!-- <Hidden> -->\n<Value>",
        "<!-- <Hidden> -->\n\\<Value>",
        ["<Value>"],
    ),
    ("x <!-- <Hidden> --> <Value>", "x <!-- <Hidden> --> \\<Value>", ["<Value>"]),
    ("x <!-- <Hidden> -->", "x <!-- <Hidden> -->", []),
    (
        "x <!-- <!-- <Hidden> --> <Value>",
        "x <!-- <!-- <Hidden> --> \\<Value>",
        ["<Value>"],
    ),
    ("x <!-- unfinished <Value>", "x <!-- unfinished \\<Value>", ["<Value>"]),
    ("> <!-- unfinished\n> <Hidden>", "> <!-- unfinished\n> <Hidden>", []),
    ("- <!-- unfinished\n  <Hidden>", "- <!-- unfinished\n  <Hidden>", []),
    ("> <!-- unfinished\n\n<Value>", "> <!-- unfinished\n\n\\<Value>", ["<Value>"]),
    (
        "x <!-- `\n```md\n<Hidden>\n-->\n<Value>",
        "x <!-- `\n```md\n<Hidden>\n-->\n<Value>",
        [],
    ),
    (
        "<!-- `\n```\n<Hidden>\n-->\n<Value>",
        "<!-- `\n```\n<Hidden>\n-->\n\\<Value>",
        ["<Value>"],
    ),
    (
        "```md\n<!-- <Hidden>\n```\n<Value>",
        "```md\n<!-- <Hidden>\n```\n\\<Value>",
        ["<Value>"],
    ),
    (
        "~~~\n<!-- <Hidden>\n~~\n<Hidden2>\n~~~\n<Value>",
        "~~~\n<!-- <Hidden>\n~~\n<Hidden2>\n~~~\n\\<Value>",
        ["<Value>"],
    ),
    ("    <!-- <Hidden>\n\n<Value>", "    <!-- <Hidden>\n\n\\<Value>", ["<Value>"]),
    (
        "x\n    <!-- <Hidden> --> <Value>",
        "x\n    <!-- <Hidden> --> \\<Value>",
        ["<Value>"],
    ),
    (r"x \<!-- <Value> -->", r"x \<!-- \<Value> -->", ["<Value>"]),
    (r"x \\<!-- <Hidden> --> <Value>", r"x \\<!-- <Hidden> --> \<Value>", ["<Value>"]),
    (
        r"x \` <!-- <Hidden> --> <Value> `",
        r"x \` <!-- <Hidden> --> \<Value> `",
        ["<Value>"],
    ),
    (r"`a\` <Value>", r"`a\` \<Value>", ["<Value>"]),
    ("x &lt;!-- <Value>", "x &lt;!-- \\<Value>", ["<Value>"]),
    ("``<!-- ` <Hidden>`` <Value>", "``<!-- ` <Hidden>`` \\<Value>", ["<Value>"]),
    ("`<Value> ``", "`\\<Value> ``", ["<Value>"]),
    ("`<!--\n<Hidden>` <Value>", "`<!--\n<Hidden>` \\<Value>", ["<Value>"]),
    ("`x\n\n<Value> `", "`x\n\n\\<Value> `", ["<Value>"]),
    (
        "`x\n~~~\n<Hidden>\n~~~\n<Value> `",
        "`x\n~~~\n<Hidden>\n~~~\n\\<Value> `",
        ["<Value>"],
    ),
    ("α\u2028`<!--` <Value>", "α\u2028`<!--` \\<Value>", ["<Value>"]),
    ("> ```\n> <Hidden>\n\n<Value>", "> ```\n> <Hidden>\n\n\\<Value>", ["<Value>"]),
    ("- ```\n  <Hidden>\n\n<Value>", "- ```\n  <Hidden>\n\n\\<Value>", ["<Value>"]),
    (
        "`<Hidden>\nheading\n---\n<Value> `",
        "`\\<Hidden>\nheading\n---\n\\<Value> `",
        ["<Hidden>", "<Value>"],
    ),
    (
        "`<Hidden>\n***\n<Value> `",
        "`\\<Hidden>\n***\n\\<Value> `",
        ["<Hidden>", "<Value>"],
    ),
]


@pytest.mark.parametrize("body,expected,tokens", CASES)
def test_actual_zip_comment_code_ownership_and_exact_note_bytes(
    tmp_path, body, expected, tokens
):
    source = graph_archive(
        tmp_path / "source.brz", {1: "Home", 2: "Probe"}, notes={2: (body.encode(), 4)}
    )
    before = source.read_bytes()
    operation = default_workflow()
    inspected = operation.inspect(source)
    assert inspected.outcome == "clean", inspected.model_dump_json()
    assert inspected.receipt is None and inspected.counts.text_adaptations == len(
        tokens
    )
    assert inspected.counts.source_references == 0
    vault = tmp_path / "vault"
    result = operation.convert(source, vault)
    assert result.outcome == "clean", result.model_dump_json()
    assert (
        note_body((vault / "Notes/Probe.md").read_bytes())
        == ("# Probe\n\n" + expected).encode()
    )
    assert (
        vault / "Attachments/00000000000000000000000000000002/Notes.md.original"
    ).read_bytes() == body.encode()
    adapted, edits = literal_edits(body)
    assert adapted == expected and [e["before"] for e in edits] == tokens
    for ordinal, (edit, token) in enumerate(zip(edits, tokens, strict=True)):
        start = body.index(token)
        assert (edit["start"], edit["end"]) == (start, start + len(token))
        assert (edit["adapted_start"], edit["adapted_end"]) == (
            start + ordinal,
            start + ordinal + len(token) + 1,
        )
        assert edit["source_digest"] == hashlib.sha256(body.encode()).hexdigest()
        assert edit["source_basis"] == "scoped_source_text/unicode_codepoints"
        assert edit["adapted_basis"] == "document.text/unicode_codepoints"
    summary = check_vault(source, vault)
    check_run_result(result.model_dump(mode="json"), vault, summary)
    assert source.read_bytes() == before


@pytest.mark.parametrize("newline", ["\n", "\r", "\r\n"])
@pytest.mark.parametrize(
    "damage",
    ["underescape", "code_escape", "comment_escape", "span", "basis", "digest"],
)
def test_comment_code_cli_raw_scoped_coordinates_and_rehashed_corruption(
    tmp_path, capsys, newline, damage
):
    body = "é `<!--` <Value> <!-- ` <Hidden> -->" + newline + "<Tail>"
    expected = "é `<!--` \\<Value> <!-- ` <Hidden> -->" + newline + "\\<Tail>"
    source = graph_archive(
        tmp_path / "source.brz", {1: "Home", 2: "Probe"}, notes={2: (body.encode(), 4)}
    )
    inspected = default_workflow().inspect(source)
    for json_mode in (False, True):
        assert main(["inspect", str(source), *(["--json"] if json_mode else [])]) == 0
        captured = capsys.readouterr()
        assert not captured.err
        if json_mode:
            parsed = json.loads(captured.out)
            assert (
                parsed["counts"] == inspected.counts.model_dump(mode="json")
                and parsed["receipt"] is None
            )
    vault = tmp_path / "vault"
    assert main(["convert", str(source), str(vault), "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    path = vault / "Notes/Probe.md"
    assert note_body(path.read_bytes()) == ("# Probe\n\n" + expected).encode()
    check_run_result(result, vault, check_vault(source, vault))
    record = load_json((vault / "migration-record.json").read_bytes())
    before = path.read_bytes()
    if damage in {"underescape", "code_escape", "comment_escape"}:
        old, new = {
            "underescape": (b"\\<Value>", b"<Value>"),
            "code_escape": (b"`<!--`", b"`\\<!--`"),
            "comment_escape": (b"<Hidden>", b"\\<Hidden>"),
        }[damage]
        path.write_bytes(before.replace(old, new, 1))
        assert path.read_bytes() != before
    else:
        doc = next(d for t in record["item_targets"] for d in t["documents"])
        edit = doc["text_adaptations"][0]
        field = {"span": "start", "basis": "source_basis", "digest": "source_digest"}[
            damage
        ]
        edit[field] = edit[field] + 1 if field == "start" else "forged"
        next(a for a in record["adaptations"] if a["kind"] == "literal_text")[
            "text_edit"
        ] = edit.copy()
    rewrite_record(vault, record, result)
    with pytest.raises(AssertionError):
        check_vault(source, vault)


@pytest.mark.parametrize(
    "state", [{"private": "excluded malformed state"}, 0, True, [], None]
)
@pytest.mark.parametrize("transitive", [False, True])
def test_excluded_state_is_omitted_without_blocking_public_complete_audit(
    tmp_path, capsys, state, transitive
):
    source = combined_archive(tmp_path / "source.brz")

    def edit(parts):
        meta = json.loads(parts["meta.json"])
        omitted_id = identity(6011 if transitive else 6014)
        if transitive:
            rows = [json.loads(line) for line in parts["attachments.json"].splitlines()]
            next(r for r in rows if r["Id"] == omitted_id)["ObjectId"] = identity(6014)
            parts["attachments.json"] = b"\n".join(
                json.dumps(row).encode() for row in rows
            )
        meta["AttachmentFileStates"][omitted_id] = state
        parts["meta.json"] = json.dumps(meta).encode()

    rewrite(source, edit)
    before = source.read_bytes()
    inspected = default_workflow().inspect(source)
    assert inspected.outcome == "warnings" and inspected.receipt is None
    assert main(["inspect", str(source), "--json"]) == 2
    cli_inspected = json.loads(capsys.readouterr().out)
    assert cli_inspected["counts"] == inspected.counts.model_dump(mode="json")
    vault = tmp_path / "vault"
    assert main(["convert", str(source), str(vault), "--json"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert note_body((vault / "Home — Opening.md").read_bytes()) == HOME_BODY
    assert all(
        identity(6014).encode() not in p.read_bytes()
        and b"excluded malformed state" not in p.read_bytes()
        for p in vault.rglob("*")
        if p.is_file()
    )
    check_run_result(result, vault, check_vault(source, vault))
    assert source.read_bytes() == before
    # Excluded malformed states are omitted, never a license to publish them.
    record = load_json((vault / "migration-record.json").read_bytes())
    meta = next(e for e in record["original_evidence"] if e["key"] == "meta.json")
    meta["records"][0]["AttachmentFileStates"][identity(6014)] = state
    rewrite_record(vault, record, result)
    with pytest.raises(AssertionError):
        check_vault(source, vault)


@pytest.mark.parametrize("state", [{"bad": 1}, 0, True, [], None])
def test_included_malformed_state_and_unknown_state_key_still_refuse(tmp_path, state):
    source = combined_archive(tmp_path / "source.brz")

    def edit(parts):
        meta = json.loads(parts["meta.json"])
        meta["AttachmentFileStates"][identity(6011)] = state
        parts["meta.json"] = json.dumps(meta).encode()

    rewrite(source, edit)
    assert default_workflow().inspect(source).outcome == "refused"
    with ZipFile(source) as archive:
        raw = {
            name: [json.loads(line) for line in archive.read(name).splitlines()]
            for name in archive.namelist()
            if name.endswith(".json")
        }
        with pytest.raises(AssertionError, match="state"):
            scope(raw, archive)
        raw["meta.json"][0]["AttachmentFileStates"] = {identity(9999): state}
        with pytest.raises(AssertionError, match="state-map ownership"):
            scope(raw, archive)


def test_mask_preserves_raw_length_and_non_markdown_unicode_line_separator():
    body = "α\u2028`<!--` <Value> <!-- hidden -->"
    mask = active_mask(body)
    assert len(mask) == len(body) and mask.index("<Value>") == 9
    assert mask[:2] == body[:2] and "<!--" not in mask


def test_block_comment_closing_line_is_protected_but_unreviewed_html_refuses(
    tmp_path, capsys
):
    body = "<!-- harmless --> <Unreviewed>\n<Value>"
    mask = active_mask(body)
    assert mask[: body.index("\n")] == " " * body.index("\n")
    assert mask[body.index("<Value>") :] == "<Value>"
    source = graph_archive(
        tmp_path / "source.brz", {1: "Home", 2: "Probe"}, notes={2: (body.encode(), 4)}
    )
    original = source.read_bytes()
    inspected = default_workflow().inspect(source)
    assert (
        inspected.outcome == "refused"
        and inspected.issues[0].code == "unsupported_feature"
    )
    assert main(["convert", str(source), str(tmp_path / "vault"), "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["outcome"] == "refused"
    assert not (tmp_path / "vault").exists() and source.read_bytes() == original


@pytest.mark.parametrize("newline", ["\n", "\r", "\r\n"])
def test_forgotten_removal_then_code_comment_live_reference_spans_are_raw_derived(
    tmp_path, newline
):
    tail = f"`<!--` <Value> <!-- ` <Hidden> --> [<CaptionWord>](brain://{compact(4)}/ignored) ![safe](.data/md-images/p.png#$width=75p$){newline}<Tail>"
    original = f"é [private](brain://{compact(3)}/ignored)" + tail
    scoped = "é " + tail
    adapted = (
        scoped.replace("<Value>", "\\<Value>")
        .replace("<CaptionWord>", "\\<CaptionWord>")
        .replace("<Tail>", "\\<Tail>")
    )
    expected = f"# Probe\n\né `<!--` \\<Value> <!-- ` <Hidden> --> [[Notes/Live.md|\\<CaptionWord>]] ![safe](../Attachments/00000000000000000000000000000002/p.png){newline}\\<Tail>"
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", 2: "Probe", 3: "Private", 4: "Live"},
        notes={2: (original.encode(), 4)},
    )
    from tests.application.test_sized_images_workflow import images

    pixels = images()[0]

    def edit(parts):
        forget(parts, 3)
        add_attachment(parts, identity(3001), 12, "p.png", pixels, owner=identity(2))

    rewrite(source, edit)
    inspected = default_workflow().inspect(source)
    assert inspected.outcome == "warnings", inspected.model_dump_json()
    assert (
        inspected.counts.source_references == 2
        and inspected.counts.text_adaptations == 3
    )
    doc = next(d for d in inspected.inspection.documents if d.owner == identity(2))
    assert doc.text_digest == hashlib.sha256(adapted.encode()).hexdigest()
    edits = [
        a.text_edit
        for a in inspected.inspection.adaptations
        if a.kind == "literal_text"
    ]
    for ordinal, (edit, token) in enumerate(
        zip(edits, ("<Value>", "<CaptionWord>", "<Tail>"), strict=True)
    ):
        start = scoped.index(token)
        assert edit.source_digest == hashlib.sha256(scoped.encode()).hexdigest()
        assert edit.start == start and edit.end == start + len(token)
        assert (
            edit.adapted_start == start + ordinal
            and edit.adapted_end == start + ordinal + len(token) + 1
        )
    assert all(adapted[r.start : r.end] == r.expected_original for r in doc.references)
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert note_body((vault / "Notes/Probe.md").read_bytes()) == expected.encode()
    assert not any(p.name.endswith(".original") for p in vault.rglob("*"))
    assert (
        vault / "Attachments/00000000000000000000000000000002/p.png"
    ).read_bytes() == pixels
    check_run_result(result.model_dump(mode="json"), vault, check_vault(source, vault))

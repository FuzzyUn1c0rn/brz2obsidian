"""Generated Markdown guards are raw-derived framing, not source adaptations."""

import hashlib
import json

import pytest

from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.cli import main
from tests.application.test_forgotten_workflow import rewrite
from tests.application.test_graph_workflow import graph_archive, identity
from tests.application.test_verified_coverage import add_attachment
from tests.local_acceptance.checker import check_run_result, check_vault, load_json
from tests.local_acceptance.test_checker_v2 import rewrite_record
from tests.support.notes import note_body

NAVIGATION = "## Categories\n\n[[Categories.md|Browse categories]]\n"
CHILDREN = "## Children\n\n- [[Notes/Live.md|Live]]\n"
RESOURCES = "## Resources\n\n- [resource.pdf](<file:///C:/absent/resource.pdf>)\n"


def source_with_tail(path, body, tail, *, label=None):
    owner = 1 if tail in {"home", "all"} else 2
    source = graph_archive(
        path,
        {1: "Home", 2: "Probe", 3: "Live"},
        [(owner, 3, 1, 1, -1)] if tail in {"children", "all"} else [],
        notes={owner: (body.encode(), 4)},
        labels={owner: label} if label else None,
    )
    if tail in {"resources", "all"}:

        def resource(parts):
            add_attachment(
                parts,
                identity(7001),
                2,
                r"C:\absent\resource.pdf",
                state=None,
                owner=identity(owner),
            )
            rows = [json.loads(line) for line in parts["attachments.json"].splitlines()]
            next(row for row in rows if row["Id"] == identity(7001))["Name"] = (
                "resource.pdf"
            )
            parts["attachments.json"] = b"\n".join(
                json.dumps(row).encode() for row in rows
            )

        rewrite(source, resource)
    return source, owner, "Home — Home.md" if owner == 1 else "Notes/Probe.md"


def authored_full_note(body, guard, tail, *, section_break="\n\n", prefix=None):
    """Assemble authored bytes with fixture-declared guard and literal section break.

    The caller works the break from its known ending; this helper neither
    normalizes source encodings nor infers padding from body/guard content.
    Resources always add two LF bytes; their final LF leaves one before Children,
    whose final LF in turn leaves one before Categories.
    """
    text = (
        prefix
        if prefix is not None
        else "# " + ("Home" if tail in {"home", "all"} else "Probe") + "\n\n"
    )
    text += body
    if tail != "none":
        text += guard
    text += {
        "none": "",
        "resources": "\n\n" + RESOURCES,
        "children": section_break + CHILDREN,
        "home": section_break + NAVIGATION,
        "all": "\n\n" + RESOURCES + "\n" + CHILDREN + "\n" + NAVIGATION,
    }[tail]
    return text.encode()


@pytest.mark.parametrize("block", ["comment", "backtick", "tilde"])
@pytest.mark.parametrize("tail", ["none", "home", "children", "resources", "all"])
@pytest.mark.parametrize("newline", ["\n", "\r", "\r\n"])
def test_raw_open_block_and_generated_sections_have_complete_exact_bytes(
    tmp_path, block, tail, newline
):
    opener, closer = {
        "comment": ("<!-- unfinished comment", "-->"),
        "backtick": ("```md", "```"),
        "tilde": ("~~~md", "~~~"),
    }[block]
    body = opener + newline + "<Hidden>"
    guard = "\n\n" + closer + "\n"
    source, owner, note_path = source_with_tail(tmp_path / "source.brz", body, tail)
    before = source.read_bytes()
    operation = default_workflow()
    inspected = operation.inspect(source)
    assert inspected.outcome == "clean", inspected.model_dump_json()
    assert inspected.receipt is None
    assert (
        inspected.counts.text_adaptations,
        inspected.counts.source_references,
        inspected.counts.source_gaps,
        inspected.counts.planned_generated_embeds,
    ) == (0, 0, 0, 0)
    vault = tmp_path / "vault"
    result = operation.convert(source, vault)
    assert result.outcome == "clean", result.model_dump_json()
    assert note_body((vault / note_path).read_bytes()) == authored_full_note(
        body, guard, tail, section_break="\n"
    )
    original = vault / (
        "Attachments/" + identity(owner).replace("-", "") + "/Notes.md.original"
    )
    assert original.read_bytes() == body.encode()
    document = inspected.inspection.documents[0]
    assert document.text_digest == hashlib.sha256(body.encode()).hexdigest()
    assert document.references == () and not any(
        a.kind in {"literal_text", "image_presentation_normalized"}
        for a in inspected.inspection.adaptations
    )
    check_run_result(result.model_dump(mode="json"), vault, check_vault(source, vault))
    assert source.read_bytes() == before


@pytest.mark.parametrize(
    "body,guard,section_break",
    [
        ("<!-- unfinished comment <Value>", "\n\n-->\n", "\n"),
        ("<!-- closed -->", "", "\n\n"),
        ("```md\n<Hidden>\n```", "", "\n\n"),
        ("~~~~md\r\n<Hidden>\r\n~~~~~~", "", "\n\n"),
        ("`````md\n<Hidden>\n```", "\n\n`````\n", "\n"),
        ("~~~~md\r<Hidden>\r~~~~ text", "\n\n~~~~\n", "\n"),
        ("> <!-- unfinished\n> <Hidden>", "", "\n\n"),
        ("- <!-- unfinished\n  <Hidden>", "", "\n\n"),
        ("> ```md\n> <Hidden>", "", "\n\n"),
        ("- ```md\n  <Hidden>", "", "\n\n"),
        ("- example\n\n  ```md\n  <Hidden>", "", "\n\n"),
        ("> - ```md\n>   <Hidden>", "", "\n\n"),
        ("> > <!-- unfinished\n> > <Hidden>", "", "\n\n"),
        # One authored CRLF is retained verbatim; only one generated LF is needed.
        ("    <!-- <Hidden>\r\n", "", "\n"),
        ("<!-- ```\n<Hidden>", "\n\n-->\n", "\n"),
        ("~~~md\n<!-- <Hidden>", "\n\n~~~\n", "\n"),
        ("plain `<!--`", "", "\n\n"),
    ],
)
@pytest.mark.parametrize("tail", ["none", "home", "children", "resources"])
def test_closed_container_and_delimiter_boundaries_do_not_invent_guards(
    tmp_path, body, guard, section_break, tail
):
    source, _, note_path = source_with_tail(tmp_path / "source.brz", body, tail)
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "clean", result.model_dump_json()
    assert result.counts.text_adaptations == result.counts.actual_references == 0
    assert note_body((vault / note_path).read_bytes()) == authored_full_note(
        body, guard, tail, section_break=section_break
    )
    check_vault(source, vault)


def test_mixed_authored_endings_need_no_separator_after_two_endings(tmp_path):
    # Worked bytes: the final LF + CRLF already give the blank line before
    # Categories. Internal CRLF/CR/LF and both ending bytes remain authored.
    body = "plain\r\nrow\rlast\n\r\n"
    expected = (
        b"# Home\n\nplain\r\nrow\rlast\n\r\n"
        b"## Categories\n\n[[Categories.md|Browse categories]]\n"
    )
    source, owner, note_path = source_with_tail(tmp_path / "source.brz", body, "home")
    before = source.read_bytes()
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "clean", result.model_dump_json()
    assert result.counts.text_adaptations == result.counts.actual_references == 0
    assert note_body((vault / note_path).read_bytes()) == expected
    assert (
        vault
        / ("Attachments/" + identity(owner).replace("-", "") + "/Notes.md.original")
    ).read_bytes() == b"plain\r\nrow\rlast\n\r\n"
    check_run_result(result.model_dump(mode="json"), vault, check_vault(source, vault))
    assert source.read_bytes() == before


@pytest.mark.parametrize(
    "block,damage",
    [
        (block, damage)
        for block in ["comment", "backtick", "tilde", "closed"]
        # Closed blocks take the same extra-closure corruption in every branch.
        for damage in (
            ["extra"] if block == "closed" else ["missing", "wrong", "extra", "moved"]
        )
    ],
)
@pytest.mark.parametrize("tail", ["home", "children", "resources"])
def test_rehashed_missing_wrong_extra_moved_generated_closures_reject(
    tmp_path, block, tail, damage
):
    opener, closer, section_break = {
        "comment": ("<!-- unfinished", "-->", "\n"),
        "backtick": ("````md", "````", "\n"),
        "tilde": ("~~~~md", "~~~~", "\n"),
        "closed": ("<!-- closed -->", "", "\n\n"),
    }[block]
    body = opener + ("\n<Hidden>" if block != "closed" else "")
    guard = "\n\n" + closer + "\n" if closer else ""
    source, _, note_path = source_with_tail(tmp_path / "source.brz", body, tail)
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault).model_dump(mode="json")
    assert result["outcome"] == "clean"
    path = vault / note_path
    before = path.read_bytes()
    assert note_body(before) == authored_full_note(
        body, guard, tail, section_break=section_break
    )
    if not guard:
        forged = before.replace(body.encode(), (body + "\n\n-->\n").encode(), 1)
    elif damage == "missing":
        # Preserve remaining framing newlines, making the old false expectation
        # match even when all declared hashes/counts are repaired consistently.
        removed = guard if tail == "resources" else guard[:-1]
        forged = before.replace(removed.encode(), b"", 1)
    elif damage == "wrong":
        forged = before.replace(guard.encode(), b"\n\n~~~wrong\n", 1)
    elif damage == "extra":
        forged = before.replace(guard.encode(), (guard * 2).encode(), 1)
    else:
        forged = before.replace(guard.encode(), b"", 1).replace(
            body.encode(), (guard + body).encode(), 1
        )
    assert forged != before
    path.write_bytes(forged)
    record = load_json((vault / "migration-record.json").read_bytes())
    rewrite_record(vault, record, result)
    assert all(
        hashlib.sha256((vault / entry["relative_path"]).read_bytes()).hexdigest()
        == entry["sha256"]
        for entry in result["receipt"]["manifest"]
    )
    with pytest.raises(AssertionError):
        check_vault(source, vault)


@pytest.mark.parametrize(
    "label,guard",
    [
        ("<!-- source label", "\n\n-->\n"),
        ("~~~~label", "\n\n~~~~\n"),
        ("> <!-- source label", ""),
    ],
)
def test_label_boundary_precedes_first_authored_document_without_changing_spans(
    tmp_path, label, guard
):
    body = "α <Value>"
    source, owner, note_path = source_with_tail(
        tmp_path / "source.brz", body, "none", label=label
    )
    inspected = default_workflow().inspect(source)
    assert inspected.outcome == "clean" and inspected.counts.text_adaptations == 1
    edit = next(
        a.text_edit
        for a in inspected.inspection.adaptations
        if a.kind == "literal_text"
    )
    assert (edit.start, edit.end, edit.adapted_start, edit.adapted_end) == (2, 9, 2, 10)
    assert edit.source_digest == hashlib.sha256(body.encode()).hexdigest()
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "clean", result.model_dump_json()
    assert (
        note_body((vault / note_path).read_bytes())
        == ("# Probe\n\n" + label + "\n\n" + guard + "α \\<Value>").encode()
    )
    assert (
        vault
        / ("Attachments/" + identity(owner).replace("-", "") + "/Notes.md.original")
    ).read_bytes() == body.encode()
    check_vault(source, vault)


@pytest.mark.parametrize("block", ["comment", "backtick", "tilde"])
def test_cli_inspection_and_full_guarded_conversion_agree(tmp_path, capsys, block):
    opener, closer = {
        "comment": ("<!-- unfinished", "-->"),
        "backtick": ("```md", "```"),
        "tilde": ("~~~md", "~~~"),
    }[block]
    body = opener + "\r\n<Hidden>"
    source, _, note_path = source_with_tail(tmp_path / "source.brz", body, "all")
    inspected = default_workflow().inspect(source)
    for json_mode in (False, True):
        assert main(["inspect", str(source), *(["--json"] if json_mode else [])]) == 0
        captured = capsys.readouterr()
        assert not captured.err
        if json_mode:
            parsed = json.loads(captured.out)
            assert parsed["receipt"] is None and parsed[
                "counts"
            ] == inspected.counts.model_dump(mode="json")
        vault = tmp_path / ("json" if json_mode else "text")
        assert (
            main(
                ["convert", str(source), str(vault), *(["--json"] if json_mode else [])]
            )
            == 0
        )
        converted = capsys.readouterr()
        assert not converted.err
        assert note_body((vault / note_path).read_bytes()) == authored_full_note(
            body, "\n\n" + closer + "\n", "all"
        )
        summary = check_vault(source, vault)
        if json_mode:
            check_run_result(json.loads(converted.out), vault, summary)

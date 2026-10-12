"""Complete raw audits reject coherently forged active declaration admission."""

import json
import re
from hashlib import sha256
from zipfile import ZipFile

import pytest

from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.cli import main
from tests.application.test_literal_angles_workflow import literal_archive
from tests.application.test_resources_workflow import HOME
from tests.local_acceptance.checker import (
    ROOTS,
    check_run_result,
    check_vault,
    load_json,
)
from tests.local_acceptance.test_checker_v2 import rewrite_record
from tests.support.notes import note_body

FORGED_DECLARATIONS = [
    "<!a",
    " <!z",
    "  <!Z",
    "   <!A",
    "Prose\n<!a\n\ncontinued",
    "> <!a\n> continued",
    "- <!a\n  continued",
    "> - <!a\n>   continued",
    "- > <!a\n  > continued",
    "   <!a>\ncontinued",
    "<!a\n\ncontinued\nend >",
    "> <!a\n\noutside container",
    "- <!a\n\noutside container",
    "-\t<!a",
    "- \t<!a",
    "-\t <!a",
    "1.\t<!a",
    "123.\t<!a",
    "> -\t<!a",
    "- ordinary\n\n\t <!a",
    "Paragraph\n> 10. <!a",
    "> Paragraph\n> > 10. <!a",
    "- Paragraph\n  > 10. <!a",
    "Paragraph\n\n10. <!a",
    # Independently authored conservative reviewed owner limit, not token output
    # from the runtime parser: missing old quote/list prefixes cannot grant
    # supported-source admission to these ordered declaration routes.
    "> Paragraph\n10. <!a",
    "- Paragraph\n10. <!a",
]


@pytest.mark.parametrize("newline", ["\n", "\r", "\r\n"])
@pytest.mark.parametrize("label", ["<!a", "   <!A", "> <!a\n> data", "- <!a\n  data"])
def test_complete_audits_reject_fully_rebound_own_label_declarations(
    tmp_path, label, newline
):
    from tests.application.test_graph_workflow import graph_archive, identity

    forged = label.replace("\n", newline)
    authored = re.sub(r"<![A-Za-z]", "<!_", forged)
    assert len(authored.encode()) == len(forged.encode())
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", 2: "Probe"},
        labels={2: authored},
        notes={2: (b"<Value>", 4)},
    )
    before = source.read_bytes()
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault).model_dump(mode="json")
    assert result["outcome"] == "clean"
    assert len(default_workflow().inspect(source).inspection.documents) == 1
    assert result["counts"]["text_adaptations"] == 1
    assert result["counts"]["source_references"] == 0
    check_run_result(result, vault, check_vault(source, vault))
    note = vault / "Notes/Probe.md"
    assert (
        note_body(note.read_bytes())
        == ("# Probe\n\n" + authored + "\n\n\\<Value>").encode()
    )
    with ZipFile(source) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    assert source.read_bytes() == before
    thoughts = [json.loads(row) for row in parts["thoughts.json"].splitlines()]
    next(row for row in thoughts if row["Id"] == identity(2))["Label"] = forged
    parts["thoughts.json"] = "\n".join(json.dumps(row) for row in thoughts).encode()
    with ZipFile(source, "w") as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    refused = default_workflow().convert(source, tmp_path / "refused")
    assert refused.outcome == "refused" and refused.receipt is None
    assert refused.issues[0].affected == (identity(2),)
    assert not (tmp_path / "refused").exists()
    note.write_bytes(note.read_bytes().replace(authored.encode(), forged.encode(), 1))
    record = load_json((vault / "migration-record.json").read_bytes())
    next(e for e in record["original_evidence"] if e["key"] == "thoughts.json")[
        "records"
    ] = thoughts
    record["source_identity"]["source_sha256"] = sha256(source.read_bytes()).hexdigest()
    pieces = []
    for name in ROOTS:
        raw = parts[name].decode("utf-8-sig")
        rows = (
            [raw]
            if name == "meta.json"
            else [row for row in re.split(r"\r\n|\r|\n", raw) if row.strip(" \t")]
        )
        pieces.append("[" + ",".join(rows) + "]")
    member = identity(2) + "/Notes.md"
    pieces.append(
        json.dumps(
            {"member": member, "length": 7, "sha256": sha256(b"<Value>").hexdigest()}
        )
    )
    record["source_identity"]["snapshot_digest"] = sha256(
        "".join(pieces).encode()
    ).hexdigest()
    rewrite_record(vault, record, result)
    frozen = source.read_bytes()
    with pytest.raises(AssertionError, match="raw-derived active HTML"):
        check_vault(source, vault)
    assert source.read_bytes() == frozen


@pytest.mark.parametrize("newline", ["\n", "\r", "\r\n"])
@pytest.mark.parametrize("unsupported", FORGED_DECLARATIONS)
def test_complete_audits_reject_fully_rebound_declaration_source(
    tmp_path, capsys, unsupported, newline
):
    forged = unsupported.replace("\n", newline)
    # Equal byte lengths and no literal/reference edits keep every count honest.
    authored = re.sub(r"<![A-Za-z]", "<!_", forged)
    assert len(authored.encode()) == len(forged.encode()) and authored != forged
    source = literal_archive(tmp_path / "source.brz", authored.encode())
    vault = tmp_path / "vault"
    assert main(["convert", str(source), str(vault), "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    check_run_result(result, vault, check_vault(source, vault))
    assert (
        note_body((vault / "Home — Entry thought.md").read_bytes())
        == (
            "# Entry thought\n\n"
            + authored
            + "\n\n## Categories\n\n[[Categories.md|Browse categories]]\n"
        ).encode()
    )
    record = load_json((vault / "migration-record.json").read_bytes())
    with ZipFile(source) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    member = HOME + "/Notes.md"
    parts[member] = forged.encode()
    with ZipFile(source, "w") as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    before = source.read_bytes()
    for observed in (
        default_workflow().inspect(source),
        default_workflow().convert(source, tmp_path / "refused-vault"),
    ):
        assert observed.outcome == "refused" and observed.receipt is None
        assert observed.issues[0].code == "unsupported_feature"
    assert not (tmp_path / "refused-vault").exists()

    payload_hash = sha256(forged.encode()).hexdigest()
    note = vault / "Home — Entry thought.md"
    note.write_bytes(note.read_bytes().replace(authored.encode(), forged.encode()))
    asset = next(a for a in record["asset_targets"] if a["original_name"] == "Notes.md")
    (vault / asset["relative_path"]).write_bytes(forged.encode())
    asset["actual_sha256"] = payload_hash
    for evidence in record["original_evidence"]:
        if evidence["key"] == "payload:" + member:
            evidence["records"]["sha256"] = payload_hash
    for item in record["item_targets"]:
        for document in item["documents"]:
            document["text_digest"] = payload_hash
    record["source_identity"]["source_sha256"] = sha256(before).hexdigest()
    # Retained root bytes and payload evidence are independently reconstructed.
    pieces = []
    for name in ROOTS:
        raw = parts[name].decode("utf-8-sig")
        rows = (
            [raw]
            if name == "meta.json"
            else [line for line in re.split(r"\r\n|\r|\n", raw) if line.strip(" \t")]
        )
        pieces.append("[" + ",".join(rows) + "]")
    pieces.append(
        json.dumps(
            {"member": member, "length": len(forged.encode()), "sha256": payload_hash}
        )
    )
    record["source_identity"]["snapshot_digest"] = sha256(
        "".join(pieces).encode()
    ).hexdigest()
    rewrite_record(vault, record, result)
    with pytest.raises(AssertionError, match="raw-derived active HTML"):
        check_vault(source, vault)
    assert source.read_bytes() == before


@pytest.mark.parametrize(
    "prefix,guard",
    [
        ("````\n<!a\n> > data", "\n\n````\n"),
        ("~~~~\n   <!A\n- data", "\n\n~~~~\n"),
        ("<!--\n<!a\n> > data", "\n\n-->\n"),
        ("> ````\n> <!a", ""),
        ("- ~~~~\n  <!a", ""),
    ],
)
@pytest.mark.parametrize("damage", ["missing", "wrong", "extra", "moved"])
@pytest.mark.parametrize("newline", ["\n", "\r", "\r\n"])
def test_protected_declarations_have_only_required_generated_guards(
    tmp_path, prefix, guard, damage, newline
):
    from tests.local_acceptance.test_generated_boundaries import (
        authored_full_note,
        source_with_tail,
    )

    body = prefix.replace("\n", newline)
    source, _, note_path = source_with_tail(tmp_path / "source.brz", body, "all")
    before = source.read_bytes()
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault).model_dump(mode="json")
    assert result["outcome"] == "clean"
    assert (
        result["counts"]["text_adaptations"]
        == result["counts"]["actual_references"]
        == 0
    )
    note = vault / note_path
    correct = note.read_bytes()
    assert note_body(correct) == authored_full_note(body, guard, "all")
    check_run_result(result, vault, check_vault(source, vault))
    if not guard:
        forged = correct.replace(b"\n\n## Resources", b"\n\n-->\n\n## Resources", 1)
    elif damage == "missing":
        forged = correct.replace(guard.encode(), b"", 1)
    elif damage == "wrong":
        forged = correct.replace(guard.encode(), b"\n\nwrong guard\n", 1)
    elif damage == "extra":
        forged = correct.replace(guard.encode(), (guard * 2).encode(), 1)
    else:
        forged = correct.replace(guard.encode(), b"", 1).replace(
            body.encode(), (guard + body).encode(), 1
        )
    assert forged != correct
    note.write_bytes(forged)
    record = load_json((vault / "migration-record.json").read_bytes())
    rewrite_record(vault, record, result)
    with pytest.raises(AssertionError):
        check_run_result(result, vault, check_vault(source, vault))
    assert source.read_bytes() == before

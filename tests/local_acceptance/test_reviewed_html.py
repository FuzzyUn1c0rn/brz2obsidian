"""Raw grammatical non-tags survive complete ZIP/CLI/original audits."""

import hashlib
import json
import re
from copy import deepcopy
from zipfile import ZipFile

import pytest

from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.cli import main
from tests.application.test_graph_workflow import graph_archive
from tests.local_acceptance.checker import check_run_result, check_vault, load_json
from tests.local_acceptance.test_checker_v2 import rewrite_record
from tests.support.notes import note_body


@pytest.mark.parametrize("token", ["<!A>", "<!a>", "<!AB>", "<!A"])
@pytest.mark.parametrize("newline", ["\n", "\r", "\r\n"])
def test_complete_raw_audit_rejects_coherently_forged_declaration_admission(
    tmp_path, capsys, token, newline
):
    from tests.application.test_literal_angles_workflow import literal_archive
    from tests.application.test_resources_workflow import HOME
    from tests.local_acceptance.checker import ROOTS

    # Equal-length non-tag control isolates grammar from lengths and counts.
    if token.endswith(">"):
        authored = (
            "Text <!" + "_" * (len(token) - 3) + "> after." + newline + "Continued."
        )
        forged = "Text " + token + " after." + newline + "Continued."
    else:
        # Type 4 block grammar owns a canonical opener through EOF; inline
        # incomplete lookalikes are independently accepted in NON_TAGS below.
        authored = "Text" + newline + "<!>"
        forged = "Text" + newline + token
    assert len(authored.encode()) == len(forged.encode())
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
    for arguments in (
        ["inspect", str(source), "--json"],
        ["convert", str(source), str(tmp_path / "refused-cli-vault"), "--json"],
    ):
        assert main(arguments) == 1
        assert json.loads(capsys.readouterr().out)["outcome"] == "refused"
    assert not (tmp_path / "refused-vault").exists()
    assert not (tmp_path / "refused-cli-vault").exists()

    # Forge admission, rebinding every source/payload/document/manifest hash.
    # These bytes are authored test corruption, never a converter success.
    payload_hash = hashlib.sha256(forged.encode()).hexdigest()
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
    record["source_identity"]["source_sha256"] = hashlib.sha256(before).hexdigest()
    # Independently serialize the fixture's complete raw retained population.
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
    record["source_identity"]["snapshot_digest"] = hashlib.sha256(
        "".join(pieces).encode()
    ).hexdigest()
    rewrite_record(vault, record, result)
    with pytest.raises(AssertionError, match="active HTML"):
        # Raw-source rejection precedes any result audit for this corruption.
        check_vault(source, vault)
    assert source.read_bytes() == before


NON_TAGS = [
    "Text <sys/header.h> <Value>",
    "Text <sys/other.h> <Value>",
    'Text <I", example\\_value\n\n## Next\n\n`<Hidden>`\n\nend > <Value>',
    r"Text <SESSION\_KEY> <Value>",
    "Text <!a\n\n<Value>",
    "Text <!_> <!1> <!é> <Value>",
    r"Text \<!a> <Value>",
    "`<!a>` <Value>",
    "<!-- <!a> -->\n<Value>",
    "```\n<!a\n> > prompt\n```\n<Value>",
    "~~~\n<!a>\n~~~\n<Value>",
    "    <!a\n\n<Value>",
]


@pytest.mark.parametrize("newline", ["\n", "\r", "\r\n"])
@pytest.mark.parametrize("authored", NON_TAGS)
def test_raw_non_tags_preserve_complete_bytes_and_one_genuine_literal(
    tmp_path, capsys, authored, newline
):
    body = authored.replace("\n", newline)
    expected = body.replace("<Value>", "\\<Value>")
    source = graph_archive(
        tmp_path / "source.brz", {1: "Home", 2: "Probe"}, notes={2: (body.encode(), 4)}
    )
    before = source.read_bytes()
    inspected = default_workflow().inspect(source)
    assert inspected.outcome == "clean"
    assert inspected.counts.text_adaptations == 1
    document = inspected.inspection.documents[0]
    edit = document.text_adaptations[0]
    start = body.index("<Value>")
    assert (edit.start, edit.end, edit.before, edit.after) == (
        start,
        start + 7,
        "<Value>",
        "\\<Value>",
    )
    assert (edit.adapted_start, edit.adapted_end) == (start, start + 8)
    assert edit.source_digest == hashlib.sha256(body.encode()).hexdigest()
    assert document.text_digest == hashlib.sha256(expected.encode()).hexdigest()
    assert document.references == ()
    assert main(["inspect", str(source), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["counts"]["text_adaptations"] == 1
    vault = tmp_path / "vault"
    assert main(["convert", str(source), str(vault), "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert (
        note_body((vault / "Notes/Probe.md").read_bytes())
        == ("# Probe\n\n" + expected).encode()
    )
    assert (
        vault / "Attachments/00000000000000000000000000000002/Notes.md.original"
    ).read_bytes() == body.encode()
    check_run_result(result, vault, check_vault(source, vault))
    assert source.read_bytes() == before


@pytest.mark.parametrize("closed", [False, True])
@pytest.mark.parametrize("block", ["```", "~~~"])
@pytest.mark.parametrize("damage", [None, "missing", "wrong", "extra", "moved"])
def test_code_owned_prompt_text_preserves_live_references_and_framing_corruptions(
    tmp_path, closed, block, damage
):
    from tests.local_acceptance.test_generated_boundaries import (
        authored_full_note,
        source_with_tail,
    )
    from tests.support.combined_collection import compact

    phrase = "[Live](brain://" + compact(3) + "/ignored)"
    body = block + "\n> > prompt\n- literal data\n<Hidden>"
    if closed:
        body += "\n" + block + "\n\n<Value> " + phrase
    guard = "" if closed else "\n\n" + block + "\n"
    expected_body = body.replace("<Value>", "\\<Value>").replace(
        phrase, "[[Notes/Live.md|Live]]"
    )
    source, _, note_path = source_with_tail(tmp_path / "source.brz", body, "all")
    before = source.read_bytes()
    inspected = default_workflow().inspect(source)
    assert inspected.outcome == "clean"
    assert (
        inspected.counts.text_adaptations
        == inspected.counts.source_references
        == int(closed)
    )
    document = inspected.inspection.documents[0]
    assert (
        document.text_digest
        == hashlib.sha256(body.replace("<Value>", "\\<Value>").encode()).hexdigest()
    )
    if closed:
        reference = document.references[0]
        start = body.index(phrase) + 1
        assert (reference.start, reference.end) == (start, start + len(phrase))
        assert (
            reference.expected_original == phrase and reference.display_text == "Live"
        )
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault).model_dump(mode="json")
    note = vault / note_path
    assert note_body(note.read_bytes()) == authored_full_note(
        expected_body, guard, "all"
    )
    check_run_result(result, vault, check_vault(source, vault))
    if damage is not None:
        data = note.read_bytes()
        framing = ("\n\n" + block + "\n").encode()
        generated = b"\n\n## Resources"
        if closed:
            authored_closer = ("\n" + block + "\n\n").encode()
            if damage == "missing":
                data = data.replace(authored_closer, b"\n\n", 1)
            elif damage == "wrong":
                data = data.replace(authored_closer, b"\nwrong fence\n\n", 1)
            elif damage == "extra":
                data = data.replace(generated, framing + generated, 1)
            else:
                data = data.replace(authored_closer, b"\n\n", 1).replace(
                    generated, framing + generated, 1
                )
        elif damage == "missing":
            data = data.replace(framing, b"", 1)
        elif damage == "wrong":
            data = data.replace(framing, b"\n\nwrong fence\n", 1)
        elif damage == "extra":
            data = data.replace(framing, framing + framing, 1)
        else:
            data = data.replace(framing, b"", 1).replace(
                b"## Children", framing + b"## Children", 1
            )
        assert data != note.read_bytes()
        note.write_bytes(data)
        record = load_json((vault / "migration-record.json").read_bytes())
        rewrite_record(vault, record, result)
        with pytest.raises(AssertionError):
            check_run_result(result, vault, check_vault(source, vault))
    assert source.read_bytes() == before


@pytest.mark.parametrize("block", ["```", "~~~", "<!--"])
@pytest.mark.parametrize("container", ["", "> ", "- "])
@pytest.mark.parametrize("newline", ["\n", "\r", "\r\n"])
def test_protected_leaf_owns_container_looking_text_and_exact_generated_tail(
    tmp_path, capsys, block, container, newline
):
    from tests.local_acceptance.test_generated_boundaries import (
        authored_full_note,
        source_with_tail,
    )

    continuation = "  " if container == "- " else container
    closer = "-->" if block == "<!--" else block
    lines = [
        container + block,
        continuation + "> > prompt",
        continuation + "- literal data",
        continuation + "<Hidden>",
        continuation + closer,
        "",
        "<Value>",
    ]
    body = newline.join(lines)
    expected_body = body.replace("<Value>", "\\<Value>")
    source, owner, note_path = source_with_tail(tmp_path / "source.brz", body, "all")
    before = source.read_bytes()
    inspected = default_workflow().inspect(source)
    assert inspected.outcome == "clean" and inspected.counts.text_adaptations == 1
    assert inspected.counts.source_references == inspected.counts.source_gaps == 0
    start = body.index("<Value>")
    edit = inspected.inspection.documents[0].text_adaptations[0]
    assert (edit.start, edit.end, edit.adapted_start, edit.adapted_end) == (
        start,
        start + 7,
        start,
        start + 8,
    )
    assert edit.source_digest == hashlib.sha256(body.encode()).hexdigest()
    assert main(["inspect", str(source), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["receipt"] is None
    vault = tmp_path / "vault"
    assert main(["convert", str(source), str(vault), "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert note_body((vault / note_path).read_bytes()) == authored_full_note(
        expected_body, "", "all"
    )
    original = vault / ("Attachments/" + str(owner).zfill(32) + "/Notes.md.original")
    assert original.read_bytes() == body.encode()
    check_run_result(result, vault, check_vault(source, vault))
    assert source.read_bytes() == before


@pytest.mark.parametrize(
    "damage",
    [
        "display",
        "identity",
        "owner",
        "location",
        "uri",
        "role",
        "merged",
        "fake_copy",
        "resource_label",
    ],
)
def test_raw_external_fallback_rejects_coherently_rehashed_false_facts(
    tmp_path, damage
):
    from tests.application.test_resources_workflow import resource_archive

    source = resource_archive(
        tmp_path / "source.brz",
        [
            ({"Type": 2, "Location": r"C:\Offline\lesson.pdf"}, None),
            ({"Type": 2, "Name": "", "Location": r"D:\Other\lesson.pdf"}, None),
        ],
    )
    before = source.read_bytes()
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault).model_dump(mode="json")
    check_run_result(result, vault, check_vault(source, vault))
    record = load_json((vault / "migration-record.json").read_bytes())
    external = [a for a in record["asset_targets"] if a["availability"] == "external"]
    first, second = external
    note = vault / "Home — Entry thought.md"
    if damage == "display":
        first["display_name"] = "forged.pdf"
        note.write_bytes(note.read_bytes().replace(b"[lesson.pdf]", b"[forged.pdf]", 1))
    elif damage == "identity":
        first["asset_id"] = "aaaaaaaa-0000-4000-8000-000000000099"
    elif damage == "owner":
        first["owner"] = "aaaaaaaa-0000-4000-8000-000000000099"
    elif damage == "location":
        first["original_name"] = r"C:\Wrong\lesson.pdf"
        evidence = next(
            e for e in record["original_evidence"] if e["key"] == "attachments.json"
        )
        next(a for a in evidence["records"] if a["Id"] == first["asset_id"])[
            "Location"
        ] = first["original_name"]
    elif damage == "uri":
        old = first["external_uri"]
        first["external_uri"] = first["resource_link"] = "file:///C:/Wrong/lesson.pdf"
        note.write_bytes(
            note.read_bytes().replace(old.encode(), first["external_uri"].encode())
        )
    elif damage == "role":
        first["role"] = "directory"
    elif damage == "merged":
        record["asset_targets"].remove(second)
        note.write_bytes(
            note.read_bytes().replace(
                b"- [lesson.pdf](<file:///D:/Other/lesson.pdf>)\n", b""
            )
        )
    elif damage == "fake_copy":
        path = vault / "Attachments/forged.pdf"
        path.write_bytes(b"invented external target bytes")
        first.update(
            availability="present",
            relative_path="Attachments/forged.pdf",
            actual_length=path.stat().st_size,
            actual_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        record["counts"]["planned_assets"] += 1
        record["counts"]["present_assets"] += 1
    else:
        note.write_bytes(
            note.read_bytes().replace(b"[lesson.pdf]", b"[wrong-label]", 1)
        )
    rewrite_record(vault, record, result)
    with pytest.raises(AssertionError):
        check_run_result(result, vault, check_vault(source, vault))
    assert source.read_bytes() == before


@pytest.mark.parametrize(
    "damage", ["non_tag", "code", "escaped", "missing_edit", "extra_edit", "moved_edit"]
)
def test_raw_authored_prose_and_edit_population_reject_coherent_forgery(
    tmp_path, damage
):
    body = r"Text <sys/header.h> `<Code>` \<Escaped> <Value>"
    source = graph_archive(
        tmp_path / "source.brz", {1: "Home", 2: "Probe"}, notes={2: (body.encode(), 4)}
    )
    before = source.read_bytes()
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault).model_dump(mode="json")
    check_run_result(result, vault, check_vault(source, vault))
    record = load_json((vault / "migration-record.json").read_bytes())
    document = next(d for t in record["item_targets"] for d in t["documents"])
    adaptation = next(a for a in record["adaptations"] if a["kind"] == "literal_text")
    note = vault / "Notes/Probe.md"
    if damage in {"non_tag", "code", "escaped"}:
        token = {
            "non_tag": b"<sys/header.h>",
            "code": b"<Code>",
            "escaped": b"<Escaped>",
        }[damage]
        note.write_bytes(note.read_bytes().replace(token, b"<Changed>", 1))
    elif damage == "missing_edit":
        document["text_adaptations"] = []
        record["adaptations"].remove(adaptation)
        record["counts"]["text_adaptations"] = 0
        note.write_bytes(note.read_bytes().replace(b"\\<Value>", b"<Value>"))
        document["text_digest"] = hashlib.sha256(body.encode()).hexdigest()
    elif damage == "extra_edit":
        start = body.index("<sys/header.h>")
        extra = dict(
            document["text_adaptations"][0],
            start=start,
            end=start + 14,
            before="<sys/header.h>",
            after="\\<sys/header.h>",
            adapted_start=start,
            adapted_end=start + 15,
        )
        document["text_adaptations"].insert(0, extra)
        second = document["text_adaptations"][1]
        second["adapted_start"] += 1
        second["adapted_end"] += 1
        adaptation["text_edit"] = second
        forged = deepcopy(adaptation)
        forged.update(affected="text:" + document["key"] + ":extra", text_edit=extra)
        record["adaptations"].append(forged)
        record["counts"]["text_adaptations"] += 1
        note.write_bytes(
            note.read_bytes().replace(b"<sys/header.h>", b"\\<sys/header.h>")
        )
        document["text_digest"] = hashlib.sha256(
            body.replace("<Value>", "\\<Value>")
            .replace("<sys/header.h>", "\\<sys/header.h>")
            .encode()
        ).hexdigest()
    else:
        edit = document["text_adaptations"][0]
        edit["start"] += 1
        edit["end"] += 1
        adaptation["text_edit"] = edit
    rewrite_record(vault, record, result)
    with pytest.raises(AssertionError):
        check_run_result(result, vault, check_vault(source, vault))
    assert source.read_bytes() == before

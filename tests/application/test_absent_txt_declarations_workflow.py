"""Repeated absent TXT declarations retain separate facts at public boundaries."""

import json

import pytest

from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.cli import main
from tests.application.test_verified_coverage import (
    OWNER,
    PDF,
    TXT,
    add_attachment,
    change_record,
    source_parts,
    write_source,
)

THIRD = "88888888-8888-4888-8888-888888888888"
INTACT_PDF = "99999999-9999-4999-8999-999999999999"
PDF_BYTES = b"%PDF-1.4 preserved same-owner resource"
RULE = "thebrain-format5/absent-txt/v1"


def repeated_parts(tmp_path, count=2):
    parts = source_parts(tmp_path)
    for key, length in zip((TXT, PDF, THIRD)[:count], (17, 29, 41)):
        add_attachment(parts, key, 15, "shared.txt", declared=length, state=2)
    add_attachment(parts, INTACT_PDF, 1, "manual.pdf", PDF_BYTES)
    return parts


def test_distinct_absent_txt_declarations_are_individually_inspected_and_preserved(
    tmp_path,
):
    source = write_source(tmp_path, repeated_parts(tmp_path))
    original = source.read_bytes()
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    assert inspected.outcome == "warnings", inspected.issues
    assert {issue.affected: issue.rule_id for issue in inspected.issues} == {
        (TXT,): RULE,
        (PDF,): RULE,
    }
    vault = tmp_path / "vault"
    converted = workflow.convert(source, vault)
    assert converted.outcome == "warnings", converted.issues
    assert converted.issues == inspected.issues
    assert converted.receipt.published and converted.receipt.verified
    assert converted.counts.actual_assets == 2
    assert converted.counts.source_references == 0
    assert not list(vault.rglob("*.txt"))
    record = json.loads((vault / "migration-record.json").read_bytes())
    absent = {
        a["asset_id"]: a for a in record["asset_targets"] if a["asset_id"] in {TXT, PDF}
    }
    assert set(absent) == {TXT, PDF}
    for key, length, pointer in (
        (TXT, 17, "attachments.json:1"),
        (PDF, 29, "attachments.json:2"),
    ):
        target = absent[key]
        assert target["relative_path"] is None and target["resource_link"] is None
        assert target["availability"] == "absent"
        assert target["actual_length"] is None and target["actual_sha256"] is None
        finding = target["source_findings"][0]
        assert finding["affected"] == [key] and finding["rule_id"] == RULE
        assert finding["evidence"] == [pointer, "meta.json", "attachments.json:3"]
        observed = json.loads(finding["observed_json"])
        assert observed["declared_length"] == length and observed["present"] is False
        assert observed["owner"] == OWNER and observed["filename"] == "shared.txt"
        assert observed["intact_same_owner_pdfs"] == [INTACT_PDF]
    assert (vault / "Attachments/22222222/manual.pdf").read_bytes() == PDF_BYTES
    evidence = next(
        e for e in record["original_evidence"] if e["key"] == "attachments.json"
    )
    assert {r["Id"] for r in evidence["records"]} >= {TXT, PDF}
    accounting = {entry["identity"] for entry in record["source_accounting"]["entries"]}
    assert {"attachments.json:1", "attachments.json:2"} <= accounting
    assert source.read_bytes() == original


def test_three_declarations_survive_repeat_root_and_record_reordering(tmp_path):
    parts = repeated_parts(tmp_path, 3)
    source = write_source(tmp_path, parts)
    original = source.read_bytes()
    workflow = default_workflow()
    results = [
        workflow.convert(source, tmp_path / name) for name in ("first", "repeat")
    ]
    assert source.read_bytes() == original
    for name in ("thoughts.json", "attachments.json", "meta.json"):
        parts[name] = b"\n".join(reversed(parts[name].splitlines()))
    reordered_source = write_source(tmp_path, dict(reversed(list(parts.items()))))
    reordered_bytes = reordered_source.read_bytes()
    results.append(workflow.convert(reordered_source, tmp_path / "reordered"))
    for result in results:
        assert result.outcome == "warnings", result.issues
        assert len(result.issues) == 3
        assert {issue.affected for issue in result.issues} == {(TXT,), (PDF,), (THIRD,)}
        assert result.counts.actual_assets == 2 and result.counts.source_references == 0
        assert result.receipt.published and result.receipt.verified
    for name in ("first", "repeat", "reordered"):
        vault = tmp_path / name
        record = json.loads((vault / "migration-record.json").read_bytes())
        assert {
            a["asset_id"]: json.loads(a["source_findings"][0]["observed_json"])[
                "declared_length"
            ]
            for a in record["asset_targets"]
            if a["source_findings"]
        } == {TXT: 17, PDF: 29, THIRD: 41}
        assert not list(vault.rglob("*.txt"))
        assert (vault / "Attachments/22222222/manual.pdf").read_bytes() == PDF_BYTES
    for relative in ("Home — Entry thought.md", "MIGRATION REPORT.md"):
        assert (tmp_path / "first" / relative).read_bytes() == (
            tmp_path / "repeat" / relative
        ).read_bytes()
        assert (tmp_path / "first" / relative).read_bytes() == (
            tmp_path / "reordered" / relative
        ).read_bytes()
    assert reordered_source.read_bytes() == reordered_bytes


@pytest.mark.parametrize("reverse", [False, True], ids=["bad-last", "bad-first"])
@pytest.mark.parametrize(
    "mutation",
    [
        "present",
        "state1",
        "state3",
        "unknown-state",
        "bool-state",
        "no-state",
        "file-role",
        "note-role",
        "unsupported-role",
        "source-type",
        "bool-source",
        "note-type",
        "icon",
        "special",
        "unknown-flag",
        "flag-scalar",
        "custom-type",
        "zero",
        "negative",
        "bool-length",
        "text-length",
        "fractional-length",
        "non-txt",
        "unsafe-path",
        "ambiguous-path",
        "duplicate-id",
        "wrong-brain",
        "unknown-owner",
        "invalid-name",
    ],
)
def test_one_ineligible_declaration_refuses_entire_group_in_both_orders(
    tmp_path, mutation, reverse
):
    parts = repeated_parts(tmp_path, 3)
    changes = {
        "file-role": {"Type": 1},
        "note-role": {"Type": 1, "NoteType": 4},
        "unsupported-role": {"Type": 99},
        "source-type": {"SourceType": 1},
        "bool-source": {"SourceType": True},
        "note-type": {"NoteType": 4},
        "icon": {"IsIcon": True},
        "special": {"IsBrainAttachment": True},
        "unknown-flag": {"IsUnreviewedRole": True},
        "flag-scalar": {"IsIcon": 0},
        "custom-type": {"TypeId": THIRD},
        "zero": {"DataLength": 0},
        "negative": {"DataLength": -1},
        "bool-length": {"DataLength": True},
        "text-length": {"DataLength": "17"},
        "fractional-length": {"DataLength": 17.5},
        "duplicate-id": {"Id": TXT},
        "wrong-brain": {"BrainId": THIRD},
        "unknown-owner": {"SourceId": THIRD},
        "invalid-name": {"Name": False},
    }
    if mutation in changes:
        change_record(parts, PDF, **changes[mutation])
    if mutation in {"non-txt", "unsafe-path", "ambiguous-path"}:
        location = {
            "non-txt": "shared.bin",
            "unsafe-path": "../shared.txt",
            "ambiguous-path": "./shared.txt",
        }[mutation]
        for key in (TXT, PDF, THIRD):
            change_record(parts, key, Location=location)
    if mutation == "present":
        parts[OWNER + "/shared.txt"] = b"physical bytes despite state 2"
    if mutation in {"state1", "state3", "unknown-state", "bool-state", "no-state"}:
        meta = json.loads(parts["meta.json"])
        meta["AttachmentFileStates"].pop(PDF)
        state = {
            "state1": 1,
            "state3": 3,
            "unknown-state": 99,
            "bool-state": True,
            "no-state": None,
        }[mutation]
        if state is not None:
            meta["AttachmentFileStates"][PDF] = state
        parts["meta.json"] = json.dumps(meta).encode()
    if reverse:
        parts["attachments.json"] = b"\n".join(
            reversed(parts["attachments.json"].splitlines())
        )
    source = write_source(tmp_path, parts)
    original = source.read_bytes()
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    caller = tmp_path / "caller"
    caller.mkdir()
    (caller / "sentinel.bin").write_bytes(b"caller-owned bytes")
    for destination in (tmp_path / "fresh", caller):
        converted = workflow.convert(source, destination)
        assert inspected.outcome == converted.outcome == "refused"
        assert converted.issues == inspected.issues
        assert converted.receipt is None
    assert not (tmp_path / "fresh").exists()
    assert {p.name: p.read_bytes() for p in caller.iterdir()} == {
        "sentinel.bin": b"caller-owned bytes"
    }
    assert source.read_bytes() == original


@pytest.mark.parametrize(
    "kind,note_type,prefix",
    [
        (1, 0, ""),
        (1, 4, ""),
        (5, 0, ".data/"),
        (12, 0, ".data/md-images/"),
        (99, 0, ""),
    ],
)
@pytest.mark.parametrize("present", [False, True])
def test_duplicate_non_txt_roles_remain_ambiguous(
    tmp_path, kind, note_type, prefix, present
):
    parts = repeated_parts(tmp_path)
    for key in (TXT, PDF):
        change_record(parts, key, Type=kind, NoteType=note_type, IsIcon=kind == 5)
    if present:
        parts[OWNER + "/" + prefix + "shared.txt"] = b"present competing payload"
    source = write_source(tmp_path, parts)
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "refused" and result.issues[0].code == "invalid_source"
    assert result.receipt is None and not (tmp_path / "vault").exists()


def test_cli_json_and_text_report_each_absent_declaration(tmp_path, capsys):
    source = write_source(tmp_path, repeated_parts(tmp_path, 3))
    expected = default_workflow().inspect(source)
    assert main(["inspect", str(source), "--json"]) == 2
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out) == expected.model_dump(mode="json", by_alias=True)
    assert main(["convert", str(source), str(tmp_path / "vault"), "--json"]) == 2
    converted = json.loads(capsys.readouterr().out)
    assert converted["issues"] == expected.model_dump(mode="json")["issues"]
    assert converted["receipt"]["published"] and converted["receipt"]["verified"]
    assert main(["inspect", str(source)]) == 2
    text = capsys.readouterr().out
    assert text.count("approved_source_gap") == 3
    for length in (17, 29, 41):
        assert f'"declared_length": {length}' in text


def test_duplicate_txt_does_not_bypass_same_owner_intact_pdf_requirement(tmp_path):
    parts = repeated_parts(tmp_path)
    records = [
        json.loads(line)
        for line in parts["attachments.json"].splitlines()
        if line.strip()
    ]
    parts["attachments.json"] = b"\n".join(
        json.dumps(r).encode() for r in records if r["Id"] != INTACT_PDF
    )
    del parts[OWNER + "/manual.pdf"]
    meta = json.loads(parts["meta.json"])
    del meta["AttachmentFileStates"][INTACT_PDF]
    parts["meta.json"] = json.dumps(meta).encode()
    source = write_source(tmp_path, parts)
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "refused"
    assert result.issues[0].code == "missing_required_payload"
    assert result.receipt is None and not (tmp_path / "vault").exists()


@pytest.mark.parametrize("mutation", ["eligible", "ineligible", "present"])
@pytest.mark.parametrize("reverse", [False, True])
def test_excluded_duplicate_txt_group_remains_private_and_globally_trusted(
    tmp_path, mutation, reverse
):
    parts = repeated_parts(tmp_path)
    private_owner = THIRD
    thought = json.loads(parts["thoughts.json"])
    thought.update(
        Id=private_owner, Name="Private owner", ForgottenDateTime="2026-10-01"
    )
    parts["thoughts.json"] += b"\n" + json.dumps(thought).encode()
    for key in (TXT, PDF, INTACT_PDF):
        change_record(parts, key, SourceId=private_owner)
    # Exclusion needs no per-role PDF verification: its absent-resource facts
    # and unsupported single role are ignored after global ownership proof.
    del parts[OWNER + "/manual.pdf"]
    change_record(parts, INTACT_PDF, Type=99, SourceType=99, NoteType=99)
    if mutation == "ineligible":
        change_record(parts, TXT, SourceType=99)
    if mutation == "present":
        parts[private_owner + "/shared.txt"] = b"excluded physical payload"
    if reverse:
        parts["attachments.json"] = b"\n".join(
            reversed(parts["attachments.json"].splitlines())
        )
    source = write_source(tmp_path, parts)
    original = source.read_bytes()
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    converted = workflow.convert(source, tmp_path / "vault")
    assert (
        inspected.outcome
        == converted.outcome
        == ("clean" if mutation == "eligible" else "refused")
    )
    for result in (inspected, converted):
        for private in (
            private_owner,
            TXT,
            PDF,
            INTACT_PDF,
            "Private owner",
            "shared.txt",
            "manual.pdf",
        ):
            assert private not in result.model_dump_json()
    if mutation != "eligible":
        assert not (tmp_path / "vault").exists() and converted.receipt is None
    else:
        assert (
            converted.counts.source_items == 1 and converted.counts.actual_assets == 1
        )
        output = b"\n".join(
            p.read_bytes() for p in (tmp_path / "vault").rglob("*") if p.is_file()
        )
        for private in (
            private_owner,
            TXT,
            PDF,
            INTACT_PDF,
            "Private owner",
            "shared.txt",
            "manual.pdf",
        ):
            assert private.encode() not in output
        assert converted.receipt.published and converted.receipt.verified
    assert source.read_bytes() == original

"""Reviewed zero-length declarations through real inspect/convert boundaries."""

import hashlib
import json

import pytest

from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.cli import main
from brz2obsidian.contracts import MigrationRefused
from brz2obsidian.core import analyze, plan
from brz2obsidian.sources.thebrain import BrzSourceModule
from brz2obsidian.sources.thebrain.profile import BRZ_POLICY
from tests.application.test_verified_coverage import (
    ICON,
    OWNER,
    PDF,
    TXT,
    add_attachment,
    change_record,
    source_parts,
    write_source,
)

PDF_BYTES = b"%PDF-1.4 zero-length rule control\r\n%%EOF\r\n"
RULE = "thebrain-format5/zero-length-absent-txt/v1"
TXT_NAME = PDF + ".txt"
OTHER = "88888888-8888-4888-8888-888888888888"


def zero_parts(tmp_path):
    parts = source_parts(tmp_path)
    add_attachment(parts, PDF, 1, "manual.pdf", PDF_BYTES)
    add_attachment(parts, TXT, 15, TXT_NAME, declared=0, state=2)
    return parts


def test_identity_associated_zero_length_txt_is_individually_evidenced_and_published(
    tmp_path,
):
    parts = zero_parts(tmp_path)
    source = write_source(tmp_path, parts)
    original_source = source.read_bytes()
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    assert inspected.outcome == "warnings", inspected.issues
    assert inspected.receipt is None and inspected.counts.actual_assets is None
    issue = inspected.issues[0]
    assert (issue.code, issue.severity, issue.rule_id, issue.affected) == (
        "approved_source_gap",
        "warning",
        RULE,
        (TXT,),
    )
    observed = json.loads(issue.message.split(" Observed: ", 1)[1])
    assert observed == {
        "owner": OWNER,
        "filename": TXT_NAME,
        "declared_length": 0,
        "state": 2,
        "present": False,
        "filename_stem": PDF,
        "pdf_attachment_id": PDF,
        "pdf": {
            "owner": OWNER,
            "filename": "manual.pdf",
            "source_type": 2,
            "type": 1,
            "note_type": 0,
            "state": 1,
            "member": OWNER + "/manual.pdf",
            "declared_length": 42,
            "actual_length": 42,
            "actual_sha256": hashlib.sha256(PDF_BYTES).hexdigest(),
            "crc_valid": True,
        },
    }
    assert set(issue.evidence) == {
        "attachments.json:2",
        "attachments.json:1",
        "meta.json",
        "payload:" + OWNER + "/manual.pdf",
    }
    absent = next(t for t in inspected.inspection.asset_targets if t.asset_id == TXT)
    assert absent.relative_path is None and absent.resource_link is None
    vault = tmp_path / "vault"
    result = workflow.convert(source, vault)
    assert result.outcome == "warnings" and result.issues == inspected.issues
    assert result.receipt.published and result.receipt.verified
    assert (vault / "Attachments/22222222/manual.pdf").read_bytes() == PDF_BYTES
    note = (vault / "Home — Entry thought.md").read_text()
    assert "Absent source file: " + TXT_NAME in note
    assert TXT_NAME + "|" not in note and not list(vault.rglob("*.txt"))
    record = json.loads((vault / "migration-record.json").read_bytes())
    asset = next(a for a in record["asset_targets"] if a["asset_id"] == TXT)
    assert json.loads(asset["source_findings"][0]["observed_json"]) == observed
    originals = next(
        e["records"]
        for e in record["original_evidence"]
        if e["key"] == "attachments.json"
    )
    assert originals == [
        json.loads(line)
        for line in parts["attachments.json"].splitlines()
        if line.strip()
    ]
    assert source.read_bytes() == original_source


def test_pdf_search_limit_is_reported_once_outside_individual_source_gaps(tmp_path):
    parts = zero_parts(tmp_path)
    other_pdf = "88888888-8888-4888-8888-888888888888"
    other_txt = "99999999-9999-4999-8999-999999999999"
    add_attachment(parts, other_pdf, 1, "second.pdf", PDF_BYTES)
    add_attachment(parts, other_txt, 15, other_pdf + ".txt", declared=0, state=2)
    result = default_workflow().convert(
        write_source(tmp_path, parts), tmp_path / "vault"
    )
    assert result.outcome == "warnings" and len(result.issues) == 2
    report = (tmp_path / "vault/MIGRATION REPORT.md").read_text()
    assert report.count("Vault Search does not search PDF body text") == 1
    limit, warnings = report.split("## Source warnings", 1)
    assert "PDF files are preserved and can be opened in Obsidian" in limit
    assert "Vault Search" not in warnings
    assert {issue.affected for issue in result.issues} == {(TXT,), (other_txt,)}
    assert all(
        "cache" not in issue.message and "extraction failure" not in issue.message
        for issue in result.issues
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "txt_source_type",
        "txt_kind",
        "txt_note_type",
        "txt_extension",
        "txt_stem",
        "txt_filename_stem",
        "txt_compact_stem",
        "txt_negative_length",
        "txt_bool_length",
        "txt_float_length",
        "txt_state_one",
        "txt_state_missing",
        "txt_state_invalid",
        "txt_present_empty",
        "txt_present_nonempty",
        "txt_owner_missing",
        "txt_owner_elsewhere",
        "txt_brain",
        "txt_icon",
        "txt_special",
        "txt_unsafe_path",
        "txt_duplicate_id",
        "pdf_source_type",
        "pdf_icon_role",
        "pdf_image_role",
        "pdf_note_role",
        "pdf_note_type",
        "pdf_extension",
        "pdf_absent",
        "pdf_state_two",
        "pdf_state_missing",
        "pdf_length",
        "pdf_crc",
        "pdf_owner_elsewhere",
        "pdf_identity_changed",
        "pdf_duplicate_id",
        "pdf_duplicate_payload",
        "combined_state_stem",
        "combined_owner_role",
        "combined_length_crc",
    ],
)
def test_each_zero_length_rule_conjunct_refuses_near_misses_without_publication(
    tmp_path, mutation
):
    parts = zero_parts(tmp_path)
    txt_updates = {
        "txt_source_type": {"SourceType": 1},
        "txt_kind": {"Type": 1},
        "txt_note_type": {"NoteType": 4},
        "txt_extension": {"Location": PDF + ".bin"},
        "txt_stem": {"Location": "paper.txt"},
        "txt_filename_stem": {"Location": "manual.txt"},
        "txt_compact_stem": {"Location": PDF.replace("-", "") + ".txt"},
        "txt_negative_length": {"DataLength": -1},
        "txt_bool_length": {"DataLength": False},
        "txt_float_length": {"DataLength": 0.0},
        "txt_owner_missing": {"SourceId": OTHER},
        "txt_brain": {"BrainId": OTHER},
        "txt_icon": {"IsIcon": True},
        "txt_special": {"IsWallpaper": True},
        "txt_unsafe_path": {"Location": "../" + TXT_NAME},
    }
    pdf_updates = {
        "pdf_source_type": {"SourceType": 1},
        "pdf_note_type": {"NoteType": 7},
        "pdf_length": {"DataLength": 43},
        "pdf_identity_changed": {"Id": OTHER},
    }
    if mutation in txt_updates:
        change_record(parts, TXT, **txt_updates[mutation])
    elif mutation in pdf_updates:
        change_record(parts, PDF, **pdf_updates[mutation])
        if mutation == "pdf_identity_changed":
            meta = json.loads(parts["meta.json"])
            meta["AttachmentFileStates"][OTHER] = meta["AttachmentFileStates"].pop(PDF)
            parts["meta.json"] = json.dumps(meta).encode()
    elif mutation in {
        "txt_state_one",
        "txt_state_missing",
        "txt_state_invalid",
        "pdf_state_two",
        "pdf_state_missing",
        "combined_state_stem",
    }:
        meta = json.loads(parts["meta.json"])
        key = PDF if mutation.startswith("pdf") else TXT
        if mutation.endswith("missing"):
            del meta["AttachmentFileStates"][key]
        else:
            meta["AttachmentFileStates"][key] = (
                0 if mutation.endswith("invalid") else (2 if key == PDF else 1)
            )
        parts["meta.json"] = json.dumps(meta).encode()
        if mutation == "combined_state_stem":
            change_record(parts, TXT, Location="paper.txt")
    elif mutation in {"txt_present_empty", "txt_present_nonempty"}:
        parts[OWNER + "/" + TXT_NAME] = (
            b""
            if mutation.endswith("empty") and not mutation.endswith("nonempty")
            else b"unexpected bytes"
        )
    elif mutation in {
        "txt_owner_elsewhere",
        "pdf_owner_elsewhere",
        "combined_owner_role",
    }:
        thought = json.loads(parts["thoughts.json"])
        thought.update(Id=OTHER, Name="Other owner")
        parts["thoughts.json"] += b"\n" + json.dumps(thought).encode()
        key = TXT if mutation.startswith("txt") else PDF
        change_record(parts, key, SourceId=OTHER)
        if key == PDF:
            parts[OTHER + "/manual.pdf"] = parts.pop(OWNER + "/manual.pdf")
        if mutation == "combined_owner_role":
            change_record(parts, TXT, NoteType=4)
    elif mutation in {"pdf_icon_role", "pdf_image_role", "pdf_note_role"}:
        kind = {"pdf_icon_role": 5, "pdf_image_role": 12, "pdf_note_role": 1}[mutation]
        change_record(
            parts,
            PDF,
            Type=kind,
            IsIcon=kind == 5,
            NoteType=4 if mutation == "pdf_note_role" else 0,
        )
        if kind != 1:
            prefix = ".data/" if kind == 5 else ".data/md-images/"
            parts[OWNER + "/" + prefix + "manual.pdf"] = parts.pop(
                OWNER + "/manual.pdf"
            )
    elif mutation == "pdf_extension":
        change_record(parts, PDF, Location="manual.bin")
        parts[OWNER + "/manual.bin"] = parts.pop(OWNER + "/manual.pdf")
    elif mutation == "pdf_absent":
        del parts[OWNER + "/manual.pdf"]
    elif mutation in {"txt_duplicate_id", "pdf_duplicate_id", "pdf_duplicate_payload"}:
        key = TXT if mutation.startswith("txt") else PDF
        duplicate = next(
            json.loads(line)
            for line in parts["attachments.json"].splitlines()
            if line.strip() and json.loads(line)["Id"] == key
        )
        if mutation == "pdf_duplicate_payload":
            duplicate["Id"] = OTHER
            meta = json.loads(parts["meta.json"])
            meta["AttachmentFileStates"][OTHER] = 1
            parts["meta.json"] = json.dumps(meta).encode()
        parts["attachments.json"] += b"\n" + json.dumps(duplicate).encode()
    elif mutation == "combined_length_crc":
        change_record(parts, TXT, DataLength=1)
    elif mutation != "pdf_crc":
        raise AssertionError("Unimplemented fixture mutation: " + mutation)
    source = write_source(tmp_path, parts)
    if mutation in {"pdf_crc", "combined_length_crc"}:
        source.write_bytes(
            source.read_bytes().replace(b"rule control", b"bad! control")
        )
    original = source.read_bytes()
    destination = tmp_path / "vault"
    destination.mkdir()
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    converted = workflow.convert(source, destination)
    assert inspected.outcome == converted.outcome == "refused", (
        mutation,
        converted.issues,
    )
    assert converted.issues == inspected.issues
    assert converted.receipt is None and not list(destination.iterdir())
    assert all(
        issue.severity == "error" and issue.guidance for issue in converted.issues
    )
    assert source.read_bytes() == original


def test_multiple_pdfs_require_identity_association_rather_than_matching_filename(
    tmp_path,
):
    parts = zero_parts(tmp_path)
    add_attachment(parts, OTHER, 1, PDF + ".pdf", b"%PDF-1.4 unrelated intact file")
    result = default_workflow().convert(
        write_source(tmp_path, parts), tmp_path / "vault"
    )
    assert result.outcome == "warnings", result.issues
    observed = json.loads(result.issues[0].message.split(" Observed: ", 1)[1])
    assert (
        observed["pdf_attachment_id"] == PDF
        and observed["pdf"]["filename"] == "manual.pdf"
    )
    assert (
        tmp_path / "vault/Attachments/22222222/manual.pdf"
    ).read_bytes() == PDF_BYTES
    change_record(parts, PDF, Location="manual.bin")
    parts[OWNER + "/manual.bin"] = parts.pop(OWNER + "/manual.pdf")
    refused = default_workflow().convert(
        write_source(tmp_path, parts), tmp_path / "refused"
    )
    assert refused.outcome == "refused" and not (tmp_path / "refused").exists()


def test_zero_length_warning_cli_json_and_text_agree_with_public_library(
    tmp_path, capsys
):
    source = write_source(tmp_path, zero_parts(tmp_path))
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
    assert "approved_source_gap" in text and TXT_NAME in text and PDF in text


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown_rule",
        "unknown_kind",
        "missing_evidence",
        "unknown_evidence",
        "unknown_subject",
        "incompatible_profile",
        "missing_disposition",
        "wrong_disposition_kind",
        "refusing_disposition",
        "no_absence_permission",
        "error_code_downgrade",
    ],
)
def test_public_analysis_requires_the_new_findings_reviewed_disposition(
    tmp_path, mutation
):
    with BrzSourceModule().open(
        write_source(tmp_path, zero_parts(tmp_path))
    ) as session:
        snapshot = session.snapshot
    policy = BRZ_POLICY
    finding_updates = {
        "unknown_rule": {"rule_id": "unknown/zero-txt/v1"},
        "unknown_kind": {"kind": "unknown"},
        "missing_evidence": {"evidence": ()},
        "unknown_evidence": {"evidence": ("unverified",)},
        "unknown_subject": {"affected": ("unverified",)},
    }
    if mutation in finding_updates:
        finding = snapshot.findings[0].model_copy(update=finding_updates[mutation])
        snapshot = snapshot.model_copy(update={"findings": (finding,)})
    elif mutation == "incompatible_profile":
        policy = policy.model_copy(update={"module_version": "future"})
    else:
        disposition = next(d for d in policy.finding_dispositions if d.rule_id == RULE)
        updates = {
            "wrong_disposition_kind": {"kind": "unknown"},
            "refusing_disposition": {"disposition": "refuse"},
            "no_absence_permission": {"permits_absent_payload": False},
            "error_code_downgrade": {"issue_code": "invalid_source"},
        }
        dispositions = (
            ()
            if mutation == "missing_disposition"
            else (disposition.model_copy(update=updates[mutation]),)
        )
        policy = policy.model_copy(update={"finding_dispositions": dispositions})
    with pytest.raises(MigrationRefused):
        analyze(snapshot, policy)


def test_gap_does_not_materialize_an_otherwise_empty_owner_or_fabricate_text(tmp_path):
    parts = source_parts(tmp_path)
    thought = json.loads(parts["thoughts.json"])
    thought.update(Id=OTHER, Name="Empty owner")
    parts["thoughts.json"] += b"\n" + json.dumps(thought).encode()
    # Normal file verification is byte/inventory based; a zero-byte file supplies
    # no content eligibility. The absent declaration must not supply it either.
    add_attachment(parts, PDF, 1, "empty.pdf", b"", owner=OTHER)
    add_attachment(parts, TXT, 15, TXT_NAME, declared=0, state=2, owner=OTHER)
    source = write_source(tmp_path, parts)
    with BrzSourceModule().open(source) as session:
        snapshot = session.snapshot
    migration_plan = plan(analyze(snapshot, BRZ_POLICY))
    owner = next(t for t in migration_plan.item_targets if t.item_key == OTHER)
    assert not owner.created
    absent = next(t for t in migration_plan.asset_targets if t.asset_id == TXT)
    assert absent.relative_path is None and absent.resource_link is None
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "warnings" and result.counts.actual_notes == 1
    assert not (vault / owner.relative_path).exists()
    assert (vault / "Attachments/88888888/empty.pdf").read_bytes() == b""
    assert not list(vault.rglob("*.txt"))
    assert TXT_NAME not in (vault / "Home — Entry thought.md").read_text()


def test_individual_new_and_existing_findings_and_bytes_survive_repeat_and_reorder(
    tmp_path,
):
    parts = zero_parts(tmp_path)
    second_txt = "99999999-9999-4999-8999-999999999999"
    positive_txt = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    add_attachment(parts, OTHER, 1, "other.pdf", b"%PDF-1.4 second exact bytes")
    add_attachment(parts, second_txt, 15, OTHER + ".txt", declared=0, state=2)
    add_attachment(parts, positive_txt, 15, "legacy.txt", declared=17, state=2)
    add_attachment(parts, ICON, 5, "icon.png", b"exact icon", declared=999)
    source = write_source(tmp_path, parts)
    first = default_workflow().convert(source, tmp_path / "first")
    repeat = default_workflow().convert(source, tmp_path / "repeat")
    parts["attachments.json"] = b"\n".join(
        reversed(
            [line for line in parts["attachments.json"].splitlines() if line.strip()]
        )
    )
    reordered = default_workflow().convert(
        write_source(tmp_path, dict(reversed(list(parts.items())))),
        tmp_path / "reordered",
    )
    assert first.outcome == repeat.outcome == reordered.outcome == "warnings"
    expected_rules = {
        TXT: RULE,
        second_txt: RULE,
        positive_txt: "thebrain-format5/absent-txt/v1",
        ICON: "thebrain-format5/icon-length/v1",
    }
    for result in (first, repeat, reordered):
        assert {
            issue.affected[0]: issue.rule_id for issue in result.issues
        } == expected_rules
        assert result.receipt.published and result.receipt.verified
        assert result.counts.actual_assets == 4
    for vault_name in ("first", "repeat", "reordered"):
        vault = tmp_path / vault_name
        assert (vault / "Attachments/22222222/manual.pdf").read_bytes() == PDF_BYTES
        assert (
            vault / "Attachments/22222222/other.pdf"
        ).read_bytes() == b"%PDF-1.4 second exact bytes"
        assert (vault / "Attachments/22222222/icon.png").read_bytes() == b"exact icon"
        assert not list(vault.rglob("*.txt"))
        record = json.loads((vault / "migration-record.json").read_bytes())
        assert {
            a["asset_id"]: a["source_findings"][0]["rule_id"]
            for a in record["asset_targets"]
            if a["source_findings"]
        } == expected_rules
        findings = {
            a["asset_id"]: json.loads(a["source_findings"][0]["observed_json"])
            for a in record["asset_targets"]
            if a["source_findings"]
        }
        assert findings[TXT]["pdf_attachment_id"] == PDF
        assert findings[second_txt]["pdf_attachment_id"] == OTHER
        assert findings[positive_txt]["declared_length"] == 17
        assert "pdf_attachment_id" not in findings[positive_txt]
    for relative_path in ("Home — Entry thought.md", "MIGRATION REPORT.md"):
        assert (
            (tmp_path / "first" / relative_path).read_bytes()
            == (tmp_path / "repeat" / relative_path).read_bytes()
            == (tmp_path / "reordered" / relative_path).read_bytes()
        )

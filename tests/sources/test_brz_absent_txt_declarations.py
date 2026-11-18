"""Approved archive loss is retained explicitly, without inferred replacement."""

import hashlib
import json

import pytest

from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.contracts import MigrationRefused
from brz2obsidian.core import analyze
from brz2obsidian.sources.thebrain import BrzSourceModule
from brz2obsidian.sources.thebrain.profile import BRZ_POLICY
from tests.application.test_verified_coverage import (
    OWNER,
    PDF,
    TXT,
    absent_parts,
    add_attachment,
    change_record,
    source_parts,
    write_source,
)

RULE = "thebrain-format5/absent-txt-declaration/v1"
DOCX = "88888888-8888-4888-8888-888888888888"
DOCX_BYTES = b"Opaque DOCX source bytes are preserved separately.\x00\xff"
NOTE_BYTES = b"Authored body.\r\n"
WARNING = (
    "This archive declares TXT content but contains no payload; "
    "its declaration is retained and the missing bytes were not recovered."
)


def absent_txt_parts(tmp_path, companion="none"):
    parts = source_parts(tmp_path)
    add_attachment(parts, TXT, 15, "unrecovered.txt", declared=17, state=2)
    if companion == "docx":
        add_attachment(parts, DOCX, 1, "lecture.docx", DOCX_BYTES)
    rows = [
        json.loads(row) for row in parts["attachments.json"].splitlines() if row.strip()
    ]
    if companion != "authored_note":
        rows = [row for row in rows if row["Id"] in {TXT, DOCX}]
        meta = json.loads(parts["meta.json"])
        meta["AttachmentFileStates"] = {
            row["Id"]: 2 if row["Id"] == TXT else 1 for row in rows
        }
        parts["meta.json"] = json.dumps(meta).encode()
        del parts[OWNER + "/Notes.md"]
    parts["attachments.json"] = "\n".join(json.dumps(row) for row in rows).encode()
    return parts


def absent_txt_source(tmp_path, companion="none"):
    return write_source(tmp_path, absent_txt_parts(tmp_path, companion))


def test_current_brz_retains_nonzero_txt_declaration_without_any_companion(tmp_path):
    source = absent_txt_source(tmp_path)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    with BrzSourceModule().open(source) as session:
        snapshot = session.snapshot
        assert snapshot.contract_version == 7
        assert (
            snapshot.identity.module_id,
            snapshot.identity.module_version,
            snapshot.identity.format_version,
        ) == ("thebrain-brz", "11", "5")
        assert len(snapshot.assets) == 1 and snapshot.documents == ()
        asset = snapshot.assets[0]
        assert (
            asset.asset_id,
            asset.owner,
            asset.original_name,
            asset.role,
            asset.availability,
            asset.actual_length,
            asset.actual_sha256,
            asset.external_uri,
        ) == (
            TXT,
            OWNER,
            "unrecovered.txt",
            "file",
            "absent",
            None,
            None,
            None,
        )
        assert len(snapshot.findings) == 1
        finding = snapshot.findings[0]
        assert (finding.kind, finding.rule_id, finding.affected, finding.evidence) == (
            "known_absent_payload",
            RULE,
            (TXT,),
            ("attachments.json:0", "meta.json"),
        )
        assert json.loads(finding.observed_json) == {
            "owner": OWNER,
            "filename": "unrecovered.txt",
            "member": OWNER + "/unrecovered.txt",
            "source_type": 2,
            "type": 15,
            "note_type": 0,
            "declared_length": 17,
            "state": 2,
            "present": False,
        }
        declared = json.loads(
            next(
                e.original_json
                for e in snapshot.original_evidence
                if e.key == "attachments.json"
            )
        )
        assert declared[0]["Id"] == TXT and declared[0]["DataLength"] == 17
        assert not any(
            e.key == "payload:" + OWNER + "/unrecovered.txt"
            for e in snapshot.original_evidence
        )
        accounting = next(
            row
            for row in snapshot.accounting.entries
            if row.identity == "attachments.json:0"
        )
        assert (accounting.disposition, accounting.references) == (
            "normalized",
            ("attachments.json:0",),
        )
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash


@pytest.mark.parametrize("companion", ("none", "authored_note", "docx"))
def test_workflow_warns_and_publishes_retained_declaration_without_invented_bytes(
    tmp_path, companion
):
    source = absent_txt_source(tmp_path, companion)
    before = source.read_bytes()
    inspected = default_workflow().inspect(source)
    assert inspected.outcome == "warnings", inspected.issues
    assert inspected.profile_version == "11"
    assert len(inspected.issues) == 1
    issue = inspected.issues[0]
    assert (issue.code, issue.severity, issue.rule_id, issue.affected) == (
        "approved_source_gap",
        "warning",
        RULE,
        (TXT,),
    )
    assert issue.message.startswith(WARNING) and "PDF" not in issue.message
    destination = tmp_path / "vault"
    result = default_workflow().convert(source, destination)
    assert (
        result.outcome == "warnings"
        and result.receipt.published
        and result.receipt.verified
    )
    assert result.issues == inspected.issues
    present = int(companion != "none")
    assert (
        result.counts.source_items,
        result.counts.present_assets,
        result.counts.planned_assets,
        result.counts.actual_assets,
        result.counts.source_gaps,
    ) == (1, present, present, present, 0)
    record = json.loads((destination / "migration-record.json").read_bytes())
    assert (
        record["schema_version"],
        record["profile_version"],
        record["source_identity"]["module_version"],
    ) == (9, "11", "11")
    assert len(record["asset_targets"]) == present + 1
    absent = next(row for row in record["asset_targets"] if row["asset_id"] == TXT)
    assert (
        absent["asset_id"],
        absent["availability"],
        absent["relative_path"],
        absent["actual_length"],
        absent["actual_sha256"],
        absent["resource_link"],
    ) == (
        TXT,
        "absent",
        None,
        None,
        None,
        None,
    )
    assert absent["source_findings"][0]["rule_id"] == RULE
    pointer = (
        "attachments.json:1" if companion == "authored_note" else "attachments.json:0"
    )
    assert absent["evidence"] == [pointer]
    entry = next(
        row
        for row in record["source_accounting"]["entries"]
        if row["identity"] == pointer
    )
    assert (entry["disposition"], entry["references"]) == ("normalized", [pointer])
    declarations = next(
        row["records"]
        for row in record["original_evidence"]
        if row["key"] == "attachments.json"
    )
    retained = next(row for row in declarations if row["Id"] == TXT)
    assert (
        retained["DataLength"],
        retained["SourceType"],
        retained["Type"],
        retained["NoteType"],
    ) == (17, 2, 15, 0)
    actual = {
        row["asset_id"]: (destination / row["relative_path"]).read_bytes()
        for row in record["asset_targets"]
        if row["relative_path"] is not None
    }
    assert actual == (
        {}
        if companion == "none"
        else {DOCX: DOCX_BYTES}
        if companion == "docx"
        else {"33333333-3333-4333-8333-333333333333": NOTE_BYTES}
    )
    if companion == "authored_note":
        assert NOTE_BYTES in (destination / "Home — Entry thought.md").read_bytes()
    assert not list(destination.rglob("*.txt"))
    report = (destination / "MIGRATION REPORT.md").read_text(encoding="utf-8")
    assert WARNING in report and "unrecovered.txt" in report
    assert source.read_bytes() == before


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("unknown_rule", "unsupported_feature"),
        ("missing_finding", "missing_required_payload"),
        ("transplanted_subject", "missing_required_payload"),
        ("missing_evidence", "unsupported_feature"),
        ("invented_evidence", "unsupported_feature"),
        ("no_absence_permission", "missing_required_payload"),
        ("old_module", "unsupported_format"),
    ],
)
def test_core_requires_bound_policy_and_evidence_for_new_txt_absence(
    tmp_path, mutation, code
):
    with BrzSourceModule().open(absent_txt_source(tmp_path)) as session:
        snapshot = session.snapshot
    policy = BRZ_POLICY
    if mutation == "no_absence_permission":
        policy = policy.model_copy(
            update={
                "finding_dispositions": tuple(
                    row.model_copy(update={"permits_absent_payload": False})
                    if row.rule_id == RULE
                    else row
                    for row in policy.finding_dispositions
                )
            }
        )
    elif mutation == "old_module":
        snapshot = snapshot.model_copy(
            update={
                "identity": snapshot.identity.model_copy(
                    update={"module_version": "10"}
                )
            }
        )
    elif mutation == "missing_finding":
        snapshot = snapshot.model_copy(update={"findings": ()})
    else:
        fields = {
            "unknown_rule": {"rule_id": "unapproved/absence/v1"},
            "transplanted_subject": {"affected": (OWNER,)},
            "missing_evidence": {"evidence": ()},
            "invented_evidence": {"evidence": ("payload:invented",)},
        }[mutation]
        snapshot = snapshot.model_copy(
            update={"findings": (snapshot.findings[0].model_copy(update=fields),)}
        )
    with pytest.raises(MigrationRefused) as error:
        analyze(snapshot, policy)
    assert error.value.issues[0].code == code


@pytest.mark.parametrize("declared", (17, 0))
def test_existing_nonzero_and_zero_exact_pdf_findings_keep_their_meaning(
    tmp_path, declared
):
    parts = absent_parts(tmp_path)
    if declared == 0:
        change_record(
            parts, TXT, Location=PDF + ".txt", Name=PDF + ".txt", DataLength=0
        )
    source = write_source(tmp_path, parts)
    with BrzSourceModule().open(source) as session:
        finding = session.snapshot.findings[0]
        observed = json.loads(finding.observed_json)
        assert finding.affected == (TXT,)
        if declared:
            assert finding.rule_id == "thebrain-format5/absent-txt/v1"
            assert observed == {
                "owner": OWNER,
                "filename": "paper.txt",
                "declared_length": 17,
                "state": 2,
                "present": False,
                "intact_same_owner_pdfs": [PDF],
            }
            assert finding.evidence == (
                "attachments.json:2",
                "meta.json",
                "attachments.json:1",
            )
        else:
            assert finding.rule_id == "thebrain-format5/zero-length-absent-txt/v1"
            assert (
                observed["declared_length"],
                observed["filename_stem"],
                observed["pdf_attachment_id"],
                observed["pdf"]["member"],
            ) == (
                0,
                PDF,
                PDF,
                OWNER + "/paper.pdf",
            )
            assert finding.evidence == (
                "attachments.json:2",
                "meta.json",
                "attachments.json:1",
                "payload:" + OWNER + "/paper.pdf",
            )
        with session.open_payload(PDF) as stream:
            assert stream.read() == b"%PDF-1.4 synthetic"
        analysis = analyze(session.snapshot, BRZ_POLICY)
        assert len(analysis.issues) == 1
        assert (analysis.issues[0].code, analysis.issues[0].rule_id) == (
            "approved_source_gap",
            finding.rule_id,
        )


def test_forgotten_owner_txt_does_not_gain_a_warning_or_public_trace(tmp_path):
    parts = absent_txt_parts(tmp_path)
    private = "99999999-9999-4999-8999-999999999999"
    parts["thoughts.json"] += (
        b"\n"
        + json.dumps(
            {
                "Id": private,
                "BrainId": "11111111-1111-4111-8111-111111111111",
                "Kind": 1,
                "ACType": 0,
                "Name": "PRIVATE OWNER CANARY",
                "TagIds": [],
                "ForgottenDateTime": "2026-10-01T12:00:00.1234567+02:00",
            }
        ).encode()
    )
    change_record(
        parts,
        TXT,
        SourceId=private,
        Location="PRIVATE-TXT-CANARY.txt",
        Name="PRIVATE-TXT-CANARY.txt",
    )
    source = write_source(tmp_path, parts)
    destination = tmp_path / "private-vault"
    result = default_workflow().convert(source, destination)
    assert result.outcome == "clean" and result.receipt.verified
    public = result.model_dump_json().encode() + b"".join(
        path.read_bytes() for path in destination.rglob("*") if path.is_file()
    )
    for secret in (
        private.encode(),
        TXT.encode(),
        b"PRIVATE OWNER CANARY",
        b"PRIVATE-TXT-CANARY",
    ):
        assert secret not in public


def test_current_api_successful_txt_without_pdf_remains_present_and_exact():
    from brz2obsidian.sources.thebrain.local_api import (
        LocalApiConfig,
        LocalApiSourceModule,
        LocalApiSourceRef,
    )
    from tests.support.local_api import BRAIN, KEY, api_server
    from tests.support.local_api_payloads import (
        PDF as API_PDF,
    )
    from tests.support.local_api_payloads import (
        TXT as API_TXT,
    )
    from tests.support.local_api_payloads import (
        MissingTxtPdfApi,
    )

    data = b"Current API text is present, not a historical reconstruction.\r\n"
    api = MissingTxtPdfApi()
    del api.attachments[API_PDF]
    api.attachments[API_TXT]["dataLength"] = len(data)
    api.overrides[f"/api/attachments/{BRAIN}/{API_TXT}/file-content"] = (200, data)
    with (
        api_server(api) as (_, address),
        LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).open(LocalApiSourceRef(BRAIN)) as session,
    ):
        asset = next(row for row in session.snapshot.assets if row.asset_id == API_TXT)
        assert (asset.availability, asset.actual_length, asset.actual_sha256) == (
            "present",
            len(data),
            hashlib.sha256(data).hexdigest(),
        )
        assert session.snapshot.findings == ()
        with session.open_payload(API_TXT) as stream:
            assert stream.read() == data


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("source_type", "unsupported_feature"),
        ("other_missing_role", "missing_required_payload"),
        ("note_type", "unsupported_feature"),
        ("icon_flag", "unsupported_feature"),
        ("present_state", "unsupported_feature"),
        ("boolean_state", "invalid_source"),
        ("boolean_length", "invalid_source"),
        ("float_length", "invalid_source"),
        ("negative_length", "invalid_source"),
        ("zero_without_pdf", "missing_required_payload"),
        ("unsafe_path", "invalid_source"),
        ("physical_member", "unsupported_feature"),
    ],
)
def test_no_pdf_txt_exception_keeps_exact_role_state_scalar_and_member_guards(
    tmp_path, mutation, code
):
    parts = absent_txt_parts(tmp_path)
    changes = {
        "source_type": {"SourceType": 1},
        "other_missing_role": {"Type": 1},
        "note_type": {"NoteType": 4},
        "icon_flag": {"IsIcon": True},
        "boolean_length": {"DataLength": True},
        "float_length": {"DataLength": 17.0},
        "negative_length": {"DataLength": -1},
        "zero_without_pdf": {"DataLength": 0},
        "unsafe_path": {"Location": "../unrecovered.txt"},
    }
    if mutation in changes:
        change_record(parts, TXT, **changes[mutation])
    elif mutation in {"present_state", "boolean_state"}:
        meta = json.loads(parts["meta.json"])
        meta["AttachmentFileStates"][TXT] = True if mutation == "boolean_state" else 1
        parts["meta.json"] = json.dumps(meta).encode()
    else:
        parts[OWNER + "/unrecovered.txt"] = b"contradictory actual member"
    source = write_source(tmp_path, parts)
    before = source.read_bytes()
    with pytest.raises(MigrationRefused) as error, BrzSourceModule().open(source):
        pytest.fail("Unqualified declaration must not expose a snapshot")
    assert error.value.issues[0].code == code
    if mutation == "unsafe_path":
        # Global scope qualification rejects untrusted paths before assigning
        # attachment context; no trusted subject is invented at that boundary.
        assert error.value.issues[0].affected == ()
        assert (
            error.value.issues[0].message
            == "Unsafe or ambiguous local attachment location"
        )
    else:
        assert TXT in error.value.issues[0].affected
    assert source.read_bytes() == before

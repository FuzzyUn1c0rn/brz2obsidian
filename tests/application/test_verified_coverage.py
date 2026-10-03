import json
from zipfile import ZIP_STORED, ZipFile

import pytest

from brz2obsidian.application import SourceModuleBinding, Workflow
from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.cli import main
from brz2obsidian.contracts import Asset, Item, MigrationRefused, Relationship
from brz2obsidian.core import analyze, plan
from brz2obsidian.obsidian import ObsidianRenderer
from brz2obsidian.publication import FilesystemPublisher
from brz2obsidian.sources.thebrain import BrzSourceModule
from brz2obsidian.sources.thebrain.profile import BRZ_POLICY
from tests.application.test_minimal_workflow import make_archive

OWNER = "22222222-2222-4222-8222-222222222222"
TXT = "55555555-5555-4555-8555-555555555555"
PDF = "66666666-6666-4666-8666-666666666666"
ICON = "77777777-7777-4777-8777-777777777777"


def source_parts(tmp_path):
    with ZipFile(make_archive(tmp_path / "base.brz")) as archive:
        return {n: archive.read(n) for n in archive.namelist()}


def write_source(tmp_path, parts):
    path = tmp_path / "source.brz"
    with ZipFile(path, "w", compression=ZIP_STORED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    return path


def add_attachment(
    parts, key, kind, location, data=None, declared=None, state=1, owner=OWNER
):
    record = json.loads(parts["attachments.json"].splitlines()[0])
    record.update(
        Id=key,
        SourceId=owner,
        Type=kind,
        NoteType=0,
        Location=location,
        Name=location,
        DataLength=declared if declared is not None else len(data or b""),
        IsIcon=kind == 5,
    )
    parts["attachments.json"] += b"\n" + json.dumps(record).encode()
    meta = json.loads(parts["meta.json"])
    if state is not None:
        meta["AttachmentFileStates"][key] = state
    parts["meta.json"] = json.dumps(meta).encode()
    if data is not None:
        prefix = ".data/" if kind == 5 else ".data/md-images/" if kind == 12 else ""
        parts[owner + "/" + prefix + location] = data


def absent_parts(tmp_path):
    parts = source_parts(tmp_path)
    add_attachment(parts, PDF, 1, "paper.pdf", b"%PDF-1.4 synthetic")
    add_attachment(parts, TXT, 15, "paper.txt", declared=17, state=2)
    return parts


def test_exact_absent_txt_publishes_warning_with_metadata_and_no_fake_payload(tmp_path):
    source = write_source(tmp_path, absent_parts(tmp_path))
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "warnings", result.issues
    assert result.receipt.published and result.receipt.verified
    assert result.counts.actual_assets == 2
    issue = result.issues[0]
    assert issue.code == "approved_source_gap"
    assert issue.severity == "warning" and issue.rule_id.endswith("/v1")
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    assert record["issues"] == [issue.model_dump(mode="json")]
    assert set(record) == {
        "schema",
        "schema_version",
        "converter_version",
        "renderer_version",
        "source_identity",
        "profile_id",
        "profile_version",
        "run_metadata",
        "item_targets",
        "asset_targets",
        "relationships",
        "tag_memberships",
        "adaptations",
        "source_accounting",
        "issues",
        "counts",
        "obsidian_configuration",
        "original_evidence",
    }
    asset = next(a for a in record["asset_targets"] if a["asset_id"] == TXT)
    observed = json.loads(asset["source_findings"][0]["observed_json"])
    assert observed["state"] == 2 and observed["declared_length"] == 17
    assert observed["present"] is False
    assert "paper.txt" in (tmp_path / "vault/MIGRATION REPORT.md").read_text()
    note = (tmp_path / "vault/Home — Entry thought.md").read_text()
    assert "Absent source file: paper.txt" in note
    assert "paper.txt|" not in note
    assert not list((tmp_path / "vault").rglob("*.txt"))
    original = next(
        e["records"]
        for e in record["original_evidence"]
        if e["key"] == "attachments.json"
    )
    assert next(r for r in original if r["Id"] == TXT)["DataLength"] == 17


def test_crc_valid_icon_length_discrepancy_copies_actual_bytes_and_retains_lengths(
    tmp_path,
):
    parts = source_parts(tmp_path)
    add_attachment(parts, ICON, 5, "icon.png", b"synthetic-icon", declared=999)
    source = write_source(tmp_path, parts)
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "warnings", result.issues
    assert result.issues[0].code == "approved_metadata_discrepancy"
    assert (
        tmp_path / "vault/Attachments/22222222/icon.png"
    ).read_bytes() == b"synthetic-icon"
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    asset = next(a for a in record["asset_targets"] if a["asset_id"] == ICON)
    observed = json.loads(asset["source_findings"][0]["observed_json"])
    assert observed["declared_length"] == 999 and observed["actual_length"] == 14
    assert "icon.png" not in (tmp_path / "vault/Home — Entry thought.md").read_text()


def change_record(parts, key, **updates):
    records = [
        json.loads(line)
        for line in parts["attachments.json"].splitlines()
        if line.strip()
    ]
    next(r for r in records if r["Id"] == key).update(updates)
    parts["attachments.json"] = "\n".join(json.dumps(r) for r in records).encode()


@pytest.mark.parametrize(
    "near_miss",
    [
        "source_type",
        "kind",
        "note_type",
        "extension",
        "zero",
        "negative",
        "state_one",
        "state_missing",
        "present",
        "pdf_absent",
        "pdf_elsewhere",
        "pdf_length",
        "pdf_corrupt",
        "owner_absent",
        "icon_flag",
        "special_flag",
    ],
)
def test_absent_txt_rule_requires_every_conjunct_and_keeps_destination_untouched(
    tmp_path, near_miss
):
    parts = absent_parts(tmp_path)
    updates = {
        "source_type": {"SourceType": 1},
        "kind": {"Type": 1},
        "note_type": {"NoteType": 4},
        "extension": {"Location": "paper.bin"},
        "zero": {"DataLength": 0},
        "negative": {"DataLength": -1},
        "owner_absent": {"SourceId": "99999999-9999-4999-8999-999999999999"},
        "icon_flag": {"IsIcon": True},
        "special_flag": {"IsWallpaper": True},
    }
    if near_miss in updates:
        change_record(parts, TXT, **updates[near_miss])
    elif near_miss in {"state_one", "state_missing"}:
        meta = json.loads(parts["meta.json"])
        if near_miss == "state_one":
            meta["AttachmentFileStates"][TXT] = 1
        else:
            del meta["AttachmentFileStates"][TXT]
        parts["meta.json"] = json.dumps(meta).encode()
    elif near_miss == "present":
        parts[OWNER + "/paper.txt"] = b"present text"
    elif near_miss == "pdf_absent":
        del parts[OWNER + "/paper.pdf"]
    elif near_miss == "pdf_elsewhere":
        other = "88888888-8888-4888-8888-888888888888"
        thought = json.loads(parts["thoughts.json"])
        thought.update(Id=other, Name="Other")
        parts["thoughts.json"] += b"\n" + json.dumps(thought).encode()
        change_record(parts, PDF, SourceId=other)
        parts[other + "/paper.pdf"] = parts.pop(OWNER + "/paper.pdf")
    elif near_miss == "pdf_length":
        change_record(parts, PDF, DataLength=999)
    source = write_source(tmp_path, parts)
    if near_miss == "pdf_corrupt":
        raw = source.read_bytes().replace(b"%PDF-1.4 synthetic", b"%PDF-1.4 corrupted")
        source.write_bytes(raw)
    destination = tmp_path / "vault"
    destination.mkdir()
    result = default_workflow().convert(source, destination)
    assert result.outcome == "refused", (near_miss, result.issues)
    assert result.receipt is None and result.counts is None
    assert result.issues[0].severity == "error" and result.issues[0].guidance
    assert list(destination.iterdir()) == []


@pytest.mark.parametrize(
    "near_miss",
    [
        "file",
        "image",
        "note",
        "absent",
        "state_two",
        "wrong_flag",
        "note_type",
        "source_type",
        "corrupt",
    ],
)
def test_icon_length_warning_does_not_authorize_other_roles_or_unreliable_bytes(
    tmp_path, near_miss
):
    parts = source_parts(tmp_path)
    add_attachment(parts, ICON, 5, "icon.png", b"synthetic-icon", declared=999)
    if near_miss in {"file", "image", "note"}:
        kind = {"file": 1, "image": 12, "note": 1}[near_miss]
        change_record(
            parts,
            ICON,
            Type=kind,
            IsIcon=False,
            NoteType=4 if near_miss == "note" else 0,
        )
        prefix = ".data/md-images/" if kind == 12 else ""
        parts[OWNER + "/" + prefix + "icon.png"] = parts.pop(OWNER + "/.data/icon.png")
    elif near_miss == "absent":
        del parts[OWNER + "/.data/icon.png"]
    elif near_miss == "state_two":
        meta = json.loads(parts["meta.json"])
        meta["AttachmentFileStates"][ICON] = 2
        parts["meta.json"] = json.dumps(meta).encode()
    elif near_miss == "wrong_flag":
        change_record(parts, ICON, IsIcon=False)
    elif near_miss == "note_type":
        change_record(parts, ICON, NoteType=4)
    elif near_miss == "source_type":
        change_record(parts, ICON, SourceType=1)
    source = write_source(tmp_path, parts)
    if near_miss == "corrupt":
        source.write_bytes(
            source.read_bytes().replace(b"synthetic-icon", b"corrupted-icon")
        )
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "refused", result.issues
    assert result.receipt is None and not (tmp_path / "vault").exists()


@pytest.mark.parametrize("separator", ["\u0085", "\u2028", "\u2029"])
def test_unicode_separators_inside_json_strings_are_preserved_not_split_as_records(
    tmp_path, separator
):
    parts = source_parts(tmp_path)
    thought = json.loads(parts["thoughts.json"])
    thought["Name"] = "Entry" + separator + "thought"
    parts["thoughts.json"] = json.dumps(thought, ensure_ascii=False).encode()
    result = default_workflow().convert(
        write_source(tmp_path, parts), tmp_path / "vault"
    )
    assert result.outcome == "clean", result.issues
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    original = next(
        e["records"][0]
        for e in record["original_evidence"]
        if e["key"] == "thoughts.json"
    )
    assert original["Name"] == "Entry" + separator + "thought"


@pytest.mark.parametrize(
    "field,value",
    [
        ("IsType", True),
        ("IsTag", True),
        ("IsSystem", True),
        ("IsEvent", True),
        ("IsBrainIcon", True),
        ("IsUnverifiedRole", True),
        ("ACType", True),
        ("ThoughtTypeId", "custom"),
        ("TypeId", False),
        ("TagIds", {}),
        ("TagIds", ["custom"]),
        ("Aliases", ["unverified alias"]),
    ],
)
def test_unverified_thought_semantics_are_explicit_refusals(tmp_path, field, value):
    parts = source_parts(tmp_path)
    thought = json.loads(parts["thoughts.json"])
    thought[field] = value
    parts["thoughts.json"] = json.dumps(thought).encode()
    result = default_workflow().convert(
        write_source(tmp_path, parts), tmp_path / "vault"
    )
    assert result.outcome == "refused", (field, result.issues)
    assert result.issues[0].code in {"invalid_source", "unsupported_feature"}
    assert result.counts is None and result.receipt is None


def test_live_identity_cannot_be_shared_between_thought_and_attachment(tmp_path):
    parts = source_parts(tmp_path)
    attachment = json.loads(parts["attachments.json"])
    old = attachment["Id"]
    attachment["Id"] = OWNER
    parts["attachments.json"] = json.dumps(attachment).encode()
    meta = json.loads(parts["meta.json"])
    meta["AttachmentFileStates"][OWNER] = meta["AttachmentFileStates"].pop(old)
    parts["meta.json"] = json.dumps(meta).encode()
    result = default_workflow().inspect(write_source(tmp_path, parts))
    assert result.outcome == "refused" and result.issues[0].code == "invalid_source"


def test_active_rich_html_note_feature_is_refused(tmp_path):
    parts = source_parts(tmp_path)
    body = b"<div>rich content</div>"
    parts[OWNER + "/Notes.md"] = body
    attachment = json.loads(parts["attachments.json"])
    attachment["DataLength"] = len(body)
    parts["attachments.json"] = json.dumps(attachment).encode()
    result = default_workflow().inspect(write_source(tmp_path, parts))
    assert (
        result.outcome == "refused" and result.issues[0].code == "unsupported_feature"
    )


def test_verified_attribute_free_markdown_linebreaks_remain_unchanged(tmp_path):
    parts = source_parts(tmp_path)
    body = b"Markdown<br>line<br/>ending\r\n"
    parts[OWNER + "/Notes.md"] = body
    attachment = json.loads(parts["attachments.json"])
    attachment["DataLength"] = len(body)
    parts["attachments.json"] = json.dumps(attachment).encode()
    result = default_workflow().convert(
        write_source(tmp_path, parts), tmp_path / "vault"
    )
    assert result.outcome == "clean"
    assert body in (tmp_path / "vault/Home — Entry thought.md").read_bytes()


def test_warning_cli_json_and_text_exit_two_match_durable_library_issues(
    tmp_path, capsys
):
    source = write_source(tmp_path, absent_parts(tmp_path))
    expected = default_workflow().inspect(source)
    assert main(["inspect", str(source), "--json"]) == 2
    captured = capsys.readouterr()
    assert captured.err == ""
    envelope = json.loads(captured.out)
    assert envelope == expected.model_dump(mode="json", by_alias=True)
    assert envelope["counts"]["actual_notes"] is None and envelope["receipt"] is None
    assert main(["convert", str(source), str(tmp_path / "vault"), "--json"]) == 2
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["receipt"]["published"] and envelope["receipt"]["verified"]
    assert envelope["issues"] == expected.model_dump(mode="json")["issues"]
    assert main(["inspect", str(source)]) == 2
    text = capsys.readouterr().out
    assert "approved_source_gap" in text and "paper.txt" in text


@pytest.mark.parametrize(
    "change",
    [
        "unknown_rule",
        "unknown_kind",
        "missing_evidence",
        "incompatible_module",
    ],
)
def test_public_core_requires_compatible_reviewed_finding_disposition(tmp_path, change):
    with BrzSourceModule().open(
        write_source(tmp_path, absent_parts(tmp_path))
    ) as session:
        snapshot = session.snapshot
    policy = BRZ_POLICY
    if change == "incompatible_module":
        snapshot = snapshot.model_copy(
            update={
                "identity": snapshot.identity.model_copy(
                    update={"module_version": "future"}
                )
            }
        )
    else:
        finding = snapshot.findings[0].model_copy(
            update={
                "unknown_rule": {"rule_id": "unknown/v1"},
                "unknown_kind": {"kind": "unknown"},
                "missing_evidence": {"evidence": ()},
            }[change]
        )
        snapshot = snapshot.model_copy(update={"findings": (finding,)})
    with pytest.raises(MigrationRefused) as refused:
        analyze(snapshot, policy)
    assert refused.value.issues[0].code in {"unsupported_feature", "unsupported_format"}


def test_public_source_findings_and_accounting_remain_durable_after_session_closes(
    tmp_path,
):
    with BrzSourceModule().open(
        write_source(tmp_path, absent_parts(tmp_path))
    ) as session:
        snapshot = session.snapshot
    assert snapshot.findings[0].affected == (TXT,)
    assert snapshot.findings[0].rule_id == "thebrain-format5/absent-txt/v1"
    assert all(e.disposition != "unresolved" for e in snapshot.accounting.entries)
    identities = {e.identity for e in snapshot.accounting.entries}
    assert {"attachments.json:2", "payload:" + OWNER + "/paper.pdf"} <= identities
    migration_plan = plan(analyze(snapshot, BRZ_POLICY))
    absent = next(t for t in migration_plan.asset_targets if t.asset_id == TXT)
    assert absent.relative_path is None and absent.resource_link is None


@pytest.mark.parametrize(
    "collection",
    [
        "calendarevents.json",
        "access.json",
        "fielddefinitions.json",
        "fieldinstances.json",
    ],
)
def test_nonempty_unverified_collections_refuse_without_modifying_destination(
    tmp_path, collection
):
    parts = source_parts(tmp_path)
    parts[collection] = b'{"Unverified":true}'
    result = default_workflow().convert(
        write_source(tmp_path, parts), tmp_path / "vault"
    )
    assert (
        result.outcome == "refused" and result.issues[0].code == "unsupported_feature"
    )
    assert not (tmp_path / "vault").exists()


@pytest.mark.parametrize(
    "body",
    [
        b'<br class="rich">',
        b'<img src="https://example.invalid/image">',
        b'<a href="brain://anything/title">local</a>',
        b"<br></br>",
        b"<!DOCTYPE html>",
        b'<?xml version="1.0"?>',
    ],
)
def test_linebreak_exception_does_not_admit_attributes_or_other_html(tmp_path, body):
    parts = source_parts(tmp_path)
    parts[OWNER + "/Notes.md"] = body
    attachment = json.loads(parts["attachments.json"])
    attachment["DataLength"] = len(body)
    parts["attachments.json"] = json.dumps(attachment).encode()
    result = default_workflow().inspect(write_source(tmp_path, parts))
    assert (
        result.outcome == "refused" and result.issues[0].code == "unsupported_feature"
    )


@pytest.mark.parametrize(
    "name", ["empty//", "./", "directory/../", "directory//child/"]
)
def test_ambiguous_directory_member_identity_is_refused(tmp_path, name):
    parts = source_parts(tmp_path)
    parts[name] = b""
    result = default_workflow().inspect(write_source(tmp_path, parts))
    assert result.outcome == "refused" and result.issues[0].code == "invalid_source"


def test_foreign_home_setting_ownership_is_not_silently_interpreted(tmp_path):
    parts = source_parts(tmp_path)
    setting = json.loads(parts["settings.json"])
    setting["BrainId"] = "99999999-9999-4999-8999-999999999999"
    parts["settings.json"] = json.dumps(setting).encode()
    result = default_workflow().inspect(write_source(tmp_path, parts))
    assert result.outcome == "refused" and result.issues[0].code == "invalid_source"


@pytest.mark.parametrize(
    "change",
    [
        "original_owner",
        "original_role",
        "original_absent",
        "duplicate_relationship",
        "external_uri",
        "duplicate_original_identity",
        "invented_finding_evidence",
        "invented_finding_subject",
    ],
)
def test_public_core_refuses_inconsistent_canonical_ownership_and_evidence(
    tmp_path, change
):
    with BrzSourceModule().open(
        write_source(tmp_path, absent_parts(tmp_path))
    ) as session:
        snapshot = session.snapshot
    if change.startswith("original_"):
        original = snapshot.documents[0].original_asset_id
        updates = {
            "original_owner": {"owner": "other"},
            "original_role": {"role": "file"},
            "original_absent": {
                "availability": "absent",
                "actual_length": None,
                "actual_sha256": None,
            },
        }[change]
        snapshot = snapshot.model_copy(
            update={
                "assets": tuple(
                    a.model_copy(update=updates) if a.asset_id == original else a
                    for a in snapshot.assets
                )
            }
        )
        if change == "original_owner":
            snapshot = snapshot.model_copy(
                update={
                    "items": snapshot.items
                    + (
                        Item(
                            key="other",
                            original_identity="other",
                            naming_seed="abcd1234",
                            title="Other",
                        ),
                    )
                }
            )
    elif change == "duplicate_relationship":
        relation = Relationship(key="same", kind="related", item_a=OWNER, item_b=OWNER)
        snapshot = snapshot.model_copy(update={"relationships": (relation, relation)})
    elif change == "external_uri":
        asset = Asset(
            asset_id="external",
            owner=OWNER,
            naming_seed="deadbeef",
            original_name="URL",
            role="url",
            availability="external",
        )
        snapshot = snapshot.model_copy(update={"assets": snapshot.assets + (asset,)})
    elif change == "duplicate_original_identity":
        other = snapshot.items[0].model_copy(
            update={"key": "other", "document_ids": (), "resource_ids": ()}
        )
        snapshot = snapshot.model_copy(update={"items": snapshot.items + (other,)})
    else:
        finding = snapshot.findings[0].model_copy(
            update={"evidence": ("invented evidence",)}
            if change == "invented_finding_evidence"
            else {"affected": ("invented subject",)}
        )
        snapshot = snapshot.model_copy(update={"findings": (finding,)})
    with pytest.raises(MigrationRefused):
        analyze(snapshot, BRZ_POLICY)


def test_icon_warning_does_not_create_an_otherwise_empty_owner_note(tmp_path):
    parts = source_parts(tmp_path)
    other = "88888888-8888-4888-8888-888888888888"
    thought = json.loads(parts["thoughts.json"])
    thought.update(Id=other, Name="Empty owner")
    parts["thoughts.json"] += b"\n" + json.dumps(thought).encode()
    add_attachment(
        parts, ICON, 5, "icon.png", b"actual-icon", declared=100, owner=other
    )
    source = write_source(tmp_path, parts)
    inspected = default_workflow().inspect(source)
    owner = next(t for t in inspected.inspection.item_targets if t.item_key == other)
    assert not owner.created
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "warnings" and result.counts.actual_notes == 1
    assert not (tmp_path / "vault" / owner.relative_path).exists()
    assert (
        tmp_path / "vault/Attachments/88888888/icon.png"
    ).read_bytes() == b"actual-icon"


def test_uninterpreted_history_keeps_nonlive_references_and_does_not_resurrect_items(
    tmp_path,
):
    parts = source_parts(tmp_path)
    history = {
        "Id": "99999999-9999-4999-8999-999999999999",
        "ThoughtId": "nonlive historical reference",
        "DateTime": "2026-10-03T12:34:56",
        "ExplicitNull": None,
    }
    parts["modificationlogs.json"] = json.dumps(history).encode()
    parts["tombstones.json"] = json.dumps(
        {"Id": "99999999-9999-4999-8999-999999999999"}
    ).encode()
    thought = json.loads(parts["thoughts.json"])
    thought["ForgottenDateTime"] = "2026-10-03T10:20:30"
    parts["thoughts.json"] = json.dumps(thought).encode()
    result = default_workflow().convert(
        write_source(tmp_path, parts), tmp_path / "vault"
    )
    assert result.outcome == "clean" and result.counts.actual_notes == 1
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    retained = next(
        e["records"][0]
        for e in record["original_evidence"]
        if e["key"] == "modificationlogs.json"
    )
    assert retained == history
    assert len(record["item_targets"]) == 1


def test_live_deleted_overlap_is_refused_without_destination_mutation(tmp_path):
    parts = source_parts(tmp_path)
    parts["tombstones.json"] = json.dumps({"Id": OWNER}).encode()
    result = default_workflow().convert(
        write_source(tmp_path, parts), tmp_path / "vault"
    )
    assert result.outcome == "refused" and result.issues[0].code == "invalid_source"
    assert not (tmp_path / "vault").exists()


def test_workflow_refusal_retains_measured_source_counts_and_leaves_planning_unavailable(
    tmp_path,
):
    source = write_source(tmp_path, absent_parts(tmp_path))
    workflow = Workflow(
        SourceModuleBinding(
            BrzSourceModule(),
            BRZ_POLICY.model_copy(update={"finding_dispositions": ()}),
        ),
        ObsidianRenderer(),
        FilesystemPublisher(),
    )
    result = workflow.convert(source, tmp_path / "vault")
    assert (
        result.outcome == "refused" and result.issues[0].code == "unsupported_feature"
    )
    assert result.counts.source_items == 1 and result.counts.present_assets == 2
    assert result.counts.planned_notes is None and result.counts.actual_notes is None
    assert result.receipt is None and not (tmp_path / "vault").exists()


def test_cli_has_no_arbitrary_warning_allowlist(tmp_path, capsys):
    source = write_source(tmp_path, absent_parts(tmp_path))
    assert main(["inspect", str(source), "--allow-missing", TXT]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and "unrecognized arguments" in captured.err


def test_system_document_facts_and_original_bytes_are_retained_without_navigation_target(
    tmp_path,
):
    parts = source_parts(tmp_path)
    system = "88888888-8888-4888-8888-888888888888"
    thought = json.loads(parts["thoughts.json"])
    thought.update(Id=system, Name="Retained system", Kind=5)
    parts["thoughts.json"] += b"\n" + json.dumps(thought).encode()
    add_attachment(
        parts, PDF, 1, "Notes.md", b"Retained system Markdown.\r\n", owner=system
    )
    change_record(parts, PDF, NoteType=4)
    result = default_workflow().convert(
        write_source(tmp_path, parts), tmp_path / "vault"
    )
    assert result.outcome == "clean" and result.counts.actual_notes == 1
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    assert system not in {t["item_key"] for t in record["item_targets"]}
    asset = next(a for a in record["asset_targets"] if a["asset_id"] == PDF)
    document = asset["retained_documents"][0]
    assert document["owner"] == system and document["original_asset_id"] == PDF
    assert document["owner_target"] is None
    assert (
        tmp_path / "vault" / asset["relative_path"]
    ).read_bytes() == b"Retained system Markdown.\r\n"


def test_warning_report_order_is_independent_of_attachment_record_order(tmp_path):
    parts = source_parts(tmp_path)
    add_attachment(parts, ICON, 5, "z-icon.png", b"icon-one", declared=100)
    add_attachment(parts, TXT, 5, "a-icon.png", b"icon-two", declared=200)
    source = write_source(tmp_path, parts)
    first = default_workflow().convert(source, tmp_path / "first")
    assert first.outcome == "warnings"
    parts["attachments.json"] = b"\n".join(
        reversed(
            [line for line in parts["attachments.json"].splitlines() if line.strip()]
        )
    )
    source = write_source(tmp_path, parts)
    second = default_workflow().convert(source, tmp_path / "second")
    assert second.outcome == "warnings"
    assert (tmp_path / "first/MIGRATION REPORT.md").read_bytes() == (
        tmp_path / "second/MIGRATION REPORT.md"
    ).read_bytes()

"""Independent raw-source controls for repeated absent positive TXT declarations."""

import json
from zipfile import ZipFile

import pytest

from tests.application.test_graph_workflow import graph_archive, identity
from tests.application.test_verified_coverage import add_attachment, write_source
from tests.local_acceptance.checker import read_source
from tests.local_acceptance.scope import scope


def duplicate_txt_parts(tmp_path):
    source = graph_archive(
        tmp_path / "base.brz", {1: "Home", 2: "Owner"}, notes={1: (b"Home body", 4)}
    )
    with ZipFile(source) as archive:
        parts = {n: archive.read(n) for n in archive.namelist()}
    add_attachment(
        parts, identity(3000), 1, "intact.pdf", b"%PDF-synthetic", owner=identity(2)
    )
    for n, length in ((3001, 17), (3002, 29), (3003, 41)):
        add_attachment(
            parts,
            identity(n),
            15,
            "shared.txt",
            declared=length,
            state=2,
            owner=identity(2),
        )
    return parts


@pytest.mark.parametrize("reverse", [False, True])
def test_raw_scope_retains_every_distinct_absent_positive_txt_declaration(
    tmp_path, reverse
):
    parts = duplicate_txt_parts(tmp_path)
    if reverse:
        parts["attachments.json"] = b"\n".join(
            reversed(parts["attachments.json"].splitlines())
        )
    source = write_source(tmp_path, parts)
    with ZipFile(source) as archive:
        retained = scope(read_source(archive), archive)
    rows = [a for a in retained["attachments.json"] if a["Type"] == 15]
    assert {a["Id"]: a["DataLength"] for a in rows} == {
        identity(3001): 17,
        identity(3002): 29,
        identity(3003): 41,
    }
    assert len(retained["attachments.json"]) == 5


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize(
    "damage",
    [
        "present",
        "source_type",
        "source_bool",
        "note_type",
        "note_bool",
        "kind",
        "kind_bool",
        "state1",
        "state3",
        "no_state",
        "state_bool",
        "zero",
        "negative",
        "float",
        "length_bool",
        "unsafe",
        "extension",
        "duplicate_id",
        "cross_table_id",
        "foreign_brain",
        "unknown_owner",
        "state_owner",
        "mixed_image_member",
        "mixed_icon_member",
        "IsIcon",
        "IsBrainAttachment",
        "IsBrainIcon",
        "IsWallpaper",
        "IsAiScriptsFile",
        "IsKeyboardShortcutsFile",
        "IsToolbarConfigFile",
        "flag_scalar",
        "ordinary_note",
        "image",
        "icon",
    ],
)
def test_raw_scope_refuses_unreviewed_duplicate_groups_in_either_order(
    tmp_path, damage, reverse
):
    parts = duplicate_txt_parts(tmp_path)
    rows = [json.loads(line) for line in parts["attachments.json"].splitlines()]
    row = next(a for a in rows if a["Id"] == identity(3003))
    meta = json.loads(parts["meta.json"])
    if damage == "present":
        parts[identity(2) + "/shared.txt"] = b"present bytes"
    elif damage in {
        "source_type",
        "source_bool",
        "note_type",
        "note_bool",
        "kind",
        "kind_bool",
    }:
        field = {
            "source_type": "SourceType",
            "source_bool": "SourceType",
            "note_type": "NoteType",
            "note_bool": "NoteType",
            "kind": "Type",
            "kind_bool": "Type",
        }[damage]
        row[field] = True if damage.endswith("bool") else 1
    elif damage in {"state1", "state3", "state_bool"}:
        meta["AttachmentFileStates"][row["Id"]] = {
            "state1": 1,
            "state3": 3,
            "state_bool": True,
        }[damage]
    elif damage == "no_state":
        del meta["AttachmentFileStates"][row["Id"]]
    elif damage in {"zero", "negative", "float", "length_bool"}:
        row["DataLength"] = {
            "zero": 0,
            "negative": -1,
            "float": 17.5,
            "length_bool": True,
        }[damage]
    elif damage in {"unsafe", "extension"}:
        for a in rows:
            if a["Type"] == 15:
                a["Location"] = "../shared.txt" if damage == "unsafe" else "shared.bin"
    elif damage == "duplicate_id":
        row["Id"] = identity(3001)
        del meta["AttachmentFileStates"][identity(3003)]
    elif damage == "cross_table_id":
        row["Id"] = identity(2)
    elif damage == "foreign_brain":
        row["BrainId"] = identity(9000)
    elif damage == "unknown_owner":
        row["SourceId"] = identity(9000)
    elif damage == "state_owner":
        meta["AttachmentFileStates"][identity(9000)] = 2
    elif damage in {"mixed_image_member", "mixed_icon_member"}:
        prefix = ".data/md-images/" if damage == "mixed_image_member" else ".data/"
        for a in rows:
            if a["Type"] == 15:
                a["Location"] = prefix + "shared.txt"
        row.update(
            Type=12 if damage == "mixed_image_member" else 5,
            Location="shared.txt",
            IsIcon=damage == "mixed_icon_member",
        )
    elif damage in {"ordinary_note", "image", "icon"}:
        for a in rows:
            if a["Type"] == 15:
                a["Type"] = {"ordinary_note": 1, "image": 12, "icon": 5}[damage]
                if damage == "ordinary_note":
                    a.update(NoteType=4, Location="Notes.md")
                elif damage == "icon":
                    a["IsIcon"] = True
    else:
        row["IsIcon" if damage == "flag_scalar" else damage] = (
            0 if damage == "flag_scalar" else True
        )
    parts["meta.json"] = json.dumps(meta).encode()
    if reverse:
        rows.reverse()
    parts["attachments.json"] = b"\n".join(json.dumps(a).encode() for a in rows)
    source = write_source(tmp_path, parts)
    with ZipFile(source) as archive, pytest.raises(AssertionError):
        scope(read_source(archive), archive)


def thirteen_txt_parts(tmp_path):
    source = graph_archive(
        tmp_path / "base.brz",
        {1: "Home", **{n: f"Owner {n}" for n in range(2, 7)}},
        notes={1: (b"Home body", 4)},
    )
    with ZipFile(source) as archive:
        parts = {n: archive.read(n) for n in archive.namelist()}
    for owner in range(2, 7):
        add_attachment(
            parts,
            identity(4000 + owner),
            1,
            "intact.pdf",
            b"%PDF-synthetic",
            owner=identity(owner),
        )
        for offset, length in ((0, 17), (1, 29)):
            add_attachment(
                parts,
                identity(5000 + 2 * owner + offset),
                15,
                "shared.TXT",
                declared=length,
                state=2,
                owner=identity(owner),
            )
    for offset in range(3):
        add_attachment(
            parts,
            identity(6000 + offset),
            15,
            f"single-{offset}.txt",
            declared=53 + offset,
            state=2,
            owner=identity(2),
        )
    return parts


@pytest.mark.parametrize("reverse", [False, True])
def test_oracle_checks_thirteen_distinct_txt_findings_without_payload_credit(
    tmp_path, reverse
):
    from brz2obsidian.application.wiring import default_workflow
    from tests.local_acceptance.checker import check_vault, load_json

    parts = thirteen_txt_parts(tmp_path)
    if reverse:
        parts["attachments.json"] = b"\n".join(
            reversed(parts["attachments.json"].splitlines())
        )
        parts = dict(reversed(list(parts.items())))
    source = write_source(tmp_path, parts)
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "warnings", result.issues
    assert result.receipt.published and result.receipt.verified
    summary = check_vault(source, vault)
    assert summary["warnings"] == summary["txt_gaps"] == 13
    assert summary["payloads"] == 6 and summary["references"] == 0
    record = load_json((vault / "migration-record.json").read_bytes())
    targets = [a for a in record["asset_targets"] if a["source_findings"]]
    assert len(targets) == len({a["asset_id"] for a in targets}) == 13
    assert len({tuple(a["evidence"]) for a in targets}) == 13
    assert all(
        a["relative_path"] is None
        and a["actual_length"] is None
        and a["actual_sha256"] is None
        for a in targets
    )
    assert not list(vault.rglob("*.txt"))


def test_raw_scope_omits_entire_eligible_excluded_txt_group(tmp_path):
    parts = duplicate_txt_parts(tmp_path)
    thoughts = [json.loads(line) for line in parts["thoughts.json"].splitlines()]
    thoughts[1]["ForgottenDateTime"] = "2026-10-01T10:00:00Z"
    parts["thoughts.json"] = b"\n".join(json.dumps(a).encode() for a in thoughts)
    source = write_source(tmp_path, parts)
    with ZipFile(source) as archive:
        retained = scope(read_source(archive), archive)
    assert [a["Id"] for a in retained["attachments.json"]] == [identity(2001)]
    assert retained.excluded == {identity(2)}
    assert retained["meta.json"][0]["AttachmentFileStates"] == {identity(2001): 1}
    assert retained.dropped_members == {
        identity(2) + "/intact.pdf",
        identity(2) + "/shared.txt",
    }


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("excluded", [False, True])
@pytest.mark.parametrize(
    "field,value",
    [
        ("Name", 11),
        ("IsUnreviewedRole", True),
        ("IsUnreviewedRole", 0),
        ("ThoughtTypeId", identity(9000)),
        ("LinkTypeId", False),
        ("TypeId", identity(9000)),
    ],
)
def test_raw_scope_refuses_unreviewed_metadata_before_excluded_group_omission(
    tmp_path, reverse, excluded, field, value
):
    parts = duplicate_txt_parts(tmp_path)
    rows = [json.loads(line) for line in parts["attachments.json"].splitlines()]
    rows[-1][field] = value
    if reverse:
        rows.reverse()
    parts["attachments.json"] = b"\n".join(json.dumps(a).encode() for a in rows)
    if excluded:
        thoughts = [json.loads(line) for line in parts["thoughts.json"].splitlines()]
        thoughts[1]["ForgottenDateTime"] = "2026-10-01T10:00:00Z"
        parts["thoughts.json"] = b"\n".join(json.dumps(a).encode() for a in thoughts)
    source = write_source(tmp_path, parts)
    with ZipFile(source) as archive, pytest.raises(AssertionError):
        scope(read_source(archive), archive)


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("excluded", [False, True])
@pytest.mark.parametrize("custom", [None, ""])
@pytest.mark.parametrize("name", ["display name", ""])
def test_raw_scope_retains_reviewed_empty_custom_metadata_and_false_unknown_flags(
    tmp_path, reverse, excluded, custom, name
):
    parts = duplicate_txt_parts(tmp_path)
    rows = [json.loads(line) for line in parts["attachments.json"].splitlines()]
    rows[-1].update(
        Name=name,
        IsUnreviewedRole=False,
        ThoughtTypeId=custom,
        LinkTypeId=custom,
        TypeId=custom,
    )
    if reverse:
        rows.reverse()
    parts["attachments.json"] = b"\n".join(json.dumps(a).encode() for a in rows)
    if excluded:
        thoughts = [json.loads(line) for line in parts["thoughts.json"].splitlines()]
        thoughts[1]["ForgottenDateTime"] = "2026-10-01T10:00:00Z"
        parts["thoughts.json"] = b"\n".join(json.dumps(a).encode() for a in thoughts)
    source = write_source(tmp_path, parts)
    with ZipFile(source) as archive:
        retained = scope(read_source(archive), archive)
    assert len(retained["attachments.json"]) == (1 if excluded else 5)
    if not excluded:
        actual = next(
            a for a in retained["attachments.json"] if a["Id"] == identity(3003)
        )
        assert actual["Name"] == name and actual["IsUnreviewedRole"] is False
        assert all(
            actual[field] == custom
            for field in ("ThoughtTypeId", "LinkTypeId", "TypeId")
        )


def test_oracle_checks_excluded_eligible_group_without_warning_or_payload_credit(
    tmp_path,
):
    from brz2obsidian.application.wiring import default_workflow
    from tests.local_acceptance.checker import check_vault

    parts = duplicate_txt_parts(tmp_path)
    thoughts = [json.loads(line) for line in parts["thoughts.json"].splitlines()]
    thoughts[1]["ForgottenDateTime"] = "2026-10-01T10:00:00Z"
    parts["thoughts.json"] = b"\n".join(json.dumps(a).encode() for a in thoughts)
    source = write_source(tmp_path, parts)
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "clean", result.issues
    assert result.receipt.published and result.receipt.verified
    summary = check_vault(source, vault)
    assert summary["warnings"] == summary["txt_gaps"] == 0
    assert summary["source_items"] == summary["payloads"] == summary["documents"] == 1


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("flag", [True, 0, False])
def test_whole_oracle_rejects_malformed_excluded_role_with_rehashed_receipt(
    tmp_path, reverse, flag
):
    import hashlib

    from brz2obsidian.application.wiring import default_workflow
    from brz2obsidian.contracts import Receipt
    from tests.local_acceptance.checker import check_vault, load_json
    from tests.local_acceptance.test_checker_v2 import rewrite_record

    parts = duplicate_txt_parts(tmp_path)
    thoughts = [json.loads(line) for line in parts["thoughts.json"].splitlines()]
    thoughts[1]["ForgottenDateTime"] = "2026-10-01T10:00:00Z"
    parts["thoughts.json"] = b"\n".join(json.dumps(a).encode() for a in thoughts)
    source = write_source(tmp_path, parts)
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault).model_dump(mode="json")
    assert result["outcome"] == "clean", result["issues"]
    check_vault(source, vault)
    record = load_json((vault / "migration-record.json").read_bytes())
    old_hash = record["source_identity"]["source_sha256"]
    rows = [json.loads(line) for line in parts["attachments.json"].splitlines()]
    rows[-1]["IsUnreviewedRole"] = flag
    if reverse:
        rows.reverse()
    parts["attachments.json"] = b"\n".join(json.dumps(a).encode() for a in rows)
    write_source(tmp_path, parts)
    new_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    assert new_hash != old_hash
    record["source_identity"]["source_sha256"] = new_hash
    report = vault / "MIGRATION REPORT.md"
    text = report.read_text(encoding="utf-8")
    if old_hash in text:
        report.write_text(text.replace(old_hash, new_hash), encoding="utf-8")
    rewrite_record(vault, record, result)
    Receipt.model_validate_json(json.dumps(result["receipt"]))
    if flag is False:
        assert check_vault(source, vault)["source_items"] == 1
    else:
        with pytest.raises(AssertionError, match="raw unique payload declaration"):
            check_vault(source, vault)


@pytest.mark.parametrize(
    "damage",
    [
        "collapsed_declaration",
        "collapsed_warning",
        "paired_length",
        "paired_evidence",
        "invented_bytes",
        "invented_reference",
    ],
)
def test_oracle_rejects_multiple_txt_semantic_lies_after_consistent_receipt_repair(
    tmp_path, damage
):
    from brz2obsidian.application.wiring import default_workflow
    from brz2obsidian.contracts import Receipt
    from tests.local_acceptance.checker import check_vault, load_json
    from tests.local_acceptance.test_checker_v2 import rewrite_record

    source = write_source(tmp_path, thirteen_txt_parts(tmp_path))
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault).model_dump(mode="json")
    assert result["outcome"] == "warnings", result["issues"]
    check_vault(source, vault)
    record = load_json((vault / "migration-record.json").read_bytes())
    first, second = (
        next(a for a in record["asset_targets"] if a["asset_id"] == identity(n))
        for n in (5004, 5005)
    )
    issue = next(i for i in record["issues"] if i["affected"] == [second["asset_id"]])
    if damage == "collapsed_declaration":
        record["asset_targets"].remove(second)
        evidence = next(
            e["records"]
            for e in record["original_evidence"]
            if e["key"] == "attachments.json"
        )
        evidence[:] = [a for a in evidence if a["Id"] != second["asset_id"]]
        record["issues"].remove(issue)
        record["source_accounting"]["entries"][:] = [
            e
            for e in record["source_accounting"]["entries"]
            if e["identity"] != second["evidence"][0]
        ]
    elif damage == "collapsed_warning":
        record["issues"].remove(issue)
        second["source_findings"].clear()
    elif damage == "paired_length":
        finding = second["source_findings"][0]
        observed = json.loads(finding["observed_json"])
        observed["declared_length"] = 17
        finding["observed_json"] = json.dumps(observed)
        issue["message"] = (
            "False paired observation. Observed: " + finding["observed_json"]
        )
    elif damage == "paired_evidence":
        second["evidence"] = list(first["evidence"])
        second["source_findings"][0]["evidence"] = list(
            first["source_findings"][0]["evidence"]
        )
        issue["evidence"] = list(first["source_findings"][0]["evidence"])
    elif damage == "invented_bytes":
        import hashlib

        path = "Attachments/invented.txt"
        (vault / path).parent.mkdir(exist_ok=True)
        (vault / path).write_bytes(b"invented source bytes")
        second.update(
            relative_path=path,
            availability="present",
            actual_length=21,
            actual_sha256=hashlib.sha256(b"invented source bytes").hexdigest(),
            resource_link=path,
        )
        record["counts"]["planned_assets"] += 1
        record["counts"]["present_assets"] += 1
        payload = "payload:" + identity(2) + "/shared.TXT"
        record["source_accounting"]["entries"].append(
            {
                "identity": payload,
                "disposition": "normalized",
                "references": [second["asset_id"]],
            }
        )
        record["original_evidence"].append(
            {
                "key": payload,
                "kind": "payload",
                "records": {
                    "member": identity(2) + "/shared.TXT",
                    "length": 21,
                    "sha256": second["actual_sha256"],
                },
            }
        )
    else:
        for field in ("source_references", "planned_references", "actual_references"):
            record["counts"][field] += 1
    rewrite_record(vault, record, result)
    Receipt.model_validate_json(json.dumps(result["receipt"]))
    assert (
        result["receipt"]["verified"]
        and result["receipt"]["counts"] == result["counts"]
    )
    with pytest.raises(AssertionError):
        check_vault(source, vault)

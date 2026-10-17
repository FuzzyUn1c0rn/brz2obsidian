import json
from zipfile import ZIP_STORED, ZipFile

import pytest

from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.cli import main
from brz2obsidian.contracts import Asset, Item, MigrationRefused, Relationship
from brz2obsidian.core import analyze
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


def change_record(parts, key, **updates):
    records = [
        json.loads(line)
        for line in parts["attachments.json"].splitlines()
        if line.strip()
    ]
    next(r for r in records if r["Id"] == key).update(updates)
    parts["attachments.json"] = "\n".join(json.dumps(r) for r in records).encode()


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

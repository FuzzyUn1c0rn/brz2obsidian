"""Physical repacking never hides changed scoped evidence or generated prose."""

import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.wiring import default_workflow
from tests.application.test_update_lifecycle import _seed, case_path, git

__all__ = ["case_path"]


def members(path):
    with ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def write_archive(path, content):
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.comment = b"Equivalent scoped bytes; different physical ZIP packing."
        for name, raw in reversed(tuple(content.items())):
            info = ZipInfo(name, date_time=(2001, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, raw)
    return path


def physical_files(root):
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_repacking_retains_bytes_but_changed_records_payload_and_prose_do_not(
    case_path,
):
    vault, archive = _seed(case_path)
    original_members = members(archive)
    repacked = write_archive(case_path / "repacked.brz", original_members)
    assert members(repacked) == original_members
    original_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    repacked_sha = hashlib.sha256(repacked.read_bytes()).hexdigest()
    assert repacked_sha != original_sha
    baseline = physical_files(case_path / "source")
    assert baseline["Attachments/22222222/Notes.md.original"] == b"Authored body.\r\n"
    original_record = json.loads(baseline["migration-record.json"])
    scoped = original_record["source_identity"]["snapshot_digest"]
    locator = (vault / ".brz2obsidian/locator.json").read_bytes()
    refs = git(vault, "for-each-ref", "--format=%(refname) %(objectname)")
    operations = Operations()
    equivalent = operations.prepare_update(vault, repacked)
    assert equivalent.status == "prepared_review" and equivalent.ready, equivalent.code
    prepared = equivalent.preparation
    assert prepared.retained_source_provenance
    assert prepared.observed_source.source_sha256 == repacked_sha
    assert prepared.observed_source.snapshot_digest == scoped
    assert physical_files(Path(prepared.payload_directory)) == baseline
    retained_record = json.loads(
        (Path(prepared.payload_directory) / "migration-record.json").read_bytes()
    )
    assert retained_record["source_identity"]["source_sha256"] == original_sha
    assert all(c.disposition == "no_change" for c in prepared.review.proposal.changes)
    applied = operations.apply_update(prepared)
    assert (applied.status, applied.publication) == (
        "no_content_change",
        "not_published",
    )
    assert applied.application is None and applied.checkpoint == prepared.locator
    assert applied.vault == str(vault) and applied.changes == equivalent.changes
    assert (vault / ".brz2obsidian/locator.json").read_bytes() == locator
    assert git(vault, "for-each-ref", "--format=%(refname) %(objectname)") == refs

    raw_records = dict(original_members)
    assert b'"number":1.5' in raw_records["meta.json"]
    raw_records["meta.json"] = raw_records["meta.json"].replace(
        b'"number":1.5', b'"number":1.50', 1
    )
    assert json.loads(raw_records["meta.json"]) == json.loads(
        original_members["meta.json"]
    )
    assert raw_records["meta.json"] != original_members["meta.json"]
    records_archive = write_archive(case_path / "changed-raw-record.brz", raw_records)
    changed_records = operations.prepare_update(vault, records_archive)
    assert changed_records.preparation is not None, changed_records.code
    assert not changed_records.preparation.retained_source_provenance
    assert changed_records.preparation.observed_source.snapshot_digest != scoped
    changed_record = next(
        s.incoming.data
        for s in changed_records.preparation.review.facts.subjects
        if s.item_id == "support:migration-record.json"
    )
    assert b'"number":1.50' in changed_record

    changed_members = dict(original_members)
    original_path = "22222222-2222-4222-8222-222222222222/Notes.md"
    assert changed_members[original_path] == b"Authored body.\r\n"
    changed_members[original_path] = b"Incoming body.\r\n"
    assert len(changed_members[original_path]) == len(original_members[original_path])
    payload_archive = write_archive(case_path / "changed-payload.brz", changed_members)
    changed_payload = operations.prepare_update(vault, payload_archive)
    assert changed_payload.preparation is not None, changed_payload.code
    assert not changed_payload.preparation.retained_source_provenance
    assert changed_payload.preparation.observed_source.snapshot_digest != scoped
    asset = next(
        s
        for s in changed_payload.preparation.review.facts.subjects
        if s.item_id == "33333333-3333-4333-8333-333333333333"
    )
    assert asset.incoming.data == b"Incoming body.\r\n"
    assert (
        hashlib.sha256(asset.incoming.data).hexdigest()
        == "4df1ce35b8c0dcf96134ba77d854740f213b8dab3d4ca6c72d022d6ff9c75886"
    )
    assert (vault / ".brz2obsidian/locator.json").read_bytes() == locator
    assert git(vault, "for-each-ref", "--format=%(refname) %(objectname)") == refs

    def prose(physical_sha):
        return (
            "\nSource fingerprint: "
            + physical_sha
            + "; scoped digest: "
            + scoped
            + "; collection: authored prose\n"
        ).encode()

    for root in (vault, case_path / "source"):
        (root / "Home — Entry thought.md").write_bytes(
            baseline["Home — Entry thought.md"] + prose(original_sha)
        )
    before = operations.read_checkpoint(vault)
    captured = operations.capture_checkpoint(
        vault,
        case_path / "source",
        vault_id="vault-280",
        import_id="import-280",
        identity=before.manifest.identity,
        admission=operations.inspect_history(vault).admission,
    )
    assert captured.status == "captured", captured.code
    workflow = default_workflow()
    delegate = workflow.renderer

    class ProseRenderer:
        def render(self, plan, metadata):
            rendered = delegate.render(plan, metadata)
            files = []
            for file in rendered.generated_files:
                if file.relative_path == "Home — Entry thought.md":
                    raw = file.content + prose(plan.source_identity.source_sha256)
                    file = file.model_copy(
                        update={
                            "content": raw,
                            "sha256": hashlib.sha256(raw).hexdigest(),
                        }
                    )
                files.append(file)
            return rendered.model_copy(update={"generated_files": tuple(files)})

    workflow.renderer = ProseRenderer()
    changed_prose = Operations(workflow=workflow).prepare_update(vault, repacked)
    assert changed_prose.preparation is not None, changed_prose.code
    assert changed_prose.preparation.observed_source.snapshot_digest == scoped
    assert not changed_prose.preparation.retained_source_provenance
    note = next(
        s
        for s in changed_prose.preparation.review.facts.subjects
        if s.item_id == "22222222-2222-4222-8222-222222222222"
    )
    assert note.current.content.data.endswith(prose(original_sha))
    assert note.incoming.data.endswith(prose(repacked_sha))

"""Historical source/renderer proof stays independent of authored current files."""

import hashlib
import json
from types import SimpleNamespace

import pytest

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.vault_contracts import VaultFile
from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.publication.vault_native import observe_file
from tests.application.test_minimal_workflow import PROPERTIES, make_archive
from tests.application.test_module_seams import METADATA
from tests.reconciliation.test_resolution import preflight

NOTE = "Home \u2014 Entry thought.md"
ORIGINAL = PROPERTIES + (
    b"# Entry thought\n\nAuthored body.\r\n\n"
    b"## Categories\n\n[[Categories.md|Browse categories]]\n"
)
CURRENT = ORIGINAL + b"\r\nLocal retained writing.\r\n"


def legacy_brz_case(root):
    archive = make_archive(root / "original.brz")
    workflow = default_workflow()
    workflow.metadata_factory = lambda: METADATA
    vault = root / "vault"
    converted = workflow.convert(archive, vault)
    assert converted.receipt is not None and converted.receipt.verified
    assert (vault / NOTE).read_bytes() == ORIGINAL
    (vault / NOTE).write_bytes(CURRENT)
    (vault / "Private.bin").write_bytes(b"\x00\xffPrivate retained bytes.\r\n")
    return Operations(workflow=workflow), vault, archive


def controlled_history(operations, vault, monkeypatch):
    history = SimpleNamespace(
        status="absent",
        checkpoint=None,
        admission=SimpleNamespace(
            vault=str(vault),
            status="supported",
            repository=SimpleNamespace(kind="root"),
            preflight=preflight(),
            findings=(),
            recovery_gaps=(),
            inventory_complete=True,
        ),
    )

    def inspect(*args, **kwargs):
        rows = []
        for path in sorted(p for p in vault.rglob("*") if p.is_file()):
            info, sha, _, identity = observe_file(vault, path, prefix_limit=0)
            rows.append(
                VaultFile(
                    path=path.relative_to(vault).as_posix(),
                    mode="100644",
                    size=info.st_size,
                    sha256=sha,
                    identity=identity,
                    tracked=True,
                    excluded=False,
                    exclusion=None,
                )
            )
        history.admission.inventory = tuple(rows)
        return history

    monkeypatch.setattr(operations, "inspect_history", inspect)


@pytest.mark.parametrize(
    "evidence",
    (
        "matching",
        "wrong_archive_digest",
        "changed_mapping",
        "unavailable_renderer",
        "unavailable_profile",
    ),
)
def test_known_original_requires_complete_archive_renderer_and_record_proof(
    tmp_path, monkeypatch, evidence
):
    operations, vault, archive = legacy_brz_case(tmp_path)
    controlled_history(operations, vault, monkeypatch)
    record_path = vault / "migration-record.json"
    original_record = record_path.read_bytes()
    old = json.loads(original_record)
    assert (
        old["source_identity"]["source_sha256"]
        == hashlib.sha256(archive.read_bytes()).hexdigest()
    )
    if evidence == "wrong_archive_digest":
        old["source_identity"]["source_sha256"] = "0" * 64
    elif evidence == "changed_mapping":
        old["item_targets"][0]["relative_path"] = "Different.md"
    elif evidence == "unavailable_renderer":
        old["run_metadata"]["renderer_version"] = "unavailable"
    elif evidence == "unavailable_profile":
        old["profile_version"] = "unavailable"
    record_path.write_text(json.dumps(old))
    before = {
        p.relative_to(vault).as_posix(): p.read_bytes()
        for p in vault.rglob("*")
        if p.is_file()
    }
    result = operations.prepare_onboarding(vault, archive, original_source=archive)
    assert result.preparation is not None, result
    facts = result.preparation.review.facts
    note = next(
        s for s in facts.subjects if s.item_id == "22222222-2222-4222-8222-222222222222"
    )
    assert note.current.content.data == CURRENT
    if evidence == "matching":
        assert (
            note.baseline.status == "known" and note.baseline.content.data == ORIGINAL
        )
        assert facts.format_operation.recorded_generation == "supported"
        assert facts.format_operation.established_baseline is not None
        assert (
            facts.baseline_identity.collection_id
            == "11111111-1111-4111-8111-111111111111"
        )
        assert facts.baseline_identity.module_id == "thebrain-brz"
        assert facts.baseline_identity.profile_id == "thebrain-format5-reviewed"
        assert facts.baseline_identity.profile_version == "10"
        assert facts.baseline_identity.output_format == 7
        assert (
            facts.baseline_identity.settings_digest == hashlib.sha256(b"{}").hexdigest()
        )
        retained_record = next(
            s for s in facts.subjects if s.item_id == "support:migration-record.json"
        )
        assert retained_record.baseline.content.data == original_record
        assert retained_record.baseline.content.data != before["migration-record.json"]
        asset = next(s for s in facts.subjects if s.facet == "asset")
        assert (
            hashlib.sha256(asset.baseline.content.data).hexdigest()
            == "5ffa7716ee53174debb9b0ddfec17efa574c4e494b4bd1a321a0378c29016229"
        )
    else:
        assert all(
            s.baseline.status == "unknown" and s.baseline.content is None
            for s in facts.subjects
        )
        assert facts.format_operation.established_baseline is None
    assert {
        p.relative_to(vault).as_posix(): p.read_bytes()
        for p in vault.rglob("*")
        if p.is_file()
    } == before


@pytest.mark.parametrize("forged", (False, True))
def test_reobserved_originals_are_qualified_not_caller_pristine_flags(
    tmp_path, monkeypatch, forged
):
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.core import prepare_review

    operations, vault, archive = legacy_brz_case(tmp_path)
    controlled_history(operations, vault, monkeypatch)
    offered = operations.prepare_onboarding(vault, archive, original_source=archive)
    assert offered.preparation is not None, offered
    prepared = offered.preparation
    if forged:
        facts = prepared.review.producer_facts
        fake = ExactContent(data=CURRENT)
        facts = facts.model_copy(
            update={
                "subjects": tuple(
                    s.model_copy(
                        update={
                            "baseline": s.baseline.model_copy(update={"content": fake}),
                            "structure": None,
                        }
                    )
                    if s.item_id == "22222222-2222-4222-8222-222222222222"
                    else s
                    for s in facts.subjects
                ),
                "format_operation": facts.format_operation.model_copy(
                    update={
                        "established_baseline": facts.format_operation.established_baseline.model_copy(
                            update={
                                "outputs": tuple(
                                    o.model_copy(update={"content": fake})
                                    if o.item_id
                                    == "22222222-2222-4222-8222-222222222222"
                                    else o
                                    for o in facts.format_operation.established_baseline.outputs
                                ),
                            }
                        ),
                    }
                ),
            }
        )
        prepared = prepared.model_copy(
            update={
                "review": prepare_review(facts, preflight=prepared.review.preflight)
            }
        )
    refreshed = operations.refresh_update(prepared)
    assert refreshed.preparation is not None, refreshed
    note = next(
        s
        for s in refreshed.preparation.review.facts.subjects
        if s.item_id == "22222222-2222-4222-8222-222222222222"
    )
    assert note.baseline.status == "known" and note.baseline.content.data == ORIGINAL
    assert note.current.content.data == CURRENT
    assert refreshed.preparation.original_source_ref == str(archive.absolute())
    assert refreshed.generation == (2 if forged else 1)
    assert refreshed.status == ("stale_review" if forged else "prepared_review")

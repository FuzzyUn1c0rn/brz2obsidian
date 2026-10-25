"""Qualified retained ownership at native read and publication boundaries."""

import hashlib
import json
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from brz2obsidian.application.checkpoint_payload_contracts import (
    CheckpointPayloadRequest,
)
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_facts import output_identity
from brz2obsidian.core import prepare_review
from tests.application.test_update_lifecycle_admission import NOTE, payload
from tests.application.test_vault_checkpoints import git, user_state


def owned_history_case():
    root = Path(tempfile.mkdtemp(prefix="brz2obsidian-283-"))
    owner = uuid4().hex
    marker = {
        "owner": owner,
        "root": str(root.resolve()),
        "base": str(Path(tempfile.gettempdir()).resolve()),
    }
    (root / ".fixture-owner.json").write_text(json.dumps(marker), encoding="utf-8")
    evidence = (
        Path(__file__).resolve().parents[2] / "tmp/issue-283-application/fixtures"
    )
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / (owner + ".json")).write_text(json.dumps(marker), encoding="utf-8")
    vault, source = root / "vault", root / "converted"
    vault.mkdir()
    source.mkdir()
    original = payload("a", "Original independently generated A.")
    original["Assets/remove.bin"] = b"\x00historical source A\xff"
    record = json.loads(original["migration-record.json"])
    record["asset_targets"] = [
        {"asset_id": "remove-asset", "relative_path": "Assets/remove.bin"}
    ]
    original["migration-record.json"] = json.dumps(record).encode()
    for path, raw in original.items():
        for directory in (vault, source):
            destination = directory / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    git(vault, "add", ".")
    git(vault, "commit", "-qm", "Independent generated baseline and user index")
    return vault, source, original


def test_native_cleanup_ownership_reads_qualified_ancestor_without_changing_current_source():
    vault, source, original = owned_history_case()
    operations = Operations()
    first = operations.capture_checkpoint(
        vault,
        source,
        vault_id="cleanup-vault",
        import_id="cleanup-import",
        identity=output_identity(json.loads(original["migration-record.json"])),
        admission=operations.inspect_history(vault).admission,
    )
    assert first.status == "captured", first.code
    assert first.locator.generation == 1
    (source / "Assets/remove.bin").unlink()
    for version, text in (
        ("b", "Unrelated source B."),
        ("c", "Later unrelated source C."),
    ):
        next_payload = payload(version, text)
        for path, raw in next_payload.items():
            (source / path).write_bytes(raw)
        captured = operations.capture_checkpoint(
            vault,
            source,
            vault_id="cleanup-vault",
            import_id="cleanup-import",
            identity=output_identity(json.loads(next_payload["migration-record.json"])),
            admission=operations.inspect_history(vault).admission,
        )
        assert captured.status == "captured", captured.code
    source_bytes = {
        p.relative_to(source).as_posix(): p.read_bytes()
        for p in source.rglob("*")
        if p.is_file()
    }
    before = user_state(vault)
    with operations.inspect_update_inputs(vault) as observed:
        current = observed.history.checkpoint
        assert current.locator.generation == 3
        assert all(row.path != "Assets/remove.bin" for row in current.manifest.source)
        owners = observed.read_attachment_ownership(
            locator=current.locator, paths=("Assets/remove.bin",)
        )
        assert len(owners) == 1
        proof = owners[0]
        assert proof.association_id == first.locator.association.association_id
        assert proof.checkpoint_commit == first.commit and proof.generation == 1
        assert proof.identity.item_id == "remove-asset" and proof.facet == "asset"
        assert (
            proof.source_path == "Assets/remove.bin"
            and proof.source_version == "a" * 64
        )
        assert (
            proof.mapping_sha256
            == hashlib.sha256(original["migration-record.json"]).hexdigest()
        )
        assert (
            proof.payload_sha256
            == hashlib.sha256(b"\x00historical source A\xff").hexdigest()
        )
        assert (
            proof.payload_size == len(b"\x00historical source A\xff")
            and proof.payload_mode == "100644"
        )
        stale = observed.read_payload(
            locator=first.locator,
            role="source",
            requests=(CheckpointPayloadRequest(path=NOTE, offset=0, limit=1),),
            byte_limit=1,
        )
        assert stale.status == "refused" and stale.code == "stale_locator"
        assert stale.chunks == ()
    assert user_state(vault) == before
    assert {
        p.relative_to(source).as_posix(): p.read_bytes()
        for p in source.rglob("*")
        if p.is_file()
    } == source_bytes
    assert (vault / "Assets/remove.bin").read_bytes() == b"\x00historical source A\xff"


def test_native_cleanup_capture_rederives_witness_before_any_history_write():
    vault, source, original = owned_history_case()
    operations = Operations()
    first = operations.capture_checkpoint(
        vault,
        source,
        vault_id="cleanup-vault",
        import_id="cleanup-import",
        identity=output_identity(json.loads(original["migration-record.json"])),
        admission=operations.inspect_history(vault).admission,
    )
    assert first.status == "captured", first.code
    offered = operations.prepare_attachment_cleanup(vault)
    assert offered.preparation is not None, offered.code
    prepared = offered.preparation
    with operations.inspect_update_inputs(vault) as observed:
        (proof,) = observed.read_attachment_ownership(
            locator=observed.history.checkpoint.locator, paths=("Assets/remove.bin",)
        )
    before = {
        p.relative_to(vault).as_posix(): p.read_bytes()
        for p in vault.rglob("*")
        if p.is_file()
    }
    before_user = user_state(vault)

    def capture(candidate):
        facts = prepared.review.producer_facts
        facts = facts.model_copy(
            update={
                "subjects": tuple(
                    s.model_copy(
                        update={
                            "attachment": s.attachment.model_copy(
                                update={"retained_ownership": candidate}
                            )
                        }
                    )
                    if s.item_id == "remove-asset"
                    else s
                    for s in facts.subjects
                )
            }
        )
        review = prepare_review(facts, preflight=prepared.review.preflight)
        binding = operations.observe_reviewed_source(prepared.payload_directory, review)
        return operations.capture_checkpoint(
            vault,
            source,
            vault_id="cleanup-vault",
            import_id="cleanup-import",
            identity=review.facts.baseline_identity,
            admission=operations.inspect_history(vault).admission,
            review=review,
            review_source=prepared.payload_directory,
            source_binding=binding,
            observed_source=prepared.observed_source,
        )

    for label, changes in (
        ("association", {"association_id": "f" * 64}),
        ("unreachable", {"checkpoint_commit": "f" * 40}),
        (
            "identity",
            {"identity": proof.identity.model_copy(update={"item_id": "other-asset"})},
        ),
        ("payload", {"payload_sha256": "f" * 64}),
    ):
        refused = capture(proof.model_copy(update=changes))
        (vault.parent / ("refused-" + label + ".json")).write_text(
            refused.model_dump_json(), encoding="utf-8"
        )
        assert (
            refused.status == "refused" and refused.code == "cleanup_ownership_unbound"
        ), (label, refused.code)
        assert not refused.objects_written and refused.object_storage == "not_started"
        assert {
            p.relative_to(vault).as_posix(): p.read_bytes()
            for p in vault.rglob("*")
            if p.is_file()
        } == before
        assert user_state(vault) == before_user
    saved = capture(proof)
    assert saved.status == "captured" and saved.locator.generation == 2, saved.code
    assert operations.read_checkpoint(vault).status == "valid"
    assert user_state(
        vault, owned_ref=first.ref
    ) == user_state_before_without_owned_ref(before_user, first.ref)


def user_state_before_without_owned_ref(state, owned_ref):
    return state | {
        "refs": tuple(
            row for row in state["refs"] if row.split(b" ", 1)[0] != owned_ref.encode()
        )
    }


@pytest.mark.parametrize("outcome", ("removed", "restored", "no-op", "disassociated"))
def test_completed_cleanup_disposition_does_not_reown_manual_path(outcome):
    from brz2obsidian.application.checkpoint_contracts import CheckpointFile
    from brz2obsidian.application.vault_update_contracts import (
        VaultOperationIntent,
        VaultOperationReceipt,
        VaultPathMetadata,
        VaultRecoveryIntent,
    )
    from brz2obsidian.contracts import (
        ImportedItemIdentity,
        RetainedAttachmentOwnership,
    )
    from brz2obsidian.publication.attachment_ownership import (
        interpret_attachment_disposition,
    )
    from tests.reconciliation.test_attachment_cleanup import cleanup_request
    from tests.reconciliation.test_resolution import preflight

    plan = prepare_review(cleanup_request(), preflight=preflight())
    subject = plan.facts.subjects[0]
    proof = RetainedAttachmentOwnership(
        schema_id="brz2obsidian.retained-attachment-ownership",
        schema_version=1,
        association_id="a" * 64,
        checkpoint_commit="1" * 40,
        generation=1,
        identity=ImportedItemIdentity(
            collection_id=plan.facts.incoming_identity.collection_id,
            module_id=plan.facts.incoming_identity.module_id,
            item_id=subject.item_id,
        ),
        facet=subject.facet,
        source_path="Assets/data.bin",
        source_version="source:A",
        mapping_sha256=hashlib.sha256(b"literal mapping A").hexdigest(),
        payload_sha256=hashlib.sha256(b"\x00original").hexdigest(),
        payload_size=len(b"\x00original"),
        payload_mode="100644",
    )
    row = CheckpointFile(
        path="Assets/data.bin",
        mode="100644",
        size=9,
        sha256=hashlib.sha256(b"\x00authored").hexdigest(),
        object_id="8" * 40,
    )
    metadata = VaultPathMetadata(
        path=row.path, mode=0, attributes=0, security="literal security"
    )
    removes = outcome in ("removed", "restored")
    original = VaultOperationIntent(
        schema_id="brz2obsidian.vault-operation-intent",
        schema_version=1,
        operation_id="a" * 32,
        kind="apply",
        generation=2,
        direction="finish",
        association_id=proof.association_id,
        prepared_commit="2" * 40,
        before=(row,),
        proposed=() if removes else (row,),
        affected_paths=(row.path,) if removes else (),
        protected_paths=() if removes else (row.path,),
        before_metadata=(metadata,) if removes else (),
        result_metadata=(),
        created_directories=(),
    )
    final = original
    if outcome == "restored":
        final = VaultRecoveryIntent(
            **(
                original.model_dump()
                | {
                    "schema_id": "brz2obsidian.vault-recovery-intent",
                    "generation": 4,
                    "direction": "restore",
                    "prepared_commit": "6" * 40,
                    "before": (),
                    "proposed": (row,),
                    "before_metadata": (),
                    "result_metadata": (metadata,),
                    "origin_intent_commit": "4" * 40,
                    "previous_operation_commit": "5" * 40,
                    "review_generation": 3,
                }
            )
        )
    receipt = VaultOperationReceipt(
        schema_id="brz2obsidian.vault-operation-receipt",
        schema_version=1,
        operation_id=original.operation_id,
        kind="apply",
        generation=final.generation,
        direction=final.direction,
        status="restored"
        if outcome == "restored"
        else "applied"
        if removes
        else "no_content_change",
        intent_commit="4" * 40,
        prepared_commit=final.prepared_commit,
        result_commit="7" * 40,
        published_paths=final.affected_paths,
    )
    if outcome == "disassociated":
        from brz2obsidian.core import reconcile
        from tests.reconciliation.test_identity import association

        entry = next(
            e for e in plan.facts.identity_inventory if e.current.path == row.path
        )
        other = entry.model_copy(
            update={
                "entry_id": "other-bound-entry",
                "current": entry.current.model_copy(
                    update={"path": "Assets/other.bin"}
                ),
                "target": entry.target.model_copy(
                    update={"normalized_path": "assets/other.bin"}
                ),
            }
        )
        facts = plan.producer_facts.model_copy(
            update={
                "identity_inventory": (*plan.producer_facts.identity_inventory, other)
            }
        )
        offered = next(c for c in reconcile(facts).changes if c.facet == subject.facet)
        decision = association(
            facts, offered.identity_review, other.entry_id, (entry.entry_id,)
        )
        plan = prepare_review(
            facts.model_copy(update={"association_decisions": (decision,)}),
            preflight=preflight(),
        )
        change = next(c for c in plan.proposal.changes if c.facet == subject.facet)
        assert change.identity_review.disassociate_entry_ids == (entry.entry_id,)
        assert change.identity_review.provenance == "explicit_user"

    # These pure native values describe completed disposition only. The native
    # reader must independently bind their receipt graph and canonical review.
    retained = interpret_attachment_disposition(
        (proof,), original=original, final=final, receipt=receipt, plan=plan
    )
    assert retained == (() if outcome in ("removed", "disassociated") else (proof,))
    # A later manual file at the same name never creates a new historical owner.
    assert (
        interpret_attachment_disposition(
            (), original=original, final=final, receipt=receipt, plan=plan
        )
        == ()
    )

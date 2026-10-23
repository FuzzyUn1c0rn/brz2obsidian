"""A real S1 mapping/path choice and declined restoration survive checkpointing."""

import hashlib

from brz2obsidian.application.operations import Operations
from brz2obsidian.contracts import ClassificationMapping, IdentityTargetFacts
from brz2obsidian.core import prepare_review, resolve_review
from tests.application.test_vault_checkpoints import (
    capture,
    fixture_case,
    git,
    inspect,
    read_history,
    user_state,
)
from tests.reconciliation.test_absence import facts_for
from tests.reconciliation.test_identity import inventory_item, with_subjects
from tests.reconciliation.test_memberships import membership_request, target
from tests.reconciliation.test_resolution import (
    action,
    preflight,
    with_observed_targets,
)


def test_mapping_identity_and_declined_restoration_survive_checkpoint_unready():
    current = b"---\ncategories: []\n---\nAuthored opening.\r\n"
    incoming = b'---\ncategories: ["[[B]]"]\n---\nAuthored opening.\r\n'
    mapping = ClassificationMapping(
        schema_id="brz2obsidian.classification-mapping",
        schema_version=1,
        classification_id="source:b",
        target_id="b",
        kind="category",
        source_label="B",
    )
    category = target("b", "category", "[[B]]")
    facts = membership_request(
        current,
        current,
        incoming,
        targets=(category,),
        incoming_mappings=(mapping,),
    )
    moved = inventory_item(
        "moved-opening", "entry:opening", "Authored/Opening.md", current
    )
    opening = facts.subjects[0].model_copy(update={"current": moved.current})
    absent = facts_for(
        original=b"deleted-v1\n", incoming=b"deleted-v2\n", existence="absent"
    )
    deleted_target = IdentityTargetFacts(
        normalized_path="notes/deleted.md", containment="contained", status="safe"
    )
    deleted = absent.subjects[0].model_copy(
        update={
            "item_id": "entry:deleted",
            "title": "Deleted",
            "path": "Notes/Deleted.md",
            "current": absent.subjects[0].current.model_copy(
                update={"path": "Notes/Deleted.md"}
            ),
            "source_target": deleted_target,
        }
    )
    deleted_entry = absent.identity_inventory[0].model_copy(
        update={
            "entry_id": "deleted-entry",
            "title": "Deleted",
            "identity": absent.identity_inventory[0].identity.model_copy(
                update={"item_id": "entry:deleted"}
            ),
            "current": deleted.current,
            "target": deleted_target,
        }
    )
    facts = with_subjects(facts, (opening, deleted), (moved, deleted_entry))
    facts = with_observed_targets(facts, (category,))
    plan = prepare_review(facts, preflight=preflight())
    assert {requirement.domain for requirement in plan.requirements} == {
        "mapping",
        "restoration",
    }
    assert plan.proposal.changes[0].identity_review.selected_entry_id == "moved-opening"
    assert plan.proposal.changes[0].target_path == "Authored/Opening.md"

    # Exercise a producer decision before approvals; the selected existing path
    # is distinct from the incoming source path and must survive history replay.
    kept_path = resolve_review(
        plan,
        action(
            plan,
            domain="rename",
            choice="keep_path",
            decision_id="memory:keep-authored-path",
        ),
    )
    assert kept_path.status == "accepted", kept_path.code
    assert not kept_path.plan.ready
    kept_mapping = resolve_review(
        kept_path.plan,
        action(
            kept_path.plan,
            domain="mapping",
            choice="current",
            decision_id="memory:keep-mapping",
        ),
    )
    assert kept_mapping.status == "accepted", kept_mapping.code
    decline = resolve_review(
        kept_mapping.plan,
        action(
            kept_mapping.plan,
            kept_mapping.plan.proposal.changes[1],
            domain="restoration",
            choice="decline_restoration",
            decision_id="memory:decline-deleted",
        ),
    )
    assert decline.status == "accepted", decline.code
    assert decline.plan.ready

    vault, source = fixture_case()
    for directory in (
        vault / "Authored",
        vault / "Targets",
        source / "Notes",
        source / "Targets",
    ):
        directory.mkdir()
    (vault / "Authored/Opening.md").write_bytes(current)
    (vault / "Targets/b.md").write_bytes(b"Target body")
    (source / "Notes/Opening.md").write_bytes(incoming)
    (source / "Notes/Deleted.md").write_bytes(b"deleted-v2\n")
    (source / "Targets/b.md").write_bytes(b"Target body")
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    git(vault, "add", ".")
    git(vault, "commit", "-qm", "independent authored state")
    (vault / "unrelated.bin").write_bytes(b"\x00\xffunrelated")
    before = user_state(vault)
    operations = Operations()
    captured = capture(
        operations,
        vault,
        source,
        vault_id="mapping-memory-vault",
        import_id="mapping-memory-import",
        identity=facts.incoming_identity,
        admission=inspect(operations, vault),
        review=decline.plan,
    )
    assert captured.status == "captured", captured.code
    assert captured.history_retained is True
    assert captured.authored_files_changed is False
    reopened = read_history(operations, vault)
    assert reopened.status == "valid", reopened.code
    assert reopened.review.ready is False
    assert reopened.review.readiness == "revalidation_required"
    loaded = reopened.review.saved.plan
    assert loaded == decline.plan
    assert loaded.ready is True  # Historical approval is not current readiness.
    assert [(event.domain, event.choice) for event in loaded.actions] == [
        ("rename", "keep_path"),
        ("mapping", "current"),
        ("restoration", "decline_restoration"),
    ]
    assert loaded.producer_facts.rename_decisions[0].choice == "keep_path"
    observed_identity = loaded.facts.identity_inventory[0].identity
    assert (
        observed_identity.collection_id,
        observed_identity.module_id,
        observed_identity.item_id,
    ) == ("folio:collection", "synthetic-folio", "entry:opening")
    assert loaded.facts.identity_inventory[0].current.path == "Authored/Opening.md"
    (retained_mapping,) = loaded.facts.subjects[0].structure.incoming_mappings
    assert (
        retained_mapping.classification_id,
        retained_mapping.target_id,
        retained_mapping.kind,
        retained_mapping.source_label,
    ) == ("source:b", "b", "category", "B")
    assert [
        (approval.domain, approval.target_path) for approval in loaded.approvals
    ] == [
        ("mapping", "Authored/Opening.md"),
        ("restoration", "Notes/Deleted.md"),
    ]
    assert loaded.approvals[0].result.data == current
    declined = loaded.approvals[1]
    assert declined.result is None and declined.source_accepted is False
    memory = declined.source_memory
    assert (
        memory.collection_id,
        memory.module_id,
        memory.item_id,
        memory.facet,
        memory.review_domain,
        memory.choice,
    ) == (
        "folio:collection",
        "synthetic-folio",
        "entry:deleted",
        "content",
        "content",
        "decline_restoration",
    )
    assert memory.reviewed_incoming.data == b"deleted-v2\n"
    assert memory.source_version == hashlib.sha256(b"deleted-v2\n").hexdigest()
    assert memory.provenance.decision_id == "memory:decline-deleted"
    assert [entry.path for entry in reopened.manifest.source] == [
        "Notes/Deleted.md",
        "Notes/Opening.md",
        "Targets/b.md",
    ]
    assert [entry.path for entry in reopened.manifest.vault] == [
        "Authored/Opening.md",
        "Targets/b.md",
        "unrelated.bin",
    ]
    baseline_digest = hashlib.sha256(b"deleted-v1\n").hexdigest()
    assert (
        git(
            vault,
            "cat-file",
            "blob",
            captured.commit + ":review-content/" + baseline_digest,
        )
        == b"deleted-v1\n"
    )
    assert (vault / "Authored/Opening.md").read_bytes() == current
    assert not (vault / "Notes/Deleted.md").exists()
    assert user_state(vault, owned_ref=captured.ref) == before

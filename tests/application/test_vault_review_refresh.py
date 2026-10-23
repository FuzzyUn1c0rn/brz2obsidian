"""Selective revalidation of genuine reviews retained in production Git history."""

import hashlib
import json
from pathlib import Path

from brz2obsidian.application.operations import Operations
from brz2obsidian.contracts import ExactContent, ReviewPlan
from brz2obsidian.core import prepare_review, refresh_review, resolve_review, resume_review
from tests.application.test_vault_checkpoints import user_state
from tests.application.test_vault_recovery_process import (
    _AFTER,
    _BEFORE,
    _assert_user_state,
    _two_note_case,
)
from tests.reconciliation.test_resolution import action, with_review_links


def test_persisted_review_reopens_then_invalidates_only_the_actually_edited_note():
    vault, source, plan_path, before, checkpoint_ref = _two_note_case()
    operations = Operations()
    original = ReviewPlan.model_validate_json(plan_path.read_bytes())
    observed = operations.inspect_history(vault)
    assert observed.status == "intact" and observed.admission.status == "supported"
    baseline = operations.capture_checkpoint(
        vault,
        source,
        vault_id="vault-one",
        import_id="import-one",
        identity=original.facts.incoming_identity,
        admission=observed.admission,
    )
    assert baseline.status == "captured", baseline.code
    observed = operations.inspect_history(vault)
    assert observed.status == "intact" and observed.admission.status == "supported"
    assert observed.checkpoint.review is None
    baseline_manifest = observed.checkpoint.manifest
    for path, content in _BEFORE.items():
        assert (vault / path).read_bytes() == content
        row = next(row for row in observed.admission.inventory if row.path == path)
        assert (row.size, row.sha256) == (
            len(content), hashlib.sha256(content).hexdigest()
        )
        assert (source / path).read_bytes() == _AFTER[path]
    reviewed = prepare_review(original.facts, preflight=observed.admission.preflight)
    previous = baseline.commit
    for path in ("Notes/Opening.md", "Notes/Closing.md"):
        change = next(
            row for row in reviewed.proposal.changes if row.target_path == path
        )
        chosen = resolve_review(
            reviewed,
            action(
                reviewed,
                change,
                choice="current",
                decision_id="persisted:" + change.item_id,
            ),
        )
        assert chosen.status == "accepted", chosen.code
        reviewed = chosen.plan
        if len(reviewed.approvals) == 1:
            first_memo = operations.capture_checkpoint(
                vault,
                source,
                vault_id="vault-one",
                import_id="import-one",
                identity=reviewed.facts.incoming_identity,
                admission=observed.admission,
                review=reviewed,
            )
            assert first_memo.status == "captured", first_memo.code
            partial = operations.read_checkpoint(vault)
            assert partial.review.ready is False
            observed = operations.inspect_history(vault)
            continued = resume_review(
                partial.review,
                reviewed.facts.model_copy(
                    update={"generation": reviewed.facts.generation + 1}
                ),
                preflight=observed.admission.preflight,
            )
            assert continued.status == "resumed", continued.code
            assert continued.plan.approvals == reviewed.approvals
            assert not continued.plan.ready
            reviewed = continued.plan
            previous = first_memo.commit
    assert reviewed.ready and len(reviewed.approvals) == 2
    captured = operations.capture_checkpoint(
        vault,
        source,
        vault_id="vault-one",
        import_id="import-one",
        identity=reviewed.facts.incoming_identity,
        admission=observed.admission,
        review=reviewed,
    )
    assert captured.status == "captured", captured.code
    reopened = operations.read_checkpoint(vault)
    assert reopened.status == "valid" and reopened.locator.commit == captured.commit
    assert reopened.review.ready is False
    assert reopened.review.saved.plan == reviewed
    memo_fields = {
        "generation", "previous", "semantic_fingerprint", "review_content",
        "review_object", "review_size", "review_sha256",
    }
    prior_roles = baseline_manifest.model_dump(mode="json", exclude=memo_fields)
    reopened_roles = reopened.manifest.model_dump(mode="json", exclude=memo_fields)
    assert prior_roles == reopened_roles
    assert prior_roles["boundary"] == "local"
    assert reopened.locator.association == observed.checkpoint.locator.association
    assert reopened.manifest.previous == previous
    fresh = operations.inspect_history(vault)
    assert fresh.status == "intact" and fresh.admission.status == "supported"
    unchanged_facts = reviewed.facts.model_copy(
        update={"generation": reviewed.proposal.generation + 1}
    )
    resumed = resume_review(
        reopened.review, unchanged_facts, preflight=fresh.admission.preflight
    )
    evidence = {
        "captured_commit": captured.commit,
        "reopened_commit": reopened.locator.commit,
        "inventory_unchanged": fresh.admission.inventory == observed.admission.inventory,
        "retained_roles_unchanged": prior_roles == reopened_roles,
        "baseline_commit": baseline.commit,
        "retained_roles": prior_roles,
        "preflight_delta": {
            key: [value, fresh.admission.preflight.model_dump(mode="json")[key]]
            for key, value in reviewed.preflight.model_dump(mode="json").items()
            if value != fresh.admission.preflight.model_dump(mode="json")[key]
        },
        "expected_decisions": [row.decision_id for row in reviewed.approvals],
        "actual_decisions": [row.decision_id for row in resumed.plan.approvals]
        if resumed.plan else None,
        "resume_status": resumed.status,
        "resume_code": resumed.code,
    }
    directory = Path(__file__).resolve().parents[2] / "tmp/issue-278/selective-refresh"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / (vault.parent.name + ".json")).write_text(json.dumps(evidence, indent=2))
    assert resumed.status == "resumed", evidence
    assert resumed.plan.approvals == reviewed.approvals, evidence
    assert resumed.ready

    later = b"opening authored\r\nlater writing\n"
    (vault / "Notes/Opening.md").write_bytes(later)
    changed_observation = operations.inspect_history(vault)
    assert changed_observation.status == "intact"
    row = next(
        row for row in changed_observation.admission.inventory
        if row.path == "Notes/Opening.md"
    )
    assert (row.size, row.sha256) == (len(later), hashlib.sha256(later).hexdigest())
    facts = resumed.plan.facts
    subjects = tuple(
        subject.model_copy(update={
            "current": subject.current.model_copy(update={
                "content": ExactContent(data=(vault / subject.path).read_bytes())
            })
        })
        for subject in facts.subjects
    )
    current = {subject.path: subject.current for subject in subjects}
    changed_facts = with_review_links(facts.model_copy(update={
        "generation": facts.generation + 1,
        "link_context": None,
        "subjects": subjects,
        "identity_inventory": tuple(
            entry.model_copy(update={"current": current[entry.current.path]})
            for entry in facts.identity_inventory
        ),
    }))
    refreshed = refresh_review(
        resumed.plan, changed_facts, preflight=changed_observation.admission.preflight
    )
    assert refreshed.status == "accepted", refreshed.code
    closing = next(row for row in reviewed.approvals if row.target_path == "Notes/Closing.md")
    assert refreshed.plan.approvals == (closing,)
    changes = {row.change_id: row for row in refreshed.plan.proposal.changes}
    assert [changes[row.change_id].target_path for row in refreshed.plan.requirements] == [
        "Notes/Opening.md"
    ]
    assert not refreshed.plan.ready
    semantic = operations.capture_checkpoint(
        vault,
        source,
        vault_id="vault-one",
        import_id="import-one",
        identity=changed_facts.incoming_identity,
        admission=changed_observation.admission,
    )
    assert semantic.status == "captured", semantic.code
    changed_history = operations.inspect_history(vault)
    assert changed_history.status == "intact"
    assert changed_history.checkpoint.review is None
    assert changed_history.checkpoint.manifest.previous == captured.commit
    assert (
        changed_history.admission.preflight.state_fingerprint
        != changed_observation.admission.preflight.state_fingerprint
    )
    advanced = refresh_review(
        refreshed.plan,
        changed_facts.model_copy(update={"generation": changed_facts.generation + 1}),
        preflight=changed_history.admission.preflight,
    )
    assert advanced.status == "accepted", advanced.code
    assert advanced.plan.approvals == ()
    assert not advanced.plan.ready
    assert (vault / "Notes/Opening.md").read_bytes() == later
    assert (vault / "Notes/Closing.md").read_bytes() == b"closing authored\r\n"
    assert (vault / "Unrelated.bin").read_bytes() == b"protected\0\xff"
    after = user_state(vault)
    _assert_user_state(before, after, allowed_refs=frozenset((checkpoint_ref.encode(),)))
    assert after["authored"] == {**before["authored"], "Notes/Opening.md": later}

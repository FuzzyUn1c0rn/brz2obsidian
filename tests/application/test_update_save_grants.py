"""Native Save requires the current consent for the canonical selected bytes."""

from brz2obsidian.application.vault_contracts import VaultSubject
from brz2obsidian.contracts import ExactContent
from brz2obsidian.core import resolve_review, validate_review
from brz2obsidian.obsidian import inspect_text_candidate
from tests.application.test_attachment_cleanup_lifecycle import user_git
from tests.application.test_vault_apply import _ready_case
from tests.application.test_vault_checkpoints import git, user_state
from tests.reconciliation.test_resolution import action


def test_native_save_refuses_stale_storage_accept_until_current_bytes_are_consented():
    vault, source, operations, reviewed, before = _ready_case(storage_transform=True)
    facts = reviewed.producer_facts
    candidate = inspect_text_candidate(
        ExactContent(data=b"Different reviewed text\n"),
        identity=facts.identity_inventory[0].identity,
        target=facts.subjects[0].source_target,
        output_format=7,
        source_path="Notes/Opening.md",
        document_id="review:opening",
        path_mode="vault",
        link_targets=(),
        link_target_facts=(),
        link_inventory="complete",
    )
    changed = resolve_review(
        reviewed,
        action(
            reviewed,
            decision_id="edited-after-storage-accept",
            choice="edited",
            candidate=candidate,
        ),
    )
    assert changed.status == "accepted" and not changed.plan.ready
    assert changed.plan.consents == reviewed.consents
    assert validate_review(changed.plan).status == "accepted"
    pending = next(row for row in changed.plan.requirements if row.domain == "storage")
    grant = next(row for row in changed.plan.consents if row.kind == "storage")
    assert grant.choice == "accept" and grant.assumptions != pending.assumptions
    change = changed.plan.proposal.changes[0]
    subjects = (VaultSubject(path=change.path, subject_id=change.subject_id),)
    admission = operations.inspect_history(vault, subjects=subjects).admission
    assert admission.preflight == changed.plan.preflight
    locator = vault / ".brz2obsidian/locator.json"
    old_locator = locator.read_bytes()
    old_objects = git(vault, "count-objects", "-v")
    old_user = user_git(vault)
    source_bytes = (source / "Notes/Opening.md").read_bytes()
    refused = operations.capture_checkpoint(
        vault,
        source,
        vault_id="vault-one",
        import_id="import-one",
        identity=facts.incoming_identity,
        admission=admission,
        subjects=subjects,
        review=changed.plan,
    )
    assert (refused.status, refused.code) == ("refused", "scoped_review_required")
    assert not refused.objects_written
    assert locator.read_bytes() == old_locator
    assert git(vault, "count-objects", "-v") == old_objects
    assert user_state(vault) == before
    accepted = resolve_review(
        changed.plan,
        action(
            changed.plan,
            decision_id="accept-current-storage-bytes",
            domain="storage",
            choice="accept",
            change_id=pending.change_id,
            reviewed_assumptions=pending.assumptions,
        ),
    )
    assert accepted.status == "accepted" and accepted.plan.ready
    saved = operations.capture_checkpoint(
        vault,
        source,
        vault_id="vault-one",
        import_id="import-one",
        identity=facts.incoming_identity,
        admission=admission,
        subjects=subjects,
        review=accepted.plan,
    )
    assert saved.status == "captured", saved.code
    assert user_git(vault) == old_user
    assert (source / "Notes/Opening.md").read_bytes() == source_bytes

"""Public recovery choices over actual retained operation history and vault bytes."""

import json

from brz2obsidian.application.operations import Operations
from brz2obsidian.contracts import ExactContent
from brz2obsidian.obsidian import inspect_text_candidate
from tests.application.test_vault_apply import _apply, _binary_link_case, _ready_case
from tests.application.test_vault_checkpoints import user_state
from tests.reconciliation.test_resolution import action


def test_stopped_apply_offers_both_first_recovery_directions_without_mutation():
    vault, source, operations, reviewed, _ = _ready_case()
    calls = 0

    def cancel():
        nonlocal calls
        calls += 1
        return calls == 2

    stopped = _apply(
        operations,
        vault,
        source,
        review=reviewed,
        vault_id="vault-one",
        import_id="import-one",
        cancel=cancel,
    )
    assert stopped.status == "cancelled" and stopped.intent_commit
    assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\n"
    retained_user_state = user_state(vault)
    retained_owner = (vault / ".git/brz2obsidian/owner.json").read_bytes()

    offered = Operations().prepare_recovery(vault)

    assert offered.status == "offered" and offered.code == "initial_recovery_choice"
    assert offered.operation_id == stopped.operation_id
    assert offered.kind == "apply" and offered.generation == stopped.generation
    assert offered.intent_commit == stopped.intent_commit
    assert offered.available_directions == ("finish", "restore")
    assert offered.review is None
    assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\n"
    assert user_state(vault) == retained_user_state
    assert (vault / ".git/brz2obsidian/owner.json").read_bytes() == retained_owner

    # A copied owner marker is only a hint; the retained Git intent is the
    # authority after the original process has stopped.
    marker = vault / ".git/brz2obsidian"
    (marker / "owner.json").unlink()
    (marker / "held").unlink()
    marker.rmdir()
    missing_marker = Operations().prepare_recovery(vault)
    assert missing_marker.status == "offered"
    assert missing_marker.intent_commit == stopped.intent_commit
    assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\n"
    assert user_state(vault) == retained_user_state

    # The edit happens after the stopped operation, so recovery must still be
    # discoverable while the new bytes await an explicit current review.
    (vault / "Notes/Opening.md").write_bytes(b"authored opening\r\nlater note\n")
    later = Operations().prepare_recovery(vault)
    assert later.status == "offered" and later.intent_commit == stopped.intent_commit
    assert later.available_directions == ("finish", "restore")
    assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\nlater note\n"

    reviewed_later = Operations().prepare_recovery(vault, direction="finish")
    assert reviewed_later.status == "offered"
    assert reviewed_later.direction == "finish"
    assert reviewed_later.review is not None
    assert reviewed_later.review.readiness == "review_required", reviewed_later.review.blockers
    assert reviewed_later.review.facts.subjects[0].current.content.data == (
        b"authored opening\r\nlater note\n"
    )
    assert reviewed_later.review.facts.generation > reviewed.proposal.generation
    assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\nlater note\n"

    restored_later = Operations().prepare_recovery(vault, direction="restore")
    assert restored_later.status == "offered" and restored_later.direction == "restore"
    assert restored_later.review is not None
    assert restored_later.review.readiness == "review_required", restored_later.review.blockers
    (reversal,) = restored_later.review.facts.subjects
    assert reversal.baseline.content.data == b"incoming opening\n"
    assert reversal.current.content.data == b"authored opening\r\nlater note\n"
    assert reversal.incoming.data == b"authored opening\r\n"
    assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\nlater note\n"

    assert [(r.domain, r.choices) for r in reviewed_later.review.requirements] == [
        ("text", ("current", "incoming", "edited"))
    ]
    kept = Operations().resolve_recovery(
        vault,
        reviewed_later,
        action(
            reviewed_later.review,
            domain="text",
            choice="current",
            decision_id="recovery:current:1",
        ),
    )
    assert kept.status == "offered" and kept.review.ready, kept.code
    assert kept.review.approvals[0].result.data == b"authored opening\r\nlater note\n"
    (vault / "Notes/Opening.md").write_bytes(
        b"authored opening\r\nlater note\nsecond later note\n"
    )
    after_later_edit = user_state(vault)
    stale = Operations().resolve_recovery(
        vault,
        kept,
        action(
            kept.review,
            domain="text",
            choice="incoming",
            decision_id="recovery:incoming:2",
        ),
    )
    assert stale.status == "refused" and stale.code == "recovery_review_stale"
    refreshed = Operations().refresh_recovery(vault, kept)
    assert refreshed.status == "offered" and refreshed.direction == "finish"
    assert refreshed.review.proposal.generation == kept.review.proposal.generation + 1
    assert refreshed.review.facts.subjects[0].current.content.data.endswith(
        b"second later note\n"
    )
    assert not refreshed.review.ready and refreshed.review.approvals == ()
    assert user_state(vault) == after_later_edit

    restored_current = Operations().refresh_recovery(vault, restored_later)
    assert restored_current.status == "offered" and not restored_current.review.ready
    assert [(r.domain, r.choices) for r in restored_current.review.requirements] == [
        ("text", ("current", "incoming", "edited"))
    ]
    restore_facts = restored_current.review.facts
    restore_subject = restore_facts.subjects[0]
    restore_links = restore_facts.link_context
    restore_candidate = inspect_text_candidate(
        ExactContent(data=b"authored opening\r\n"),
        identity=restore_facts.identity_inventory[0].identity,
        target=restore_subject.source_target,
        output_format=7,
        source_path=restore_subject.path,
        document_id=restore_links.incoming_documents[0].document_id,
        path_mode="vault",
        link_targets=restore_links.incoming_targets,
        link_target_facts=restore_links.incoming_target_facts,
        link_inventory="complete",
    )
    chosen_restore = Operations().resolve_recovery(
        vault,
        restored_current,
        action(
            restored_current.review,
            domain="text",
            choice="incoming",
            decision_id="recovery:restore:1",
            candidate=restore_candidate,
        ),
    )
    assert chosen_restore.status == "offered" and chosen_restore.review.ready
    completed = Operations().execute_recovery(vault, chosen_restore)
    assert completed.status == "restored" and completed.publication == "complete", completed.code
    assert completed.direction == "restore" and completed.receipt_commit
    assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\n"
    assert Operations().inspect_update_status(vault).status == "restored"
    assert user_state(vault)["index"] == after_later_edit["index"]


def test_torn_owner_marker_refuses_recovery_preparation_without_touching_vault():
    vault, source, operations, reviewed, _ = _ready_case()
    calls = 0

    def cancel():
        nonlocal calls
        calls += 1
        return calls == 2

    stopped = _apply(
        operations,
        vault,
        source,
        review=reviewed,
        vault_id="vault-one",
        import_id="import-one",
        cancel=cancel,
    )
    assert stopped.status == "cancelled" and stopped.intent_commit
    owner = vault / ".git/brz2obsidian/owner.json"
    owner.write_bytes(b'{"schema_id":"torn"')
    retained_user_state = user_state(vault)

    offered = Operations().prepare_recovery(vault)

    assert offered.status == "unavailable" and offered.code == "operation_marker_invalid"
    assert offered.available_directions == () and offered.review is None
    assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\n"
    assert owner.read_bytes() == b'{"schema_id":"torn"'
    assert user_state(vault) == retained_user_state


def test_missing_checkpoint_locator_reports_unknown_history_without_authored_mutation():
    vault, source, operations, reviewed, _ = _ready_case()
    calls = 0

    def cancel():
        nonlocal calls
        calls += 1
        return calls == 2

    stopped = _apply(
        operations,
        vault,
        source,
        review=reviewed,
        vault_id="vault-one",
        import_id="import-one",
        cancel=cancel,
    )
    assert stopped.status == "cancelled" and stopped.intent_commit
    locator = vault / ".brz2obsidian/locator.json"
    locator.unlink()
    damaged_state = user_state(vault)

    observed = Operations().inspect_update_status(vault)
    offered = Operations().prepare_recovery(vault, direction="finish")
    gated = Operations().inspect_history(vault)

    assert observed.status == "unknown" and observed.recovery_required
    assert observed.publication == "unknown" and observed.history == "unknown"
    assert offered.status == "unavailable" and offered.review is None
    assert gated.status == "unavailable"
    assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\n"
    assert not locator.exists()
    assert user_state(vault) == damaged_state


def test_partial_binary_both_restore_reviews_created_asset_and_owner_as_one_operation():
    from brz2obsidian.publication.vault_replace import move_file

    vault, source, _, reviewed, before, changed_document = _binary_link_case()
    original_document = (vault / "Notes/Owner.md").read_bytes()
    created = vault / "Assets/data (incoming-ba7816bf).bin"

    class StopAfterActualFirstMove:
        calls = 0

        def move(self, stage, target, *, replace):
            move_file(stage, target, replace=replace)
            self.calls += 1
            if self.calls == 1:
                raise OSError("Stopped after actual new asset publication")

        def remove(self, target, destination):
            raise AssertionError("Original selected effect has no removal")

    stopped = _apply(
        Operations(vault_executor=StopAfterActualFirstMove()),
        vault,
        source,
        review=reviewed,
        vault_id="vault-one",
        import_id="import-one",
    )
    assert stopped.status == "incomplete" and stopped.recovery_required
    assert created.read_bytes() == b"abc"
    assert (vault / "Assets/data.bin").read_bytes() == b"\x00authored"
    assert (vault / "Notes/Owner.md").read_bytes() == original_document
    assert (vault / "Notes/Owner.md").read_bytes() != changed_document
    retained = user_state(vault)

    offered = Operations().prepare_recovery(vault, direction="restore")
    assert offered.status == "offered" and offered.review is not None, offered.code
    assert any(
        requirement.domain == "reversal"
        and change.target_path == "Assets/data (incoming-ba7816bf).bin"
        for requirement in offered.review.requirements
        for change in offered.review.proposal.changes
        if change.change_id == requirement.change_id
    )
    assert created.read_bytes() == b"abc"
    assert (vault / "Notes/Owner.md").read_bytes() == original_document
    assert user_state(vault) == retained
    assert retained["index"] == before["index"]


def test_ready_stopped_apply_finishes_through_retained_direction_and_actual_result():
    vault, source, operations, reviewed, before = _ready_case()
    calls = 0

    def cancel():
        nonlocal calls
        calls += 1
        return calls == 2

    stopped = _apply(
        operations,
        vault,
        source,
        review=reviewed,
        vault_id="vault-one",
        import_id="import-one",
        cancel=cancel,
    )
    assert stopped.status == "cancelled" and stopped.intent_commit
    assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\n"
    (source / "Notes/Opening.md").unlink()
    assert not (source / "Notes/Opening.md").exists()
    offer = Operations().prepare_recovery(vault, direction="finish")
    assert offer.status == "offered" and offer.review.ready, (
        offer.code,
        len(offer.review.approvals) if offer.review else None,
        offer.review.history.events[-1].changed_keys if offer.review else None,
    )
    old_owner = (vault / ".git/brz2obsidian/owner.json").read_bytes()
    old_held = (vault / ".git/brz2obsidian/held").read_bytes()

    completed = Operations().execute_recovery(vault, offer)
    assert completed.status == "applied" and completed.publication == "complete", (
        completed.code,
        completed.phase,
        completed.history,
    )
    assert completed.intent_commit and completed.receipt_commit
    assert completed.direction == "finish" and completed.kind == "apply"
    assert (vault / "Notes/Opening.md").read_bytes() == b"incoming opening\n"
    fresh = Operations().inspect_update_status(vault)
    assert fresh.status == "applied" and fresh.receipt_commit == completed.receipt_commit
    assert user_state(vault)["index"] == before["index"]

    # Reintroduce only the exact old fixture-owned marker to model a failed
    # final directory cleanup after the real result and receipt were retained.
    marker = vault / ".git/brz2obsidian"
    marker.mkdir()
    (marker / "owner.json").write_bytes(old_owner)
    (marker / "held").write_bytes(old_held)
    pending = Operations().inspect_update_status(vault)
    assert pending.status == "content_complete" and pending.code == "terminal_cleanup_required"
    cleanup = Operations().prepare_recovery(vault)
    assert cleanup.status == "cleanup" and cleanup.review is None
    assert Operations().prepare_recovery(vault, direction="restore").status == "refused"
    after_cleanup = Operations().execute_recovery(vault, cleanup)
    assert after_cleanup.status == "applied" and after_cleanup.receipt_commit == completed.receipt_commit
    assert not marker.exists()


def test_fully_published_apply_without_receipt_finishes_as_applied_with_zero_new_moves():
    from brz2obsidian.publication.vault_replace import move_file

    vault, source, _, reviewed, before = _ready_case()

    class StopAfterActualMove:
        def move(self, stage, target, *, replace):
            move_file(stage, target, replace=replace)
            raise OSError("Stopped after exact authored replacement")

        def remove(self, target, destination):
            raise AssertionError("This selected update has no removal")

    stopped = _apply(
        Operations(vault_executor=StopAfterActualMove()),
        vault,
        source,
        review=reviewed,
        vault_id="vault-one",
        import_id="import-one",
    )
    assert stopped.status == "content_complete" and stopped.recovery_required
    assert (vault / "Notes/Opening.md").read_bytes() == b"incoming opening\n"
    retained_user_state = user_state(vault)

    offered = Operations().prepare_recovery(vault, direction="finish")
    assert offered.status == "offered" and offered.review.ready, offered.code
    completed = Operations().execute_recovery(vault, offered)

    assert completed.status == "applied" and completed.publication == "complete", completed.code
    assert completed.planned_files == completed.published_files == 0
    assert completed.authored_files_changed is False
    assert completed.receipt_commit and completed.result_commit
    assert Operations().inspect_update_status(vault).status == "applied"
    assert (vault / "Notes/Opening.md").read_bytes() == b"incoming opening\n"
    after = user_state(vault)
    for key in ("index", "head", "config", "stages", "authored"):
        assert after[key] == retained_user_state[key]
    checkpoint_ref = json.loads(
        (vault / ".brz2obsidian/locator.json").read_bytes()
    )["association"]["ref"]
    assert checkpoint_ref.endswith("/checkpoints")
    operation_ref = checkpoint_ref.removesuffix("/checkpoints") + "/operations/" + stopped.operation_id
    owned_refs = {checkpoint_ref.encode(), operation_ref.encode()}
    assert tuple(
        row for row in after["refs"] if row.split(b" ", 1)[0] not in owned_refs
    ) == tuple(
        row
        for row in retained_user_state["refs"]
        if row.split(b" ", 1)[0] not in owned_refs
    )
    assert retained_user_state["index"] == before["index"]
